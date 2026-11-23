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
# Topic numbers in the order the learner checked them. This list, not the checkboxes, is the record:
# a checkbox's own state is dropped while the outline is hidden behind another view.
WEAK_TOPIC_ORDER = "checked_topic_order"


def weak_topic_key(index: int) -> str:
    return f"{WEAK_TOPIC_PREFIX}{index}"


def _track_order(index: int) -> None:
    order = st.session_state.setdefault(WEAK_TOPIC_ORDER, [])
    number = index + 1
    if st.session_state.get(weak_topic_key(index)):
        if number not in order:
            order.append(number)
    elif number in order:
        order.remove(number)


def render_weak_topic_checkbox(index: int) -> None:
    st.checkbox("I don't understand this", key=weak_topic_key(index), value=index + 1 in weak_topics_in_order(),
                on_change=_track_order, args=(index,))


def clear_weak_topics() -> None:
    for key in [key for key in st.session_state if str(key).startswith(WEAK_TOPIC_PREFIX)]:
        del st.session_state[key]
    st.session_state.pop(WEAK_TOPIC_ORDER, None)


def weak_topics_in_order() -> list[int]:
    """1-based topic numbers in the order they were checked."""
    return list(st.session_state.get(WEAK_TOPIC_ORDER, []))


def weak_topic_numbers() -> set[int]:
    """1-based outline topic numbers the learner has checked."""
    return set(weak_topics_in_order())


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
    """Record the weak topics checked when the plan was created; return the units that get extra time.

    Answers count too: a reported unit the learner has since mastered gets no extra time, and a
    unit the tutor's checks found weak keeps it.
    """
    state = learner_state(units)
    state.apply_report(weak_unit_ids(units))
    return state.focus_units()


def _evidence_text(evidence) -> str:
    parts = []
    if evidence.answers:
        right = sum(answer.correct for answer in evidence.answers)
        parts.append(f"{right} of {len(evidence.answers)} answers correct")
    if evidence.self_reported:
        parts.append("you marked it weak")
    return " · ".join(parts) or "No answers yet"


# The chapter bar's segments, in order: what is settled first, what is still open last.
PROGRESS_SEGMENTS = (
    ("understood", "Understood", ("mastered",)),
    ("uncertain", "Needs more evidence", ("uncertain",)),
    ("gap", "Likely gap", ("gap",)),
    ("untested", "Not checked yet", ("untested", "suspected")),
)


# How much each segment's units count toward the chapter's percentage: an understood unit fully, one
# that needs more evidence half; a likely gap or an unchecked unit not yet.
PROGRESS_WEIGHTS = {"understood": 1.0, "uncertain": 0.5, "gap": 0.0, "untested": 0.0}


def chapter_progress(state: LearnerState) -> dict[str, int]:
    """How many of the chapter's units are in each segment of the progress bar."""
    statuses = [evidence.status for evidence in state.units.values()]
    return {name: sum(status in members for status in statuses) for name, _, members in PROGRESS_SEGMENTS}


def chapter_percent(counts: dict[str, int]) -> int:
    """The chapter's progress in percent, each unit weighted by how it stands (see PROGRESS_WEIGHTS)."""
    total = sum(counts.values())
    if not total:
        return 0
    return round(100 * sum(PROGRESS_WEIGHTS[name] * count for name, count in counts.items()) / total)


def chapter_progress_html(counts: dict[str, int], days_checked: int, plan_days: int) -> str:
    """One large bar for the whole chapter: its weighted percentage, and how each unit stands.
    Styled in app.py's layout CSS."""
    total = sum(counts.values())
    understood = counts["understood"]
    percent = chapter_percent(counts)
    segments = "".join(
        f'<span class="chapter-bar-part {name}" style="width: {100 * counts[name] / total:.4f}%" '
        f'title="{label}: {counts[name]}"></span>'
        for name, label, _ in PROGRESS_SEGMENTS if total and counts[name]
    )
    legend = "".join(
        f'<span class="chapter-legend-item"><span class="chapter-legend-swatch {name}"></span>'
        f"{label} <strong>{counts[name]}</strong></span>"
        for name, label, _ in PROGRESS_SEGMENTS
    )
    return (
        '<div class="chapter-progress">'
        '<p class="wizard-kicker">Chapter progress</p>'
        f'<p class="chapter-percent"><span>{percent}%</span> of the chapter learned</p>'
        f'<div class="chapter-bar" role="progressbar" aria-label="Chapter progress" aria-valuemin="0" '
        f'aria-valuemax="100" aria-valuenow="{percent}">{segments}</div>'
        f'<div class="chapter-legend">{legend}</div>'
        f'<p class="chapter-summary">{understood} of {total} unit{"s" if total != 1 else ""} understood · '
        f'{days_checked} of {plan_days} day{"s" if plan_days != 1 else ""} checked</p>'
        '<p class="chapter-summary">Understood units count fully and units that need more evidence count '
        "half.</p>"
        "</div>"
    )


def render_chapter_progress(units: Sequence[StudyUnit], days_checked: int, plan_days: int) -> None:
    st.html(chapter_progress_html(chapter_progress(learner_state(units)), days_checked, plan_days))


def render_learning_status(units: Sequence[StudyUnit]) -> None:
    state = learner_state(units)
    with st.container(key="learning_status_panel"):
        st.caption("Each status comes from your answers and the topics you marked, not from the reading alone.")
        for evidence in state.units.values():
            st.html(
                f"<p><strong>{escape(evidence.unit.title)}</strong> · {STATUS_LABELS[evidence.status]}"
                f"<br><small>{escape(_evidence_text(evidence))}</small></p>"
            )
