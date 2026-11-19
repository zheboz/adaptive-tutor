"""Weak topics marked on the outline, the learner's note, and the evidence behind each unit's status."""

from collections.abc import Sequence
from html import escape

import streamlit as st

from tutor.agent.intake import MAX_NOTE_CHARS, Intake, read_self_report
from tutor.agent.state import LearnerState
from tutor.llm import LLMError
from tutor.planning import StudyUnit


STATUS_LABELS = {
    "untested": "Not checked yet",
    "suspected": "Marked weak · not checked yet",
    "uncertain": "Needs more evidence",
    "mastered": "Understood",
    "gap": "Likely gap",
}
WEAK_TOPIC_PREFIX = "weak_topic_"
NOTE_KEY = "self_report_note"


def weak_topic_key(index: int) -> str:
    return f"{WEAK_TOPIC_PREFIX}{index}"


def render_weak_topic_checkbox(index: int) -> None:
    st.checkbox("I find this weak or unclear", key=weak_topic_key(index))


def clear_weak_topics() -> None:
    for key in [key for key in st.session_state if str(key).startswith(WEAK_TOPIC_PREFIX)]:
        del st.session_state[key]


def weak_topic_numbers() -> set[int]:
    """1-based outline topic numbers the learner has checked."""
    return {
        int(str(key)[len(WEAK_TOPIC_PREFIX):]) + 1
        for key, checked in st.session_state.items()
        if str(key).startswith(WEAK_TOPIC_PREFIX) and checked
    }


def weak_unit_ids(units: Sequence[StudyUnit]) -> tuple[str, ...]:
    topics = weak_topic_numbers()
    return tuple(unit.unit_id for unit in units if topics.intersection(unit.topic_ids))


def render_note_input() -> None:
    st.text_area(
        "Describe what you don't understand (optional)", max_chars=MAX_NOTE_CHARS, key=NOTE_KEY,
        help="For example: “I don't see why x = x + 1 changes x.” The tutor matches it to your material.",
    )


def learner_state(units: Sequence[StudyUnit]) -> LearnerState:
    """Keep one record per set of study units; a new unit plan starts a new record."""
    state = st.session_state.get("learner_state")
    if state is None or not state.matches(units):
        state = LearnerState(units)
        st.session_state.learner_state = state
        st.session_state.pop("learner_intake", None)
    return state


def apply_plan_inputs(units: Sequence[StudyUnit]) -> tuple[str, ...]:
    """Record the weak topics and note submitted with the plan; return the weak unit IDs.

    The note is matched again only when it or the weak topics change.
    """
    state = learner_state(units)
    checked = weak_unit_ids(units)
    note = " ".join(str(st.session_state.get(NOTE_KEY, "")).split())
    previous: Intake | None = st.session_state.get("learner_intake")
    if previous is None or previous.checked_ids != checked or previous.note != note:
        try:
            with st.spinner("Matching your note to the material…"):
                intake = read_self_report(units, checked, note)
        except LLMError as error:
            st.error(f"Your note could not be matched to the material. {error}")
            intake = Intake(checked, "", (), None)
        st.session_state.learner_intake = intake
        state.apply_report(intake.checked_ids, intake.note, intake.noted_ids, intake.missing_topic)
    return st.session_state.learner_intake.unit_ids


def render_intake_feedback(units: Sequence[StudyUnit]) -> None:
    intake: Intake | None = st.session_state.get("learner_intake")
    if intake is None:
        return
    titles = {unit.unit_id: unit.title for unit in units}
    if intake.noted_ids:
        st.caption("Your note matches: " + "; ".join(titles[unit_id] for unit_id in intake.noted_ids))
    if intake.missing_topic:
        st.info(
            f"Your material doesn't seem to cover “{intake.missing_topic}”. "
            "Upload material that explains it to study it here."
        )


def _evidence_text(evidence) -> str:
    parts = []
    if evidence.answers:
        right = sum(answer.correct for answer in evidence.answers)
        parts.append(f"{right} of {len(evidence.answers)} answers correct")
    if evidence.self_reported:
        parts.append("you marked it weak")
    if evidence.notes:
        parts.append(f"your note: “{evidence.notes[0]}”")
    return " · ".join(parts) or "No answers yet"


def render_learning_status(units: Sequence[StudyUnit], height: int) -> None:
    state = learner_state(units)
    st.header("Learning status")
    with st.container(height=height, border=True, key="learning_status_panel"):
        st.caption("Each status comes from your answers and what you reported, not from the reading alone.")
        for evidence in state.units.values():
            st.html(
                f"<p><strong>{escape(evidence.unit.title)}</strong> · {STATUS_LABELS[evidence.status]}"
                f"<br><small>{escape(_evidence_text(evidence))}</small></p>"
            )
