"""The study workspace, once the plan exists: Today, Plan and Progress.

Today puts the PDF beside the open day's material, or beside the chat. The daily check takes the
whole width and hides the PDF, so answers come from what was learned; its page links open a window.
Plan and Progress take the whole width too.
"""

from collections.abc import Sequence

import streamlit as st

import tutor.planning as planning
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.ui import check, learner, navigation, tutor_chat, views
from tutor.ui.citations import links_open_in_reader
from tutor.ui.reader import READER_PANEL_HEIGHT, render_pdf_preview


# The panel's own row of buttons sits above its content.
_CONTENT_HEIGHT = READER_PANEL_HEIGHT - 80


def ensure_plan() -> None:
    study_units = st.session_state.study_units
    learner.learner_state(study_units)
    days = st.session_state.get("study_plan")
    # An open session can still hold a schedule made by the previous version.
    if not days or not hasattr(days[0], "assignments"):
        st.session_state.study_plan = planning.schedule_units(
            study_units, st.session_state.planned_days, st.session_state.get("planned_weak", ()),
        )


def render(page: str, result: Outline, pages: Sequence[PdfPage], pdf: tuple[bytes, str, str]) -> None:
    ensure_plan()
    units = st.session_state.study_units
    if page == "Today":
        _today(units, result, pages, pdf)
    elif page == "Plan":
        with st.container(key="plan_overview_panel"):
            views.render_plan_overview(units, result)
            _change_plan(units, result)
    else:
        with st.container(key="progress_panel"):
            views.render_progress(units)


def _today(units, result: Outline, pages: Sequence[PdfPage], pdf: tuple[bytes, str, str]) -> None:
    if check.active():
        with st.container(key="check_panel"):
            check.render_check(units, pages)
        return
    days = st.session_state.study_plan
    done = check.completed_days()
    with st.container(key="day_strip", horizontal=True, vertical_alignment="center"):
        day = navigation.render_day_picker(max(st.session_state.planned_days, len(days)),
                                           views.day_label(days, done))
        st.caption(f"{len(done)} of {len(days)} days checked · ✓ checked · ↻ review")
    reader_column, panel_column = st.columns(2, gap="medium")
    with reader_column:
        render_pdf_preview(*pdf[:2], pages)
    with panel_column, st.container(height=READER_PANEL_HEIGHT, border=True, key="today_panel"):
        panel = navigation.render_panel_picker()
        with links_open_in_reader():
            if panel == "Study":
                with st.container(height=_CONTENT_HEIGHT, border=False, key="study_panel"):
                    views.render_study_day(units, pages, day)
            else:
                tutor_chat.render_tutor_chat(pages, result, _CONTENT_HEIGHT - 70)


def _change_plan(units, result: Outline) -> None:
    with st.expander("Change the plan"):
        st.caption("Check or uncheck topics, set the number of days, then update the plan. Checks and plan "
                   "changes so far start again.")
        views.render_outline_topics(result)
        with st.form("study_duration"):
            target_days = st.number_input(
                "Target duration (days)", min_value=1, max_value=365, value=st.session_state.planned_days,
                step=1, key="study_target_days",
            )
            update = st.form_submit_button("Update plan", type="primary")
    if update:
        weak = learner.apply_plan_inputs(units)
        if st.session_state.planned_days != target_days or st.session_state.get("planned_weak") != weak:
            st.session_state.planned_days = target_days
            st.session_state.planned_weak = weak
            st.session_state.study_plan = planning.schedule_units(units, target_days, weak)
            check.reset_progress()
            navigation.open_day(1)
        navigation.show_page("Today")
        st.rerun()
