import streamlit as st

import tutor.planning as planning
from tutor import llm
from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.ui import check, learner, navigation, quiz, settings, tutor_chat, views
from tutor.ui.reader import READER_PANEL_HEIGHT, render_extracted_text, render_pdf_preview


def reset_preview() -> None:
    for key in (
        "pdf_pages", "pdf_page_number", "study_outline", "unit_plan", "study_units",
        "study_plan", "study_target_days", "planned_days", "passage_index",
        "learner_state", "planned_weak", "qa_session",
        *check.CHECK_KEYS, *quiz.QUIZ_KEYS, *navigation.NAVIGATION_KEYS,
    ):
        st.session_state.pop(key, None)
    learner.clear_weak_topics()


def ensure_units(result: outline.Outline) -> tuple[planning.StudyUnit, ...] | None:
    """Build the study units once. They depend only on the outline, not on the number of days."""
    # Retire schedules from sessions opened before model-planned units were introduced.
    if "study_units" in st.session_state and "unit_plan" not in st.session_state:
        for key in ("study_units", "study_plan", "planned_days"):
            st.session_state.pop(key, None)
    try:
        if "unit_plan" not in st.session_state:
            with st.spinner("Planning the learning units…"):
                st.session_state.unit_plan = planning.plan_units(result)
        if "study_units" not in st.session_state:
            with st.spinner("Preparing study tasks for the planned units…"):
                st.session_state.study_units = planning.build_study_units(result, st.session_state.unit_plan)
    except (LLMError, planning.PlanningError) as error:
        st.error(str(error))
        return None
    return st.session_state.study_units


def render_plan_controls(result: outline.Outline) -> None:
    """Shown once the initial quiz has its results."""
    with st.form("study_duration"):
        target_days = st.number_input(
            "Target duration (days)", min_value=1, value=7, step=1, key="study_target_days",
            help="Choose how many days to spend on the full outline.",
        )
        st.caption("Topics you checked, and topics you answered wrong in the quiz, get more of the time.")
        create_plan = st.form_submit_button(
            "Create study plan", help="OpenAI prepares the study tasks once. Changing the duration reuses them.",
        )

    if create_plan:
        units = ensure_units(result)
        if units is None:
            return
        weak = learner.apply_plan_inputs(units)
        if st.session_state.get("planned_days") != target_days or st.session_state.get("planned_weak") != weak:
            st.session_state.pop("study_plan", None)
            st.session_state.planned_days = target_days
            st.session_state.planned_weak = weak
            check.reset_progress()
            navigation.open_day(1)
            navigation.show_view("Today")
            # The quiz step above the form was drawn before the plan existed.
            st.rerun()


def ensure_plan() -> None:
    units = st.session_state.study_units
    learner.learner_state(units)
    days = st.session_state.get("study_plan")
    # An open session can still hold a schedule made by the previous version.
    if not days or not hasattr(days[0], "assignments"):
        st.session_state.study_plan = planning.schedule_units(
            units, st.session_state.planned_days, st.session_state.get("planned_weak", ()),
        )


def tutor_context(result: outline.Outline | None) -> dict:
    """What the tutor should know about the learner when answering a question."""
    topics = result.topics if result is not None else []
    context: dict = {"weak_topics": [
        topics[number - 1].title for number in sorted(learner.weak_topic_numbers()) if number <= len(topics)
    ]}
    days = st.session_state.get("study_plan")
    number = navigation.current_day()
    if days and number <= len(days):
        context["study_day"] = number
        context["todays_units"] = [
            {"title": a.unit.title, "objective": a.unit.objective, "pages": list(a.source_ids)}
            for a in days[number - 1].assignments
        ]
    return context


def prepare_outline(pages: list[PdfPage]) -> outline.Outline | None:
    result = st.session_state.get("study_outline")
    if result is not None:
        return result
    readable_count = sum(1 for page in pages if not page.error and page.text.strip())
    controls = st.empty()
    with controls.container():
        st.caption("Generate an outline from this PDF’s readable text using OpenAI.")
        if readable_count < len(pages):
            st.caption(f"Pages with readable text: {readable_count} of {len(pages)}.")
        if not st.button("Generate outline", type="primary", disabled=readable_count == 0):
            return None
    try:
        with st.spinner("Generating study outline…"):
            result = outline.generate_outline(pages)
    except (LLMError, outline.OutlineError) as error:
        st.error(str(error))
        return None
    st.session_state.study_outline = result
    controls.empty()
    return result


