"""Setup, one step at a time, before studying starts: Material, Topics, Quick check, Plan.

Each step fills the page's width and ends with the button to the next one. The step bar above
shows where the learner is and opens any step already reached. Page links open the page in a
window, since the PDF reader belongs to the study workspace.
"""

import streamlit as st

import tutor.planning as planning
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.ui import check, learner, material, navigation, quiz, settings, tutor_chat, views
from tutor.ui.navigation import SETUP_STEPS, go_to_step
from tutor.ui.units import ensure_units


def reachable() -> int:
    """The furthest step the learner can open."""
    if material.pages() is None:
        return 1
    if quiz.done():
        return 4
    if quiz.started():
        return 3
    return 2


def _completed(step: int) -> bool:
    return {1: material.pages() is not None and settings.current_key() is not None,
            2: quiz.started(), 3: quiz.done()}.get(step, False)


def current() -> int:
    step = min(navigation.current_step(), reachable())
    go_to_step(step)
    return step


def render_step_bar(step: int) -> None:
    furthest = reachable()
    with st.container(key="steps", horizontal=True, gap="small"):
        for number, name in enumerate(SETUP_STEPS, start=1):
            done = _completed(number) and number != step
            st.button(f"✓ {name}" if done else f"{number} · {name}", key=f"step_{number}",
                      type="primary" if number == step else "secondary", disabled=number > furthest,
                      on_click=go_to_step, args=(number,))


def render(step: int) -> None:
    # The steps are tabs on top of a sheet of paper that holds the open step (see app.py's layout CSS).
    with st.container(key="wizard"):
        render_step_bar(step)
        with st.container(key="wizard_sheet"):
            st.html(f'<p class="wizard-kicker">Step {step} of {len(SETUP_STEPS)}</p>')
            if step == 1:
                _material()
                return
            pages = material.pages()
            result = material.prepare_outline(pages, settings.current_key() is not None)
            if step == 2:
                _topics(pages, result)
            elif step == 3:
                _quick_check(pages, result)
            else:
                _plan(result)


def _back(step: int) -> None:
    st.button("← Back", key="wizard_back", on_click=go_to_step, args=(step,))


def _material() -> None:
    st.header("Start with your material", anchor=False)
    st.caption("The tutor reads your PDF, lists its topics, checks what you already know, and plans your "
               "study days from it.")
    with st.container(border=True, key="material_settings"):
        st.markdown("**The OpenAI model**")
        settings.render_settings(horizontal=True)
    with st.container(border=True, key="material_upload"):
        st.markdown("**The PDF to study**")
        st.file_uploader("PDF to study", type=["pdf"], key=material.UPLOAD_KEY, on_change=material.keep_upload,
                         label_visibility="collapsed")
        pages = material.pages()
        if st.session_state.get("pdf_error"):
            st.error(st.session_state.pdf_error)
        elif pages is not None:
            name = st.session_state.pdf_name
            st.success(f"{name} · {len(pages)} page{'s' if len(pages) != 1 else ''}, "
                       f"{material.readable(pages)} with readable text")
            # The topics are listed in the background while the learner finishes this step.
            material.start_outline(pages, settings.current_key() is not None)
            if material.outline_running():
                st.caption("The tutor has started reading it and listing its topics.")
            elif material.current_outline() is not None:
                st.caption("Its topics are ready.")
            if st.session_state.get(material.UPLOAD_KEY) is None:
                st.caption("Choose another PDF above to replace it.")
    has_key = settings.current_key() is not None
    st.button("Next: review the topics →", key="material_next", type="primary",
              disabled=not has_key or pages is None, on_click=go_to_step, args=(2,))
    if has_key and pages is None:
        st.caption("To continue, add a PDF.")


