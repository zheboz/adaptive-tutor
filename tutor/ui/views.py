"""What the setup steps and the workspace pages show: the outline, a study day, the plan, progress."""

from collections.abc import Sequence
from html import escape

import streamlit as st

from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.planning import StudyDay, StudyUnit
from tutor.ui import cards, check, learner, quiz
from tutor.ui.citations import render_sources


def unit_label(unit: StudyUnit, outline: Outline | None) -> str:
    """A unit's title, with the outline topics it covers when their names differ."""
    if outline is None:
        return unit.title
    topics = [outline.topics[n - 1].title for n in unit.topic_ids if 1 <= n <= len(outline.topics)]
    if not topics or topics == [unit.title]:
        return unit.title
    return f"{unit.title} (topics: {'; '.join(topics)})"


def render_outline_topics(result: Outline) -> None:
    """Each topic with its summary, its pages and the box to mark it as not understood."""
    with st.container(key="outline_panel"):
        for index, topic in enumerate(result.topics):
            with st.container(border=True, key=f"topic_{index}"):
                st.html(f"<h4>{index + 1}. {escape(topic.title)}</h4><p>{escape(topic.summary)}</p>")
                with st.container(horizontal=True, vertical_alignment="center"):
                    learner.render_weak_topic_checkbox(index)
                    render_sources(topic.source_ids, f"citation_{index}")


def day_label(days: Sequence[StudyDay], done: set[int]):
    def label(number: int) -> str:
        if number > len(days):
            return f"Day {number}"
        review = any(a.kind == "review" for a in days[number - 1].assignments)
        return f"Day {number}{' ✓' if number in done else ''}{' ↻' if review else ''}"
    return label


def render_study_day(units: Sequence[StudyUnit], pages: Sequence[PdfPage], day: int) -> None:
    """The open study day: each unit's knowledge points, its task and pages, then the check."""
    days = st.session_state.study_plan
    done = check.completed_days()
    st.subheader(f"Day {day} · checked" if day in done else f"Day {day}", anchor=False)
    if day > len(days):
        st.info("Optional review day. Choose an earlier day to revisit its reading or repeat a study task.")
        return
    # Today's cards first, then the next day's and today's check questions, all in the background.
    cards.prefetch(days[day - 1], pages)
    if day < len(days):
        cards.prefetch(days[day], pages)
    check.prefetch_questions(units, pages, day)
    check.start_head_start(units, pages, day)
    number = 1
    for index, assignment in enumerate(days[day - 1].assignments):
        unit = assignment.unit
        # Laid out as a notebook page; the classes are styled in app.py's layout CSS.
        st.html(f'<div class="unit-heading"><span class="unit-kind">{assignment.kind.capitalize()}</span>'
                f'<p><strong>{escape(unit.title)}</strong></p>'
                f'<p class="unit-objective">{escape(unit.objective)}</p></div>')
        number = cards.render_card(assignment, pages, f"card_{day}_{index}", number)
        if assignment.kind != "read":
            st.html('<div class="study-task"><p class="study-task-title"><span class="study-task-box"></span>'
                    f"Study task</p><p>{escape(unit.activity)}</p></div>")
        with st.container(key=f"unit_pages_{day}_{index}", gap="xsmall"):
            st.caption("All pages for this unit:")
            render_sources(sorted(assignment.source_ids, key=lambda source_id: int(source_id[1:])),
                           f"plan_citation_{day}_{unit.unit_id}")
    check.render_daily_check_button(day)


def _pages_text(source_ids: Sequence[str]) -> str:
    numbers = [int(source_id[1:]) for source_id in source_ids]
    if not numbers:
        return ""
    if numbers == list(range(numbers[0], numbers[-1] + 1)) and len(numbers) > 1:
        return f"{numbers[0]}–{numbers[-1]}"
    return ", ".join(map(str, numbers))


def plan_rows(days: Sequence[StudyDay], planned_days: int, done: set[int] = frozenset()) -> list[dict]:
    rows = [
        {"Day": day.number, "Status": "✓ checked" if day.number in done else "",
         "Study": " · ".join(f"{a.kind.capitalize()}: {a.unit.title}" for a in day.assignments),
         "Pages": _pages_text(tuple(dict.fromkeys(p for a in day.assignments for p in a.source_ids)))}
        for day in days
    ]
    if planned_days > len(days):
        rows += [{"Day": n, "Status": "", "Study": "Optional review", "Pages": ""}
                 for n in range(len(days) + 1, planned_days + 1)]
    return rows


def more_time_text(units: Sequence[StudyUnit], weak: Sequence[str], outline: Outline | None) -> str:
    return "; ".join(unit_label(u, outline) for u in units if u.unit_id in set(weak))


def render_plan_overview(units: Sequence[StudyUnit], result: Outline) -> None:
    """Every day at a glance, and why the plan looks the way it does."""
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
                   "because reviews were added after your checks. Study at your own pace, or change the "
                   "plan below.")
    weak = st.session_state.get("planned_weak", ())
    if weak:
        st.caption("More time for: " + more_time_text(units, weak, result))
    if st.session_state.get("quiz_summary"):
        st.caption(f"Quick check: {st.session_state.quiz_summary}")
    st.dataframe(plan_rows(days, planned_days, done), hide_index=True, key="plan_table")
    check.render_plan_changes()


def render_progress(units: Sequence[StudyUnit]) -> None:
    learner.render_learning_status(units)
    quiz.render_quiz_review()
