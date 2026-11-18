from collections.abc import Sequence
from html import escape

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

import tutor.planning as planning
from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages


def reset_preview() -> None:
    for key in (
        "pdf_pages", "pdf_page_number", "study_outline", "unit_plan", "study_units",
        "study_plan", "study_target_days", "planned_days", "study_day",
    ):
        st.session_state.pop(key, None)


def show_page(number: int) -> None:
    st.session_state.pdf_page_number = number


def render_sources(source_ids: Sequence[str], key_prefix: str) -> None:
    with st.container(horizontal=True):
        for source_id in source_ids:
            number = int(source_id[1:])
            st.button(
                f"Page {number}",
                key=f"{key_prefix}_{source_id}",
                on_click=show_page,
                args=(number,),
            )


def render_study_plan(result: outline.Outline) -> None:
    st.header("Daily study plan")
    # Retire schedules from sessions opened before model-planned units were introduced.
    if "study_units" in st.session_state and "unit_plan" not in st.session_state:
        for key in ("study_units", "study_plan", "planned_days", "study_day"):
            st.session_state.pop(key, None)
    if "study_units" not in st.session_state:
        st.caption("OpenAI uses the outline to organize topics into learning units and prepare a study task for each.")
    with st.form("study_duration"):
        target_days = st.number_input(
            "Target duration (days)", min_value=1, value=7, step=1, key="study_target_days",
            help="Choose how many days to spend on the full outline.",
        )
        create_plan = st.form_submit_button("Create study plan")

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

    planned_days = st.session_state.get("planned_days")
    if planned_days is None:
        return
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
    for assignment in days[number - 1].assignments:
        unit = assignment.unit
        action = assignment.kind.capitalize()
        task = ""
        if assignment.kind != "read":
            task = f"<p><strong>Study task</strong><br>{escape(unit.activity)}</p>"
        st.html(
            f"<p><strong>{action} · {escape(unit.title)}</strong><br>{escape(unit.objective)}</p>{task}"
        )
        render_sources(assignment.source_ids, f"plan_citation_{number}_{unit.unit_id}")


def render_outline(pages: list[PdfPage]) -> None:
    st.header("Study outline")
    result = st.session_state.get("study_outline")
    if result is None:
        readable_count = sum(1 for page in pages if not page.error and page.text.strip())
        st.caption("Generate an outline from this PDF’s readable text using OpenAI.")
        if readable_count < len(pages):
            st.caption(f"Pages with readable text: {readable_count} of {len(pages)}.")
        if not st.button("Generate outline", type="primary", disabled=readable_count == 0):
            return
        try:
            with st.spinner("Generating study outline…"):
                result = outline.generate_outline(pages)
        except (LLMError, outline.OutlineError) as error:
            st.error(str(error))
            return
        st.session_state.study_outline = result

    for index, topic in enumerate(result.topics):
        st.html(f"<h3>{escape(topic.title)}</h3><p>{escape(topic.summary)}</p>")
        render_sources(topic.source_ids, f"citation_{index}")
    render_study_plan(result)


def main() -> None:
    st.set_page_config(page_title="Study materials · Adaptive Tutor", layout="wide")
    st.title("Study materials")
    upload = st.file_uploader("Upload a PDF", type=["pdf"], on_change=reset_preview)
    if upload is None:
        return

    if "pdf_pages" not in st.session_state:
        try:
            with st.spinner("Reading PDF…"):
                st.session_state.pdf_pages = read_pdf_pages(upload.getvalue())
        except PdfInputError as error:
            st.error(str(error))
            return

    pages = st.session_state.pdf_pages
    preview_column, outline_column = st.columns(2, gap="large")
    with preview_column:
        st.header("PDF preview")
        page_number = st.selectbox("Page", range(1, len(pages) + 1), key="pdf_page_number")
        page = pages[page_number - 1]
        st.text(f"{upload.name} · Page {page.number} of {len(pages)}")
        pdf_viewer(
            upload.getvalue(),
            pages_to_render=[page.number],
            render_text=True,
            height=650,
            key=f"original_pdf_{upload.file_id}_{page.number}",
        )
        with st.expander("Extracted text"):
            if page.error:
                st.warning(page.error)
            elif page.text.strip():
                st.code(page.text, language=None)
            else:
                st.info("No selectable text on this page. It may be blank or scanned. Scanned pages need OCR.")
    with outline_column:
        render_outline(pages)


if __name__ == "__main__":
    main()
