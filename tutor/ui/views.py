"""The step bar above the page and the views beside the PDF: Outline, Initial quiz, Today, Plan,
Ask the tutor and Progress."""

from collections.abc import Sequence
from html import escape

import streamlit as st

from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.planning import StudyDay, StudyUnit
from tutor.ui import check, learner, navigation, quiz
from tutor.ui.citations import render_sources


STEPS = ("Upload", "Outline", "Mark & quiz", "Plan", "Study")


def render_steps(current: int, hint: str) -> None:
    """Where the learner is in the flow, and what to do next."""
    parts = []
    for number, name in enumerate(STEPS, start=1):
        if number < current:
            parts.append(f"✓ {name}")
        elif number == current:
            parts.append(f"**{number} · {name}**")
        else:
            parts.append(f"{number} · {name}")
    with st.container(key="steps"):
        st.markdown("  ›  ".join(parts))
        st.caption(f"Next: {hint}")


def unit_label(unit: StudyUnit, outline: Outline | None) -> str:
    """A unit's title, with the outline topics it covers when their names differ."""
    if outline is None:
        return unit.title
    topics = [outline.topics[n - 1].title for n in unit.topic_ids if 1 <= n <= len(outline.topics)]
    if not topics or topics == [unit.title]:
        return unit.title
    return f"{unit.title} (topics: {'; '.join(topics)})"


def render_outline_topics(result: Outline) -> None:
    st.caption("Check the topics you don't understand. The initial quiz asks about them first, "
               "and the plan gives them more time.")
    for index, topic in enumerate(result.topics):
        st.html(f"<h3>{escape(topic.title)}</h3><p>{escape(topic.summary)}</p>")
        learner.render_weak_topic_checkbox(index)
        render_sources(topic.source_ids, f"citation_{index}")


def _day_label(days: Sequence[StudyDay], done: set[int]):
    def label(number: int) -> str:
        if number > len(days):
            return f"{number}"
        review = any(a.kind == "review" for a in days[number - 1].assignments)
        return f"{number}{' ✓' if number in done else ''}{' ↻' if review else ''}"
    return label


def render_today(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    """The open study day: what to read and do, then the check."""
    if check.render_check(units, pages):
        return
    days = st.session_state.study_plan
    planned_days = st.session_state.planned_days
    done = check.completed_days()
    day = navigation.render_day_picker(max(planned_days, len(days)), _day_label(days, done))
    st.caption(f"{len(done)} of {len(days)} days checked · ✓ checked · ↻ review")
    st.subheader(f"Day {day} · checked" if day in done else f"Day {day}", anchor=False)
    if day > len(days):
        st.info("Optional review day. Choose an earlier day to revisit its reading or repeat a study task.")
        return
    for assignment in days[day - 1].assignments:
        unit = assignment.unit
        task = ""
        if assignment.kind != "read":
            task = f"<p><strong>Study task</strong><br>{escape(unit.activity)}</p>"
        st.html(f"<p><strong>{assignment.kind.capitalize()} · {escape(unit.title)}</strong>"
                f"<br>{escape(unit.objective)}</p>{task}")
        render_sources(assignment.source_ids, f"plan_citation_{day}_{unit.unit_id}")
    check.render_daily_check_button(day)


def _pages_text(source_ids: Sequence[str]) -> str:
    numbers = [int(source_id[1:]) for source_id in source_ids]
    if not numbers:
        return ""
    if numbers == list(range(numbers[0], numbers[-1] + 1)) and len(numbers) > 1:
        return f"{numbers[0]}–{numbers[-1]}"
    return ", ".join(map(str, numbers))


def render_plan_overview(units: Sequence[StudyUnit], result: Outline) -> None:
    """Every day at a glance, why the plan looks the way it does, and the outline."""
    days = st.session_state.study_plan
    planned_days = st.session_state.planned_days
    done = check.completed_days()
    to_go = sum(number not in done for number in range(1, len(days) + 1))
    with st.container(horizontal=True, key="plan_metrics"):
        st.metric("Goal", f"{planned_days} days")
        st.metric("Plan", f"{len(days)} days")
        st.metric("Checked", len(done))
        st.metric("To go", to_go)
    if len(days) > planned_days:
        st.warning(f"The plan now needs {len(days)} days, {len(days) - planned_days} more than your goal, "
                   "because reviews were added after your checks. Study at your own pace, or create the "
                   "plan again with more days.")
    weak = set(st.session_state.get("planned_weak", ()))
    if weak:
        st.caption("More time for: " + "; ".join(unit_label(u, result) for u in units if u.unit_id in weak))
    if st.session_state.get("quiz_summary"):
        st.caption(f"Initial quiz: {st.session_state.quiz_summary}")
    rows = [
        {"Day": day.number, "Status": "✓ checked" if day.number in done else "",
         "Study": " · ".join(f"{a.kind.capitalize()}: {a.unit.title}" for a in day.assignments),
         "Pages": _pages_text(tuple(dict.fromkeys(p for a in day.assignments for p in a.source_ids)))}
        for day in days
    ]
    if planned_days > len(days):
        rows += [{"Day": n, "Status": "", "Study": "Optional review", "Pages": ""}
                 for n in range(len(days) + 1, planned_days + 1)]
    st.dataframe(rows, hide_index=True, key="plan_table")
    check.render_plan_changes()
    with st.expander("Outline"):
        st.caption("Changes to the checked topics take effect when you create the plan again.")
        render_outline_topics(result)


def render_progress(units: Sequence[StudyUnit]) -> None:
    learner.render_learning_status(units)
    quiz.render_quiz_review()