def current_step(result: outline.Outline | None, has_plan: bool) -> tuple[int, str]:
    if result is None:
        return 2, "select Generate outline in the sidebar."
    if not quiz.done():
        if quiz.started():
            return 3, "answer every question of the initial quiz, then submit."
        return 3, ("check the topics you don't understand in the Outline view, then select "
                   "Start initial quiz in the sidebar.")
    if not has_plan:
        return 4, "set the number of days in the sidebar and select Create study plan."
    return 5, "study today's material, then select Check my understanding."


# The view bar stays at the top of the view panel; the view's content scrolls below it.
VIEW_CONTENT_HEIGHT = READER_PANEL_HEIGHT - 90


def render_views(result: outline.Outline | None, pages: list[PdfPage], has_plan: bool) -> None:
    """The panel beside the PDF: a view bar and the selected view, in one panel as tall as the PDF's,
    so the two line up. Each view keeps the PDF in sight, so its page links can be followed."""
    units = st.session_state.get("study_units")
    if result is None:
        options = ["Outline"]
    elif has_plan:
        options = ["Today", "Plan", "Progress"]
    else:
        options = ["Outline", *(["Initial quiz"] if quiz.started() else []), *(["Progress"] if units else [])]
    panels = {"Outline": "outline_panel", "Initial quiz": "quiz_panel", "Today": "plan_panel",
              "Plan": "plan_overview_panel", "Progress": "progress_panel"}
    with st.container(height=READER_PANEL_HEIGHT, border=True, key="view_panel"):
        view = navigation.render_view_bar(options)
        with st.container(height=VIEW_CONTENT_HEIGHT, border=False, key=panels[view]):
            if result is None:
                st.caption("Select Generate outline in the sidebar to see the topics and their source pages.")
            elif view == "Outline":
                views.render_outline_topics(result)
            elif view == "Initial quiz":
                quiz.render_quiz(result, units, pages)
            elif view == "Today":
                views.render_today(units, pages)
            elif view == "Plan":
                views.render_plan_overview(units, result)
            else:
                views.render_progress(units)


def main() -> None:
    st.set_page_config(page_title="Study materials · Adaptive Tutor", layout="wide")
    st.html("""
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-inline: clamp(0.75rem, 2vw, 1.5rem);
            padding-top: 3rem;
        }
        /* Keep the arrow buttons' text labels accessible to screen readers. */
        .st-key-pdf_page_controls button [data-testid="stMarkdownContainer"] {
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
        }
        </style>
    """)
    st.title("Study materials")
    with st.sidebar:
        st.header("Study setup")
        api_key, model = settings.render_settings()
        upload = st.file_uploader("Upload a PDF", type=["pdf"], on_change=reset_preview)
    # Every model call in this run, including those in background threads, uses this session's
    # key and model (or the app's when the learner gave none).
    with llm.using(api_key, model):
        render_study(upload)


def render_study(upload) -> None:
    if upload is None:
        views.render_steps(1, "upload a PDF in the sidebar.")
        st.info("Upload a PDF in the sidebar to begin.")
        return

    if "pdf_pages" not in st.session_state:
        try:
            with st.spinner("Reading PDF…"):
                st.session_state.pdf_pages = read_pdf_pages(upload.getvalue())
        except PdfInputError as error:
            st.error(str(error))
            return

    pages = st.session_state.pdf_pages
    with st.sidebar:
        result = prepare_outline(pages)
        if result is not None:
            quiz.render_start(result, pages, ensure_units)
            if quiz.done():
                render_plan_controls(result)

    has_plan = st.session_state.get("planned_days") is not None
    if has_plan:
        ensure_plan()
    views.render_steps(*current_step(result, has_plan))
    preview_column, learning_column = st.columns([3, 2], gap=12)
    # Each column is one panel of the same height, so the two line up.
    with preview_column:
        page = render_pdf_preview(upload, pages)
    with learning_column:
        render_views(result, pages, has_plan)
    # Asking the tutor needs only the PDF, so it is always available, right below both panels.
    st.header("Ask the tutor")
    tutor_chat.render_tutor_chat(pages, tutor_context(result), 360)
    render_extracted_text(page)


if __name__ == "__main__":
    main()
