"""Tool definitions for the diagnosis agent, and the code checks on its conclusion.

The same agent runs two kinds of check, configured by ``CheckConfig``:

- initial: before studying, check the units the learner marked weak (up to 5 questions, all units)
- daily:   after a study day's practice, decide whether to continue, review today's material, or
           revisit an earlier unit (up to 3 follow-up questions, today's and earlier units only)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from tutor.planning import StudyUnit

from .state import LearnerState


MAX_QUESTIONS = 5
DAILY_QUESTIONS = 3
INITIAL_STEPS = ("review_gap", "continue")
DAILY_STEPS = ("continue", "review_today", "revisit_earlier")


@dataclass(frozen=True)
class CheckConfig:
    mode: Literal["initial", "daily"]
    scope: tuple[str, ...]
    max_questions: int
    next_steps: tuple[str, ...]
    today: tuple[str, ...] = ()
    day: int | None = None


def initial_config(units: Sequence[StudyUnit]) -> CheckConfig:
    return CheckConfig("initial", tuple(unit.unit_id for unit in units), MAX_QUESTIONS, INITIAL_STEPS)


def daily_config(units: Sequence[StudyUnit], today: Sequence[str], day: int) -> CheckConfig:
    """Today's units and every unit before them in study order."""
    order = [unit.unit_id for unit in units]
    today = tuple(dict.fromkeys(unit_id for unit_id in today if unit_id in order))
    last = max(order.index(unit_id) for unit_id in today)
    return CheckConfig("daily", tuple(order[:last + 1]), DAILY_QUESTIONS, DAILY_STEPS, today, day)


@dataclass(frozen=True)
class Diagnosis:
    primary_gap: str | None
    status: Literal["confirmed", "uncertain"]
    evidence: tuple[str, ...]
    next_step: str
    summary: str
    # True when the tutor stopped at its call limit instead of concluding.
    forced: bool = False


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def tool_schemas(units: Sequence[StudyUnit], config: CheckConfig | None = None) -> list[dict[str, Any]]:
    """Unit IDs come from this learner's material and the check's scope, so each session gets its own enums."""
    config = config or initial_config(units)
    unit_ids = list(config.scope)
    return [
        {
            "type": "function",
            "name": "get_learner_state",
            "description": "Get the current evidence for every study unit: whether the learner marked it "
                           "weak, scored answers, and the status derived from them.",
            "strict": True,
            "parameters": _object({}),
        },
        {
            "type": "function",
            "name": "ask_question",
            "description": "Ask the learner one question checked against the unit's reading. The scored "
                           f"answer is returned as this call's output. At most {config.max_questions} per check.",
            "strict": True,
            "parameters": _object({
                "unit_id": {"type": "string", "enum": unit_ids},
                "reason": {"type": "string", "description": "Why this unit, given the evidence so far."},
            }),
        },
        {
            "type": "function",
            "name": "finish",
            "description": "Report the learner's main difficulty and the answers that support it. "
                           "Rejected with a reason when the evidence does not support the conclusion.",
            "strict": True,
            "parameters": _object({
                "primary_gap": {"type": "string", "enum": [*unit_ids, "none"]},
                "status": {"type": "string", "enum": ["confirmed", "uncertain"]},
                "evidence": {"type": "array", "items": {"type": "string"},
                             "description": "question_id values of the answers that support the conclusion."},
                "next_step": {"type": "string", "enum": list(config.next_steps)},
                "summary": {"type": "string", "description": "Two sentences to the learner about what "
                                                            "their answers showed."},
            }),
        },
    ]


def _check_next_step(gap: str, status: str, next_step: str, config: CheckConfig) -> str | None:
    if next_step not in config.next_steps:
        return f"next_step must be one of {', '.join(config.next_steps)}."
    if status == "confirmed" and gap != "none" and next_step == "continue":
        return "A confirmed gap needs review; choose a review step instead of continue."
    if config.mode == "initial":
        if next_step == "review_gap" and gap == "none":
            return "review_gap needs a unit in primary_gap."
        return None
    if next_step == "review_today" and gap != "none" and gap not in config.today:
        return f"{gap} was not studied today; use revisit_earlier for an earlier unit."
    if next_step == "revisit_earlier" and (gap == "none" or gap in config.today):
        return "revisit_earlier needs an earlier unit (not one of today's) in primary_gap."
    return None


