import streamlit as st

import tutor.planning as planning
from tutor import llm
from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.ui import cards, check, learner, navigation, quiz, settings, tutor_chat, units, views
from tutor.ui.reader import READER_PANEL_HEIGHT, render_extracted_text, render_pdf_preview


def reset_preview() -> None:
    for key in (
        "pdf_pages", "pdf_page_number", "study_outline", "outline_error",
        "study_plan", "study_target_days", "planned_days", "passage_index",
        "learner_state", "planned_weak", "qa_session",
        *units.UNIT_KEYS, *cards.CARD_KEYS, *check.CHECK_KEYS, *quiz.QUIZ_KEYS, *navigation.NAVIGATION_KEYS,
    ):
        st.session_state.pop(key, None)
    learner.clear_weak_topics()


def render_plan_controls(result: outline.Outline) -> None:
    """Below the initial quiz results, and later in the Plan view to change the number of days."""
    with st.form("study_duration"):
        target_days = st.number_input(
            "Target duration (days)", min_value=1, value=st.session_state.get("planned_days") or 7, step=1,
            key="study_target_days", help="Choose how many days to spend on the full outline.",
        )
        st.caption("Topics you checked, and topics you answered wrong in the quiz, get more of the time.")
        create_plan = st.form_submit_button(
            "Create study plan", help="OpenAI prepares the study tasks once. Changing the duration reuses them.",
        )

    if create_plan:
        study_units = units.ensure_units(result)
        if study_units is None:
            return
        weak = learner.apply_plan_inputs(study_units)
        if st.session_state.get("planned_days") != target_days or st.session_state.get("planned_weak") != weak:
            st.session_state.pop("study_plan", None)
            st.session_state.planned_days = target_days
            st.session_state.planned_weak = weak
            check.reset_progress()
            navigation.open_day(1)
            navigation.show_view("Today")
            # The view bar and steps above the form were drawn before the plan existed.
            st.rerun()


