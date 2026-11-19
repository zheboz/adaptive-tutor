"""Ask what the learner finds unclear and show the evidence behind each unit's status."""

from collections.abc import Sequence
from html import escape

import streamlit as st

from tutor.agent.intake import MAX_NOTE_CHARS, read_self_report
from tutor.agent.state import LearnerState
from tutor.llm import LLMError
from tutor.planning import StudyUnit


STATUS_LABELS = {
    "untested": "Not checked yet",
    "suspected": "Marked unclear · not checked yet",
    "uncertain": "Needs more evidence",
    "mastered": "Understood",
    "gap": "Likely gap",
}
_FORM_KEYS = ("self_report_units", "self_report_note")


def learner_state(units: Sequence[StudyUnit]) -> LearnerState:
    """Keep one record per set of study units; a new unit plan starts a new record."""
    state = st.session_state.get("learner_state")
    if state is None or not state.matches(units):
        state = LearnerState(units)
        st.session_state.learner_state = state
        for key in ("learner_intake", *_FORM_KEYS):
            st.session_state.pop(key, None)
    return state


def render_self_report(units: Sequence[StudyUnit]) -> None:
    state = learner_state(units)
    titles = {unit.unit_id: unit.title for unit in units}
    with st.form("self_report"):
        st.subheader("What's unclear?")
        checked = st.multiselect(
            "Units I don't understand", options=list(titles), format_func=titles.__getitem__,
            key="self_report_units",
        )
        note = st.text_area(
            "Describe what you don't understand (optional)", max_chars=MAX_NOTE_CHARS, key="self_report_note",
            help="For example: “I don't see why x = x + 1 changes x.” The tutor matches it to your material.",
        )
        submitted = st.form_submit_button("Save")
    if submitted:
        try:
            with st.spinner("Matching your note to the material…"):
                intake = read_self_report(units, checked, note)
        except LLMError as error:
            st.error(str(error))
            return
        state.apply_report(intake.checked_ids, intake.note, intake.noted_ids, intake.missing_topic)
        st.session_state.learner_intake = intake

    intake = st.session_state.get("learner_intake")
    if intake is None:
        return
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
        parts.append("you marked it unclear")
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
