"""Weak topics marked on the outline, and the evidence behind each unit's status."""

from collections.abc import Sequence
from html import escape

import streamlit as st

from tutor.agent.state import LearnerState
from tutor.planning import StudyUnit


STATUS_LABELS = {
    "untested": "Not checked yet",
    "suspected": "Marked weak · not checked yet",
    "uncertain": "Needs more evidence",
    "mastered": "Understood",
    "gap": "Likely gap",
}
WEAK_TOPIC_PREFIX = "weak_topic_"


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


def learner_state(units: Sequence[StudyUnit]) -> LearnerState:
    """Keep one record per set of study units; a new unit plan starts a new record."""
    state = st.session_state.get("learner_state")
    if state is None or not state.matches(units):
        state = LearnerState(units)
        st.session_state.learner_state = state
    return state


def apply_plan_inputs(units: Sequence[StudyUnit]) -> tuple[str, ...]:
    """Record the weak topics checked when the plan was created; return the weak unit IDs."""
    weak = weak_unit_ids(units)
    learner_state(units).apply_report(weak)
    return weak


def _evidence_text(evidence) -> str:
    parts = []
    if evidence.answers:
        right = sum(answer.correct for answer in evidence.answers)
        parts.append(f"{right} of {len(evidence.answers)} answers correct")
    if evidence.self_reported:
        parts.append("you marked it weak")
    return " · ".join(parts) or "No answers yet"


def render_learning_status(units: Sequence[StudyUnit], height: int) -> None:
    state = learner_state(units)
    st.header("Learning status")
    with st.container(height=height, border=True, key="learning_status_panel"):
        st.caption("Each status comes from your answers and the topics you marked weak, not from the reading alone.")
        for evidence in state.units.values():
            st.html(
                f"<p><strong>{escape(evidence.unit.title)}</strong> · {STATUS_LABELS[evidence.status]}"
                f"<br><small>{escape(_evidence_text(evidence))}</small></p>"
            )