def ensure_plan() -> None:
    study_units = st.session_state.study_units
    learner.learner_state(study_units)
    days = st.session_state.get("study_plan")
    # An open session can still hold a schedule made by the previous version.
    if not days or not hasattr(days[0], "assignments"):
        st.session_state.study_plan = planning.schedule_units(
            study_units, st.session_state.planned_days, st.session_state.get("planned_weak", ()),
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


def _readable(pages: list[PdfPage]) -> int:
    return sum(1 for page in pages if not page.error and page.text.strip())


def prepare_outline(pages: list[PdfPage], has_key: bool) -> outline.Outline | None:
    """Generate the outline as soon as the PDF and the learner's key are in; there is nothing to
    decide first. A failure waits for Try again rather than repeating on every interaction.

    Without a key the model call stops before any request, and the outline follows once the key
    is entered."""
    result = st.session_state.get("study_outline")
    if result is not None or not _readable(pages) or "outline_error" in st.session_state:
        return result
    try:
        with st.spinner("Generating study outline…"):
            result = outline.generate_outline(pages)
    except (LLMError, outline.OutlineError) as error:
        if has_key:
            st.session_state.outline_error = str(error)
        return None
    st.session_state.study_outline = result
    return result


def render_outline_status(pages: list[PdfPage], has_key: bool) -> None:
    """Why there is no outline yet, in the view panel."""
    if not _readable(pages):
        st.warning("This PDF has no readable text, so no outline can be made from it. Try a PDF "
                   "with selectable text.")
    elif not has_key:
        st.info("Enter your OpenAI API key at the top of the page. The outline is generated as soon as it is in.")
    elif "outline_error" in st.session_state:
        st.error(st.session_state.outline_error)
        st.button("Try again", key="outline_retry", type="primary",
                  on_click=lambda: st.session_state.pop("outline_error", None))
    if 0 < _readable(pages) < len(pages):
        st.caption(f"Pages with readable text: {_readable(pages)} of {len(pages)}.")


def current_step(result: outline.Outline | None, has_plan: bool, has_key: bool) -> tuple[int, str]:
    if result is None:
        if not has_key:
            return 2, "enter your OpenAI API key at the top; the outline is then generated for you."
        return 2, "the outline could not be generated; see the panel on the right."
    if not quiz.done():
        if quiz.started():
            return 3, "answer every question of the initial quiz, then submit."
        return 3, ("check the topics you don't understand in the Outline, then select Start initial quiz "
                   "(or Skip the quiz) at the end of the outline.")
    if not has_plan:
        return 4, "set the number of days below the quiz results and select Create study plan."
    return 5, "study today's material, then select Check my understanding."


# The view bar stays at the top of the view panel; the view's content scrolls below it.
VIEW_CONTENT_HEIGHT = READER_PANEL_HEIGHT - 80


def render_views(result: outline.Outline | None, pages: list[PdfPage], has_plan: bool, has_key: bool) -> None:
    """The panel beside the PDF: a view bar and the selected view, in one panel as tall as the PDF's,
    so the two line up. Each view keeps the PDF in sight, so its page links can be followed."""
    study_units = st.session_state.get("study_units")
    if result is None:
        options = ["Outline"]
    elif has_plan:
        options = ["Today", "Plan", "Progress"]
    else:
        options = ["Outline", *(["Initial quiz"] if quiz.started() else []), *(["Progress"] if study_units else [])]
    panels = {"Outline": "outline_panel", "Initial quiz": "quiz_panel", "Today": "plan_panel",
              "Plan": "plan_overview_panel", "Progress": "progress_panel"}
    with st.container(height=READER_PANEL_HEIGHT, border=True, key="view_panel"):
        view = navigation.render_view_bar(options)
        with st.container(height=VIEW_CONTENT_HEIGHT, border=False, key=panels[view]):
            if result is None:
                render_outline_status(pages, has_key)
            elif view == "Outline":
                views.render_outline_topics(result)
                quiz.render_start(result, pages)
            elif view == "Initial quiz":
                quiz.render_quiz(result, study_units, pages)
                if quiz.done():
                    render_plan_controls(result)
            elif view == "Today":
                views.render_today(study_units, pages)
            elif view == "Plan":
                views.render_plan_overview(study_units, result)
                with st.expander("Change the number of days"):
                    render_plan_controls(result)
            else:
                views.render_progress(study_units)


# The PDF and view panels fill the window below the top bar and the step bar; the numbers are the
# space those take, the PDF's page controls and the view bar. Python's pixel heights are the fallback.
_LAYOUT_CSS = """
<style>
[data-testid="stMainBlockContainer"] {
    padding-inline: clamp(0.75rem, 2vw, 1.5rem);
    padding-top: 4.25rem;
}
:root { --panel-height: max(460px, calc(100vh - 290px)); }
.st-key-pdf_preview_panel, .st-key-view_panel { height: var(--panel-height) !important; }
.st-key-pdf_page_view { height: calc(var(--panel-height) - 72px) !important; }
.st-key-outline_panel, .st-key-quiz_panel, .st-key-plan_panel, .st-key-plan_overview_panel,
.st-key-progress_panel { height: calc(var(--panel-height) - 80px) !important; }
/* A compact upload box in the top bar. */
.st-key-topbar [data-testid="stFileUploaderDropzone"] { padding-block: 0.4rem; }
.st-key-topbar [data-testid="stFileUploaderDropzoneInstructions"] small { display: none; }
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
"""


def render_top_bar():
    """The learner's key, the model and the PDF, in one bar across the top of the page."""
    with st.container(key="topbar", border=True):
        key_column, model_column, upload_column = st.columns([4, 3, 5], vertical_alignment="top")
        with key_column:
            api_key = settings.render_key()
        with model_column:
            model = settings.render_model()
        with upload_column:
            upload = st.file_uploader("PDF to study", type=["pdf"], on_change=reset_preview)
    return api_key, model, upload


def main() -> None:
    st.set_page_config(page_title="Adaptive Tutor", layout="wide", initial_sidebar_state="collapsed")
    st.html(_LAYOUT_CSS)
    api_key, model, upload = render_top_bar()
    # Every model call in this run, including those in background threads, uses this session's
    # key and model.
    with llm.using(api_key, model):
        render_study(upload, has_key=api_key is not None)


def render_study(upload, has_key: bool) -> None:
    if upload is None:
        views.render_steps(1, "upload a PDF at the top.")
        st.info("Upload a PDF at the top to begin.")
        return

    if "pdf_pages" not in st.session_state:
        try:
            with st.spinner("Reading PDF…"):
                st.session_state.pdf_pages = read_pdf_pages(upload.getvalue())
        except PdfInputError as error:
            st.error(str(error))
            return

    pages = st.session_state.pdf_pages
    result = prepare_outline(pages, has_key)
    if result is not None:
        # Plan the units while the learner reads the outline, so the quiz starts sooner.
        units.start_planning(result)

    has_plan = st.session_state.get("planned_days") is not None
    if has_plan:
        ensure_plan()
    views.render_steps(*current_step(result, has_plan, has_key))
    preview_column, learning_column = st.columns([3, 2], gap=12)
    # Each column is one panel of the same height, so the two line up.
    with preview_column:
        page = render_pdf_preview(upload, pages)
    with learning_column:
        render_views(result, pages, has_plan, has_key)
    # Asking the tutor needs only the PDF, so it is always available, right below both panels.
    st.header("Ask the tutor")
    tutor_chat.render_tutor_chat(pages, tutor_context(result), 360)
    render_extracted_text(page)


if __name__ == "__main__":
    main()
