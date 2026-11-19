"""Tool definitions for the diagnosis agent, and the code checks on its conclusion."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from tutor.planning import StudyUnit

from .state import LearnerState


MAX_QUESTIONS = 5
NEXT_STEPS = ("review_gap", "practice_current", "continue")


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


def tool_schemas(units: Sequence[StudyUnit]) -> list[dict[str, Any]]:
    """Unit IDs come from this learner's material, so each session gets its own enums."""
    unit_ids = [unit.unit_id for unit in units]
    return [
        {
            "type": "function",
            "name": "get_learner_state",
            "description": "Get the current evidence for every study unit: the learner's self-report, "
                           "scored answers, and the status derived from them.",
            "strict": True,
            "parameters": _object({}),
        },
        {
            "type": "function",
            "name": "ask_question",
            "description": "Ask the learner one question checked against the unit's reading. The scored "
                           f"answer is returned as this call's output. At most {MAX_QUESTIONS} per diagnosis.",
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
                "next_step": {"type": "string", "enum": list(NEXT_STEPS)},
                "summary": {"type": "string", "description": "Two sentences to the learner about what "
                                                            "their answers showed."},
            }),
        },
    ]


def validate_finish(arguments: dict[str, Any], state: LearnerState) -> str | None:
    """Return why the conclusion is not supported, or None when it can be accepted."""
    gap = arguments.get("primary_gap")
    status = arguments.get("status")
    evidence = arguments.get("evidence") or []
    if gap != "none" and gap not in state.units:
        return f"Unknown unit {gap!r}. Use a unit_id from the list or 'none'."
    if status not in ("confirmed", "uncertain"):
        return "status must be 'confirmed' or 'uncertain'."
    if arguments.get("next_step") not in NEXT_STEPS:
        return f"next_step must be one of {', '.join(NEXT_STEPS)}."
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
        gaps = [unit_id for unit_id in state.units if state.status(unit_id) == "gap"]
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


def fallback_diagnosis(state: LearnerState) -> Diagnosis:
    """Used when the tutor runs out of calls: name the likeliest unit, but stay uncertain."""
    def wrong(unit_id: str) -> int:
        return sum(not answer.correct for answer in state.units[unit_id].answers)

    candidates = sorted(state.units, key=lambda unit_id: (state.status(unit_id) != "gap", -wrong(unit_id)))
    likely = next((unit_id for unit_id in candidates if wrong(unit_id)), None)
    if likely is None:
        likely = next((unit_id for unit_id in state.units if state.status(unit_id) == "suspected"), None)
    evidence = tuple(a.question_id for a in state.answers() if likely and a.unit_id == likely)
    return Diagnosis(
        primary_gap=likely, status="uncertain", evidence=evidence,
        next_step="review_gap" if likely else "continue",
        summary="The tutor stopped before it had enough evidence for a conclusion. "
                "Practice the unit below and the diagnosis can continue later.",
        forced=True,
    )
