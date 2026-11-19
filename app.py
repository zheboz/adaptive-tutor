from html import escape

import streamlit as st

import tutor.planning as planning
from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.ui import check, learner, tutor_chat
from tutor.ui import practice as practice_ui
from tutor.ui.citations import render_sources
from tutor.ui.reader import READER_PANEL_HEIGHT, render_extracted_text, render_pdf_preview


def reset_preview() -> None:
    for key in (
        "pdf_pages", "pdf_page_number", "study_outline", "unit_plan", "study_units",
        "study_plan", "study_target_days", "planned_days", "study_day",
        "practice_index", "practice_sets", "practice_answers", "practice_skips",
        "learner_state", "planned_weak", "qa_session", *check.CHECK_KEYS,
    ):
        st.session_state.pop(key, None)
    learner.clear_weak_topics()


def ensure_units(result: outline.Outline) -> tuple[planning.StudyUnit, ...] | None:
    """Build the study units once. They depend only on the outline, not on the number of days."""
    # Retire schedules from sessions opened before model-planned units were introduced.
    if "study_units" in st.session_state and "unit_plan" not in st.session_state:
        for key in ("study_units", "study_plan", "planned_days", "study_day"):
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


def render_initial_check_controls(result: outline.Outline, pages: list[PdfPage]) -> None:
    """Between the outline and the plan: check the weak topics with a few questions."""
    if st.session_state.get("planned_days") is not None:
        return
    st.subheader("Initial check")
    summary = st.session_state.get("initial_check_summary")
    if summary:
        st.caption(f"Done. {summary}")
    else:
        st.caption("Optional, before you plan: check the topics you find weak in the outline, then answer "
                   "up to 5 questions. Your plan uses the answers.")
    if st.button("Check again" if summary else "Start initial check", key="start_initial_check",
                 disabled=check.active()):
        units = ensure_units(result)
        if units is not None:
            learner.apply_plan_inputs(units)
            check.start_initial_check(units, pages)
            st.rerun()


def render_plan_controls(result: outline.Outline) -> None:
    running = check.initial_running()
    with st.form("study_duration"):
        target_days = st.number_input(
            "Target duration (days)", min_value=1, value=7, step=1, key="study_target_days",
            help="Choose how many days to spend on the full outline.",
        )
        st.caption("Finish or stop the initial check before creating the plan." if running else
                   "Topics you check as weak, and units the initial check finds weak, get more of the time.")
        create_plan = st.form_submit_button(
            "Create study plan", disabled=running,
            help="OpenAI prepares the study tasks once. Changing the duration reuses them.",
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
            st.session_state.study_day = 1
            check.reset_progress()
            # The initial check controls above the form were drawn before the plan existed.
            st.rerun()


def render_study_plan(pages: list[PdfPage], document_id: str) -> None:
    planned_days = st.session_state.planned_days
    units = st.session_state.study_units
    learner.learner_state(units)
    days = st.session_state.get("study_plan")
    # An open session can still hold a schedule made by the previous version.
    if not days or not hasattr(days[0], "assignments"):
        days = planning.schedule_units(units, planned_days, st.session_state.get("planned_weak", ()))
        st.session_state.study_plan = days
    if check.render_check(units):
        return
    days = st.session_state.study_plan
    st.text(f"{planned_days}-day plan · {len(units)} study unit{'s' if len(units) != 1 else ''}")
    weak = set(st.session_state.get("planned_weak", ()))
    if weak:
        st.caption("More time for: " + "; ".join(unit.title for unit in units if unit.unit_id in weak))
    if st.session_state.get("initial_check_summary"):
        st.caption(f"From your initial check: {st.session_state.initial_check_summary}")
    done = check.completed_days()
    st.caption(f"Goal: {planned_days} days · plan: {len(days)} study days · "
               f"{len(done)} checked · {sum(n not in done for n in range(1, len(days) + 1))} to go")
    if len(days) > planned_days:
        st.warning(f"The plan now needs {len(days)} days, {len(days) - planned_days} more than your goal, "
                   "because reviews were added after your checks. Study at your own pace, or create the "
                   "plan again with more days.")
    if planned_days > len(days):
        start = len(days) + 1
        label = f"Day {start}" if start == planned_days else f"Days {start}–{planned_days}"
        st.caption(f"{label} · optional review")
    check.render_plan_changes()

    last_day = max(planned_days, len(days))
    number = st.number_input("Study day", min_value=1, max_value=last_day, step=1, key="study_day")
    st.subheader(f"Day {number} · checked" if number in done else f"Day {number}")
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
        practice_ui.render_questions(scope, unit.unit_id)
    check.render_daily_check_button(units, pages, days, number)


def tutor_context(result: outline.Outline) -> dict:
    """What the tutor should know about the learner when answering a question."""
    context: dict = {"weak_topics": [
        result.topics[number - 1].title for number in sorted(learner.weak_topic_numbers())
        if number <= len(result.topics)
    ]}
    days = st.session_state.get("study_plan")
    number = st.session_state.get("study_day")
    if days and number and number <= len(days):
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


def render_outline(result: outline.Outline | None, height: int) -> None:
    st.header("Study outline")
    with st.container(height=height, border=True, key="outline_panel"):
        if result is None:
            st.caption("Select Generate outline in the sidebar to see the topics and their source pages.")
            return
        st.caption("Check the topics you find weak or unclear. They are used when you select Create study plan.")
        for index, topic in enumerate(result.topics):
            st.html(f"<h3>{escape(topic.title)}</h3><p>{escape(topic.summary)}</p>")
            learner.render_weak_topic_checkbox(index)
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
            render_initial_check_controls(result, pages)
            render_plan_controls(result)

    has_plan = st.session_state.get("planned_days") is not None
    # Before a plan exists, an initial check takes the outline's place beside the PDF.
    checking = not has_plan and check.active()
    preview_column, learning_column = st.columns([3, 2] if has_plan or checking else 2, gap=12)
    with preview_column:
        page = render_pdf_preview(upload, pages)
    with learning_column:
        if has_plan:
            st.header("Daily study plan")
            with st.container(height=READER_PANEL_HEIGHT, border=True, key="plan_panel"):
                render_study_plan(pages, upload.file_id)
        elif checking:
            st.header("Initial check")
            with st.container(height=READER_PANEL_HEIGHT, border=True, key="check_panel"):
                check.render_check(st.session_state.study_units)
        else:
            render_outline(result, READER_PANEL_HEIGHT)
    if result is not None:
        tutor_chat.render_tutor_chat(pages, tutor_context(result), 360)
    if "study_units" in st.session_state:
        learner.render_learning_status(st.session_state.study_units, 280)
    if has_plan or checking:
        render_outline(result, 320)
    render_extracted_text(page)


if __name__ == "__main__":
    main()
