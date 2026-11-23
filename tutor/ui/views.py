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


def day_states(days: Sequence[StudyDay], done: set[int], last_day: int) -> list[str]:
    """How each day from 1 to `last_day` stands: checked, a review still to do, the day to study next,
    a day still to come, or an optional day past the plan."""
    next_day = next((day.number for day in days if day.number not in done), None)
    states = []
    for number in range(1, last_day + 1):
        if number > len(days):
            states.append("optional")
        elif number in done:
            states.append("checked")
        elif any(a.kind == "review" for a in days[number - 1].assignments):
            states.append("review")
        else:
            states.append("next" if number == next_day else "todo")
    return states


def day_strip_html(states: Sequence[str]) -> str:
    """Colors each day's tab by its state, as the plan's timeline does, and says what the colors mean.
    The tabs cannot carry a class of their own, so they are picked by position."""
    rules = "".join(
        f'.st-key-day_strip [role="radiogroup"] > button:nth-child({number}) {{ {_DAY_TAB_STYLES[state]} }}'
        for number, state in enumerate(states, start=1) if state != "todo"
    )
    legend = "".join(
        f'<span class="day-legend-item"><span class="day-legend-swatch {state}"></span>{name}</span>'
        for state, name in (("checked", "Checked"), ("next", "Up next"), ("review", "Review"))
    )
    return f'<style>{rules}</style><div class="day-legend">{legend}</div>'


_DAY_TAB_STYLES = {
    "checked": "background: #EAF6EF; color: #1F6B3D; border-left-color: #2E9E5B !important;",
    "next": "background: #FFF8DC; border-left-color: #F2C94C !important;",
    "review": "background: #FFF1E3; color: #A25A12; border-left-color: #E08A2E !important;",
    "optional": "background: transparent; color: #6B7485; border-style: dashed !important; border-left-style: solid !important;",
}


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
    """The page numbers in order, runs of consecutive pages joined: 4–13, 36–40."""
    runs: list[list[int]] = []
    for number in sorted({int(source_id[1:]) for source_id in source_ids}):
        if runs and number == runs[-1][1] + 1:
            runs[-1][1] = number
        else:
            runs.append([number, number])
    return ", ".join(f"{first}–{last}" if last > first else str(first) for first, last in runs)


def plan_html(days: Sequence[StudyDay], planned_days: int, done: set[int] = frozenset(),
              next_day: int | None = None) -> str:
    """Every day of the plan down a timeline: what it studies and its pages, checked days in green and
    reviews still to do in orange, the day to study next in yellow. Styled in app.py's layout CSS."""
    items = []
    for day in days:
        review = any(a.kind == "review" for a in day.assignments)
        state = ("checked" if day.number in done else "review" if review
                 else "next" if day.number == next_day else "")
        status = {"checked": '<span class="plan-day-status">✓ Checked</span>',
                  "next": '<span class="plan-day-status">Up next</span>'}.get(state, "")
        units = "".join(
            f'<p class="plan-unit"><span class="plan-kind {a.kind}">{a.kind.capitalize()}</span>'
            f'<span class="plan-unit-title">{escape(a.unit.title)}</span></p>'
            for a in day.assignments
        )
        pages = _pages_text(tuple(p for a in day.assignments for p in a.source_ids))
        pages = f'<p class="plan-day-pages">Pages {pages}</p>' if pages else ""
        items.append(_plan_day(day.number, state, f"{status}</div>{units}{pages}"))
    items += [_plan_day(n, "optional", '</div><p class="plan-unit">Optional review</p>')
              for n in range(len(days) + 1, planned_days + 1)]
    return f'<ol class="plan-days">{"".join(items)}</ol>'


def _plan_day(number: int, state: str, rest: str) -> str:
    marker = "✓" if state == "checked" else str(number)
    return (f'<li class="plan-day {state}" data-day="{number}"><span class="plan-day-dot">{marker}</span>'
            f'<div class="plan-day-card"><div class="plan-day-head"><span class="plan-day-title">Day {number}'
            f"</span>{rest}</div></li>")


def more_time_text(units: Sequence[StudyUnit], weak: Sequence[str], outline: Outline | None) -> str:
    return "; ".join(unit_label(u, outline) for u in units if u.unit_id in set(weak))


def render_plan_overview(units: Sequence[StudyUnit], result: Outline) -> None:
    """Every day at a glance, and why the plan looks the way it does."""
    days = st.session_state.study_plan
    planned_days = st.session_state.planned_days
    done = check.completed_days()
    to_go = sum(number not in done for number in range(1, len(days) + 1))
    st.html('<p class="wizard-kicker">Your study plan</p>')
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
    next_day = next((day.number for day in days if day.number not in done), None)
    st.html(plan_html(days, planned_days, done, next_day))
    check.render_plan_changes()


def render_progress(units: Sequence[StudyUnit]) -> None:
    """The whole chapter's progress in one bar, then each unit's status and the quick check."""
    days = st.session_state.study_plan
    learner.render_chapter_progress(units, len(check.completed_days()), len(days))
    learner.render_learning_status(units)
    quiz.render_quiz_review()