def validate_finish(arguments: dict[str, Any], state: LearnerState, config: CheckConfig | None = None) -> str | None:
    """Return why the conclusion is not supported, or None when it can be accepted."""
    config = config or initial_config([evidence.unit for evidence in state.units.values()])
    gap = arguments.get("primary_gap")
    status = arguments.get("status")
    evidence = arguments.get("evidence") or []
    if gap != "none" and gap not in config.scope:
        return f"Unknown unit {gap!r}. Use a unit_id from the list or 'none'."
    if status not in ("confirmed", "uncertain"):
        return "status must be 'confirmed' or 'uncertain'."
    problem = _check_next_step(gap, status, arguments.get("next_step"), config)
    if problem:
        return problem
    if not str(arguments.get("summary", "")).strip():
        return "Write a short summary for the learner."
    unknown = [question_id for question_id in evidence if state.answer(question_id) is None]
    if unknown:
        return f"These evidence IDs are not answers the learner gave: {', '.join(unknown)}."
    if status == "uncertain":
        return None

    answers = state.answers()
    if not answers:
        return "There are no answers yet. Ask a question, or finish with status 'uncertain'."
    if gap == "none":
        gaps = [unit_id for unit_id in config.scope if state.status(unit_id) == "gap"]
        if gaps:
            return f"The answers show a likely gap in {', '.join(gaps)}; it cannot be 'none'."
        if len(answers) < 2:
            return "One answer cannot rule out every gap. Ask another question or finish as 'uncertain'."
        return None
    if state.status(gap) != "gap":
        return (f"{gap} has status '{state.status(gap)}'. A confirmed gap needs at least two wrong answers "
                "on that unit that outnumber the correct ones. Ask another question on it, or finish "
                "with status 'uncertain'.")
    if not any(not state.answer(question_id).correct and state.answer(question_id).unit_id == gap
               for question_id in evidence):
        return f"Cite the wrong answers on {gap} in evidence."
    return None


def to_diagnosis(arguments: dict[str, Any], forced: bool = False) -> Diagnosis:
    gap = arguments["primary_gap"]
    return Diagnosis(
        primary_gap=None if gap == "none" else gap,
        status=arguments["status"],
        evidence=tuple(dict.fromkeys(arguments.get("evidence") or [])),
        next_step=arguments["next_step"],
        summary=" ".join(str(arguments["summary"]).split()),
        forced=forced,
    )


def fallback_diagnosis(state: LearnerState, config: CheckConfig | None = None) -> Diagnosis:
    """Used when the tutor runs out of calls: name the likeliest unit, but stay uncertain."""
    config = config or initial_config([evidence.unit for evidence in state.units.values()])

    def wrong(unit_id: str) -> int:
        return sum(not answer.correct for answer in state.units[unit_id].answers)

    candidates = sorted(config.scope, key=lambda unit_id: (state.status(unit_id) != "gap", -wrong(unit_id)))
    likely = next((unit_id for unit_id in candidates if wrong(unit_id)), None)
    if likely is None:
        likely = next((unit_id for unit_id in config.scope if state.status(unit_id) == "suspected"), None)
    evidence = tuple(a.question_id for a in state.answers() if likely and a.unit_id == likely)
    if config.mode == "initial":
        next_step = "review_gap" if likely else "continue"
    elif likely is None:
        next_step = "continue"
    else:
        next_step = "review_today" if likely in config.today else "revisit_earlier"
    return Diagnosis(
        primary_gap=likely, status="uncertain", evidence=evidence, next_step=next_step,
        summary="The tutor stopped before it had enough evidence for a conclusion. "
                "Practice the unit below and check again later.",
        forced=True,
    )
