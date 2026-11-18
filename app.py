from html import escape

import streamlit as st

import tutor.planning as planning
from tutor.assessment import practice_ui
from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.citations import render_sources
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.materials.reader import READER_PANEL_HEIGHT, render_extracted_text, render_pdf_preview


def reset_preview() -> None:
    for key in (
        "pdf_pages", "pdf_page_number", "study_outline", "unit_plan", "study_units",
        "study_plan", "study_target_days", "planned_days", "study_day",
        "practice_index", "practice_sets", "practice_answers",
    ):
        st.session_state.pop(key, None)


def render_plan_controls(result: outline.Outline) -> None:
    # Retire schedules from sessions opened before model-planned units were introduced.
    if "study_units" in st.session_state and "unit_plan" not in st.session_state:
        for key in ("study_units", "study_plan", "planned_days", "study_day"):
            st.session_state.pop(key, None)
    with st.form("study_duration"):
        target_days = st.number_input(
            "Target duration (days)", min_value=1, value=7, step=1, key="study_target_days",
            help="Choose how many days to spend on the full outline.",
        )
        create_plan = st.form_submit_button(
            "Create study plan", help="OpenAI prepares the study tasks once. Changing the duration reuses them."
        )

    if create_plan:
        try:
            if "unit_plan" not in st.session_state:
                with st.spinner("Planning the learning units…"):
                    st.session_state.unit_plan = planning.plan_units(result)
            if "study_units" not in st.session_state:
                with st.spinner("Preparing study tasks for the planned units…"):
                    st.session_state.study_units = planning.build_study_units(result, st.session_state.unit_plan)
        except (LLMError, planning.PlanningError) as error:
            st.error(str(error))
            return
        if st.session_state.get("planned_days") != target_days:
            st.session_state.pop("study_plan", None)
            st.session_state.planned_days = target_days
            st.session_state.study_day = 1


def render_study_plan(pages: list[PdfPage], document_id: str) -> None:
    planned_days = st.session_state.planned_days
    units = st.session_state.study_units
    days = st.session_state.get("study_plan")
    # An open session can still hold a schedule made by the previous version.
    if not days or not hasattr(days[0], "assignments"):
        days = planning.schedule_units(units, planned_days)
        st.session_state.study_plan = days
    st.text(f"{planned_days}-day plan · {len(units)} study unit{'s' if len(units) != 1 else ''}")
    if planned_days > len(days):
        start = len(days) + 1
        label = f"Day {start}" if start == planned_days else f"Days {start}–{planned_days}"
        st.caption(f"{label} · optional review")

    number = st.number_input("Study day", min_value=1, max_value=planned_days, step=1, key="study_day")
    st.subheader(f"Day {number}")
    if number > len(days):
        st.info("Optional review day. Choose an earlier day to revisit its reading or repeat a study task.")
        return
    assignments = days[number - 1].assignments
    scopes = [(practice_ui.practice_key(document_id, assignment), assignment) for assignment in assignments]
    practice_ui.prepare_daily_practice(scopes, pages)
    for scope, assignment in scopes:
        unit = assignment.unit
        action = assignment.kind.capitalize()
        task = ""
        if assignment.kind != "read":
            task = f"<p><strong>Study task</strong><br>{escape(unit.activity)}</p>"
        st.html(
            f"<p><strong>{action} · {escape(unit.title)}</strong><br>{escape(unit.objective)}</p>{task}"
        )
        render_sources(assignment.source_ids, f"plan_citation_{number}_{unit.unit_id}")
        practice_ui.render_questions(scope)


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


def render_outline(result: outline.Outline | None, height: int) -> None:
    st.header("Study outline")
    with st.container(height=height, border=True, key="outline_panel"):
        if result is None:
            st.caption("Select Generate outline in the sidebar to see the topics and their source pages.")
            return
        for index, topic in enumerate(result.topics):
            st.html(f"<h3>{escape(topic.title)}</h3><p>{escape(topic.summary)}</p>")
            render_sources(topic.source_ids, f"citation_{index}")


def main() -> None:
    st.set_page_config(page_title="Study materials · Adaptive Tutor", layout="wide")
    st.html("""
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-inline: clamp(0.75rem, 2vw, 1.5rem);
            padding-top: 4rem;
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
        upload = st.file_uploader("Upload a PDF", type=["pdf"], on_change=reset_preview)
    if upload is None:
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
            render_plan_controls(result)

    has_plan = st.session_state.get("planned_days") is not None
    preview_column, learning_column = st.columns([3, 2] if has_plan else 2, gap=12)
    with preview_column:
        page = render_pdf_preview(upload, pages)
    with learning_column:
        if has_plan:
            st.header("Daily study plan")
            with st.container(height=READER_PANEL_HEIGHT, border=True, key="plan_panel"):
                render_study_plan(pages, upload.file_id)
        else:
            render_outline(result, READER_PANEL_HEIGHT)
    if has_plan:
        render_outline(result, 320)
    render_extracted_text(page)


if __name__ == "__main__":
    main()