def _topics(pages: list[PdfPage], result: Outline | None) -> None:
    st.header("Which topics are unclear to you?", anchor=False)
    if result is None and material.outline_running():
        material.render_outline_progress(len(pages))
        _back(1)
        return
    if result is None:
        material.render_outline_status(pages, settings.current_key() is not None)
        _back(1)
        return
    st.caption("Check every topic you don't understand yet: the quick check asks about them first, and the "
               "plan gives them more time. Page links show the page.")
    views.render_outline_topics(result)

    checked = learner.weak_topics_in_order()
    with st.container(border=True, key="quiz_start"):
        st.markdown("**Next: a quick check**")
        if quiz.done() and not quiz.skipped():
            st.caption(f"Done: {st.session_state.get('quiz_summary', '')} Topics you check or uncheck now still "
                       "change the plan.")
        elif quiz.started() and not quiz.skipped():
            st.caption("You have started the quick check.")
        elif checked:
            st.caption(f"One question for each topic you checked ({len(checked)}), in the order you checked "
                       "them. You see each answer right away.")
        else:
            st.caption("No topic checked: the quick check asks up to 3 questions from across the material.")
    with st.container(horizontal=True, key="topics_actions"):
        _back(1)
        if quiz.started() and not quiz.skipped():
            st.button("Continue to the plan →" if quiz.done() else "Continue the quick check →",
                      key="topics_next", type="primary", on_click=go_to_step, args=(4 if quiz.done() else 3,))
            start = skip = False
        else:
            start = st.button("Start the quick check →", key="start_initial_quiz", type="primary")
            skip = st.button("Skip to the plan", key="skip_initial_quiz",
                             help="No questions. Topics you checked still get more time.")
    if start and quiz.start(result, pages):
        go_to_step(3)
        st.rerun()
    if skip and quiz.skip(result):
        go_to_step(4)
        st.rerun()

    with st.expander("Ask the tutor about this material"):
        tutor_chat.render_tutor_chat(pages, result, 320)


def _quick_check(pages: list[PdfPage], result: Outline | None) -> None:
    st.header("Quick check", anchor=False)
    if result is None or "study_units" not in st.session_state:
        material.render_outline_status(pages, settings.current_key() is not None)
        _back(2)
        return
    st.caption("A few questions from your own pages show what you already know. Each answer is shown right "
               "away, with the passage that supports it.")
    with st.container(key="quiz_panel"):
        quiz.render_quiz(result, st.session_state.study_units, pages)
    with st.container(horizontal=True, key="quiz_actions"):
        _back(2)
        if quiz.done():
            st.button("Continue to the plan →", key="quiz_continue", type="primary", on_click=go_to_step, args=(4,))


def _start_studying(days: int, weak: tuple[str, ...], plan: tuple) -> None:
    st.session_state.planned_days = days
    st.session_state.planned_weak = weak
    st.session_state.study_plan = plan
    check.reset_progress()
    navigation.open_day(1)
    navigation.show_page("Today")


def _plan(result: Outline | None) -> None:
    st.header("Plan your study days", anchor=False)
    back = 3 if quiz.started() and not quiz.skipped() else 2
    units = ensure_units(result) if result is not None else None
    if units is None:
        with st.container(horizontal=True):
            _back(back)
            st.button("Try again", key="plan_retry", type="primary")
        return
    weak = learner.apply_plan_inputs(units)
    days = st.number_input(
        "How many days do you want to spend on this material?", min_value=1, max_value=365,
        value=st.session_state.get("draft_days", 7), step=1, key="study_target_days",
    )
    st.session_state.draft_days = days
    plan = planning.schedule_units(units, days, weak)
    summary = f"{len(units)} learning unit{'s' if len(units) != 1 else ''} over {days} day{'s' if days != 1 else ''}."
    if weak:
        summary += " More time for: " + views.more_time_text(units, weak, result) + "."
    st.caption(summary)
    st.html(views.plan_html(plan, days))
    st.caption("You can change the number of days later on the Plan page. After each study day, a check "
               "may add a review at the end of the plan.")
    with st.container(horizontal=True, key="plan_actions"):
        _back(back)
        st.button("Start studying →", key="start_studying", type="primary", on_click=_start_studying,
                  args=(days, weak, plan))
