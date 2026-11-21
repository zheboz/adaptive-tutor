"""Diagnosis tasks: the daily-check ReAct agent against a fixed-question baseline, with a simulated learner.

Units and questions are a fixed, hand-written snapshot of the Week 2 slides (diagnosis_bank.json), and
each task fixes the learner's answer to every question, so differences between runs come from the agent
alone. The baseline asks the first two questions of every unit studied today without looking at the
answers, then makes one model call for the conclusion, checked by the same validate_finish.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from tutor.agent.bank import DiagnosticQuestion
from tutor.agent.loop import Ask, advance, instructions, start_session
from tutor.agent.state import LearnerState
from tutor.agent.tools import Diagnosis, daily_config, fallback_diagnosis, tally, to_diagnosis, validate_finish
from tutor.assessment.questions import Question
from tutor.llm import Span, Trace, generate_structured, tracing
from tutor.planning import StudyUnit


SNAPSHOT = json.loads((Path(__file__).parent / "diagnosis_bank.json").read_text())
UNITS = tuple(StudyUnit(u["unit_id"], u["title"], u["objective"], tuple(u["source_ids"]), u["activity"])
              for u in SNAPSHOT["units"])
# The correct option is always the first; the agent sees only the prompt, the learner's choice and the score.
QUESTIONS = {
    unit_id: tuple(DiagnosticQuestion(f"{unit_id}:q{n}", unit_id, Question(
        "multiple_choice", q["prompt"], tuple(q["options"]), 0, "", "generated", (q["source"],), "reading"))
        for n, q in enumerate(items, 1))
    for unit_id, items in SNAPSHOT["questions"].items()
}
BASELINE_QUESTIONS = 2
BASELINE_NOTE = """
The questions have already been asked, two per unit studied today, and no more can be asked. Give the
conclusion now from learner_state and this_check: primary_gap is a unit_id or "none", and evidence lists
question_id values of the answers that support it."""


class FixedBank:
    """The snapshot's questions in order; `available` caps a unit's questions to test running out."""

    def __init__(self, available: dict[str, int]):
        self.problems: dict[str, str] = {}
        self.questions = {u: qs[:available.get(u, len(qs))] for u, qs in QUESTIONS.items()}

    def pick(self, unit_id, exclude):
        return next((q for q in self.questions.get(unit_id, ()) if q.id not in exclude), None)

    def remaining(self, unit_id, exclude):
        return sum(q.id not in exclude for q in self.questions.get(unit_id, ()))


class Conclusion(BaseModel):
    primary_gap: str
    status: Literal["confirmed", "uncertain"]
    evidence: list[str]
    next_step: str
    summary: str


def _setup(task):
    state = LearnerState(UNITS)
    state.apply_report(task.get("marked_weak", []))
    for unit_id, results in task.get("earlier", {}).items():  # e.g. the initial quiz
        for n, correct in enumerate(results, 1):
            state.record(f"quiz:{unit_id}:q{n}", unit_id, "multiple_choice", correct, "quiz")
    return state, FixedBank(task.get("available", {})), daily_config(UNITS, task["today"], task["day"])


def _correct(task, question: DiagnosticQuestion) -> bool:
    return task["answers"][question.unit_id][int(question.id.rsplit(":q", 1)[1]) - 1]


def run_agent(task) -> tuple[Diagnosis, Trace, int]:
    state, bank, config = _setup(task)
    session = start_session(UNITS, state, bank, config)
    step = advance(session)
    while isinstance(step, Ask):
        step = advance(session, 0 if _correct(task, step.question) else 1)
    return step.diagnosis, session.trace, len(session.asked)


def run_baseline(task) -> tuple[Diagnosis, Trace, int]:
    state, bank, config = _setup(task)
    asked = []
    for unit_id in config.askable:
        for _ in range(BASELINE_QUESTIONS):
            if question := bank.pick(unit_id, asked):
                asked.append(question.id)
                state.record(question.id, unit_id, "multiple_choice", _correct(task, question), "diagnosis")
    content = json.dumps({
        "units_in_study_order": [{"unit_id": u.unit_id, "title": u.title} for u in UNITS if u.unit_id in config.scope],
        "studied_today": list(config.today),
        "learner_state": state.summary(),
        "this_check": {u: t.as_dict(config.per_unit) for u, t in tally(state, asked).items()},
        "summary_language": "English",
    })
    trace = Trace()
    with tracing(trace):
        args = generate_structured(instructions=instructions(config) + BASELINE_NOTE, content=content,
                                   schema=Conclusion).model_dump()
    # A rejected conclusion falls back to the same uncertain diagnosis the agent gets at its call limit.
    rejected = validate_finish(args, state, config, asked)
    trace.spans.append(Span("check:finish", 0.0, detail=f"{args['primary_gap']} ({args['status']}, "
                                                        f"{args['next_step']})", error=rejected))
    return (fallback_diagnosis(state, config) if rejected else to_diagnosis(args)), trace, len(asked)


def grade(task, diagnosis: Diagnosis) -> tuple[bool, str]:
    actual = {"primary_gap": diagnosis.primary_gap or "none", "status": diagnosis.status,
              "next_step": diagnosis.next_step}
    if diagnosis.forced:
        return False, f"no accepted conclusion; fallback {actual}"
    wrong = [f"{key}={actual[key]}, expected {' or '.join(allowed)}"
             for key, allowed in task["expected"].items() if actual[key] not in allowed]
    return not wrong, "; ".join(wrong) or ", ".join(f"{k}={v}" for k, v in actual.items())
