"""Adaptive Tutor: set up in four steps, then study day by day.

Setup (tutor/ui/wizard.py) takes the learner from their material to a plan, one full-width step at
a time. The study workspace (tutor/ui/workspace.py) then puts the PDF beside each day's material.
"""

import streamlit as st

from tutor import llm
from tutor.ui import material, navigation, settings, wizard, workspace
from tutor.ui.reader import render_page_window


# The reader and the panel beside it fill the window below the header and the day row; the numbers
# are the space those take, the page controls and the panel's own buttons. Python's pixel heights
# are the fallback.
_LAYOUT_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Caveat:wght@700&display=swap");
[data-testid="stMainBlockContainer"] {
    padding-inline: clamp(0.75rem, 2vw, 1.5rem);
    padding-top: 1.25rem;
}
.st-key-wizard, .st-key-check_panel, .st-key-progress_panel { max-width: 880px; margin-inline: auto; }
.st-key-plan_overview_panel { max-width: 1100px; margin-inline: auto; }
/* A container with a height is a flexible box inside a wrapper whose flex basis is that height, so
the heights go on the wrappers. */
:root { --panel-height: max(480px, calc(100vh - 210px)); }
[data-testid="stLayoutWrapper"]:has(> .st-key-pdf_preview_panel),
[data-testid="stLayoutWrapper"]:has(> .st-key-today_panel) { flex: 0 0 var(--panel-height) !important; height: var(--panel-height) !important; }
[data-testid="stLayoutWrapper"]:has(> .st-key-pdf_page_view),
.st-key-pdf_preview_panel [data-testid="stLayoutWrapper"]:has(> .st-key-extracted_text_panel) {
    flex: 0 0 calc(var(--panel-height) - 72px) !important; height: calc(var(--panel-height) - 72px) !important;
}
[data-testid="stLayoutWrapper"]:has(> .st-key-study_panel) { flex: 0 0 calc(var(--panel-height) - 80px) !important; height: calc(var(--panel-height) - 80px) !important; }
.st-key-today_panel [data-testid="stLayoutWrapper"]:has(> .st-key-tutor_chat_panel) {
    flex: 0 0 calc(var(--panel-height) - 150px) !important; height: calc(var(--panel-height) - 150px) !important;
}
.st-key-steps button { flex: 1 1 0; }
/* Notebook look: graph paper behind everything, the page as a sheet, the notes as sticky notes. */
/* Setup: the steps are tabs on top of a sheet of paper with a red margin line. */
.st-key-steps { gap: 6px !important; padding-inline: 12px; margin-bottom: calc(-1rem - 1px); position: relative; z-index: 1; }
.st-key-steps button {
    border-radius: 10px 10px 0 0 !important;
    border: 1px solid #DCE1E8 !important;
    border-bottom: none !important;
    background: #FFFFFF;
    color: #1E2430;
}
.st-key-steps button[data-testid="stBaseButton-primary"] {
    background: #1E2430;
    border-color: #1E2430 !important;
    color: #FFFFFF;
    box-shadow: inset 0 4px 0 #F2C94C;
}
.st-key-steps button:disabled { background: #EEF1F5; color: #6B7485; opacity: 1; }
.st-key-wizard_sheet, .st-key-check_panel {
    background-color: #FFFFFF;
    background-image: linear-gradient(90deg, transparent 36px, #F2A7A7 36px, #F2A7A7 38px, transparent 38px);
    padding: 24px 32px 32px 60px;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.08), 0 12px 32px rgba(30, 36, 48, 0.10);
}
.wizard-kicker { margin: 0; font-family: Caveat, cursive; font-size: 1.6rem; line-height: 1; color: #2457C5; }
.st-key-material_settings, .st-key-material_upload, .st-key-quiz_start {
    background: #F9FAFC;
    border: 1.5px dashed #C9D0DA !important;
    border-radius: 8px;
}
.st-key-material_settings strong, .st-key-material_upload strong, .st-key-quiz_start strong {
    font-family: Caveat, cursive;
    font-size: 1.7rem;
    font-weight: 700;
}
/* Each topic is an index card: a red rule under its title. */
[class*="st-key-topic_"] {
    background: #FFFFFF;
    border: 1px solid #DCE1E8 !important;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.06), 0 6px 16px rgba(30, 36, 48, 0.07);
}
[class*="st-key-topic_"] h4 { padding: 0 0 0.4rem; margin-bottom: 0.4rem; border-bottom: 2px solid #F2A7A7; }
.st-key-wizard_sheet [data-testid="stFileUploaderDropzone"] { background: #FFFBEA; border: 2px dashed #E0B53A; }
.st-key-wizard_sheet [data-baseweb="input"], .st-key-wizard_sheet [data-baseweb="select"] > div { background: #FFFFFF; }
.st-key-wizard_sheet button[data-testid="stBaseButton-primary"] {
    background: #F2C94C;
    border-color: #E0B53A;
    color: #1E2430;
    font-weight: 600;
}
.st-key-wizard_sheet button[data-testid="stBaseButton-primary"]:hover {
    background: #F5D56E;
    border-color: #C99A1E;
    color: #1E2430;
}
.st-key-wizard_sheet button[data-testid="stBaseButton-primary"]:disabled {
    background: #F7F1DA;
    border-color: #EADFB8;
    color: #7A6C40;
}
[data-testid="stAppViewContainer"] {
    background-color: #F7F8FA;
    background-image: linear-gradient(#E6EAF0 1px, transparent 1px),
                      linear-gradient(90deg, #E6EAF0 1px, transparent 1px);
    background-size: 28px 28px;
}
/* No Streamlit toolbar (running status, Stop, Deploy, menu): long steps show their own progress. */
[data-testid="stHeader"] { display: none; }
/* The outline being made in the background. */
.outline-progress {
    padding: 18px 20px;
    background: #FFFBEA;
    border: 2px dashed #E0B53A;
    border-radius: 8px;
}
.outline-progress p { margin: 0 0 0.4rem; }
.outline-progress-title { font-family: Caveat, cursive; font-size: 1.8rem; font-weight: 700; line-height: 1.1; }
.outline-progress-note { color: #586274; font-size: 0.9rem; }
.outline-progress-bar {
    position: relative;
    height: 8px;
    margin: 0.6rem 0;
    overflow: hidden;
    border-radius: 4px;
    background: #F3E6B5;
}
.outline-progress-bar span {
    position: absolute;
    inset: 0 auto 0 0;
    width: 35%;
    border-radius: 4px;
    background: #E0B53A;
    animation: outline-progress 1.4s ease-in-out infinite;
}
/* Topics already found, shown as the index cards they become. */
.topic-preview {
    margin-top: 12px;
    padding: 14px 16px;
    background: #FFFFFF;
    border: 1px solid #DCE1E8;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.06), 0 6px 16px rgba(30, 36, 48, 0.07);
}
.topic-preview h4 { margin: 0 0 0.4rem; padding: 0 0 0.4rem; border-bottom: 2px solid #F2A7A7; }
.topic-preview p { margin: 0 0 0.3rem; }
.topic-preview-pages { color: #1F4B9E; font-size: 0.9rem; }
@keyframes outline-progress { from { left: -35%; } to { left: 100%; } }
@media (prefers-reduced-motion: reduce) {
    .outline-progress-bar span { animation: none; width: 100%; opacity: 0.5; }
}
.st-key-header {
    background: #FFFFFF;
    border: 1px solid #DCE1E8;
    border-radius: 12px;
    padding: 6px 14px;
}
.notebook-label {
    margin: 0;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #586274;
}
/* The days as tabs down the side of the notebook. */
.st-key-day_strip [data-testid="stElementContainer"],
.st-key-day_strip [data-testid="stButtonGroup"] { width: 100% !important; }
.st-key-day_strip [role="radiogroup"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    width: 100% !important;
    max-width: none !important;
    gap: 6px;
}
.st-key-day_strip [data-testid="stButtonGroup"] button {
    width: 100%;
    justify-content: flex-start;
    border-radius: 0 10px 10px 0 !important;
    border: 1px solid #DCE1E8 !important;
    border-left: 4px solid #C9D0DA !important;
    background: #FFFFFF;
    margin: 0 !important;
}
.st-key-day_strip [data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: #1E2430;
    color: #FFFFFF;
    border-left-color: #F2C94C !important;
}
.st-key-pdf_preview_panel {
    background: #FFFFFF;
    border: none !important;
    border-radius: 6px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.08), 0 12px 32px rgba(30, 36, 48, 0.10);
}
.st-key-study_panel h3 { font-family: Caveat, cursive; font-size: 2.1rem; font-weight: 700; }
/* A unit opens like a section of the notebook: a handwritten label over a ruled line. */
.unit-heading { margin: 0.75rem 0 0.25rem; padding-bottom: 0.4rem; border-bottom: 2px solid #1E2430; }
.unit-heading p { margin: 0; }
.unit-heading strong { font-size: 1.1rem; }
.unit-kind { font-family: Caveat, cursive; font-size: 1.5rem; line-height: 1; color: #2457C5; }
.unit-objective { color: #3E4756; }
/* The study task is written on ruled paper with a red margin line. */
.study-task {
    position: relative;
    margin: 0.25rem 0;
    padding: 12px 16px 12px 44px;
    background-color: #FFFFFF;
    background-image: linear-gradient(90deg, transparent 31px, #F2A7A7 31px, #F2A7A7 33px, transparent 33px),
                      repeating-linear-gradient(#FFFFFF 0, #FFFFFF 27px, #DCE6F2 27px, #DCE6F2 28px);
    background-position: 0 0, 0 10px;
    line-height: 28px;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.08), 0 8px 20px rgba(30, 36, 48, 0.08);
}
.study-task p { margin: 0; }
.study-task-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: Caveat, cursive;
    font-size: 1.6rem;
    font-weight: 700;
}
.study-task-box { width: 16px; height: 16px; border: 2px solid #1E2430; border-radius: 3px; }
/* Page links as small bookmark tabs. */
[class*="st-key-unit_pages_"] [data-testid="stCaptionContainer"] { font-family: Caveat, cursive; font-size: 1.25rem; }
[class*="st-key-unit_pages_"] button, [class*="st-key-topic_"] button {
    height: 32px;
    padding: 2px 12px;
    border-radius: 999px;
    border-color: #C9D6F5;
    background: #EEF3FF;
    color: #1F4B9E;
}
/* The day's check: a card taped to the page, with a highlighter-yellow button. */
.st-key-daily_check_box {
    position: relative;
    margin-top: 1.25rem;
    padding: 22px 18px 14px;
    background: #FFFFFF;
    border-radius: 4px;
    box-shadow: 0 1px 2px rgba(30, 36, 48, 0.08), 0 10px 24px rgba(30, 36, 48, 0.10);
}
.st-key-daily_check_box::before {
    content: "";
    position: absolute;
    top: -10px;
    left: 50%;
    width: 96px;
    height: 22px;
    transform: translateX(-50%) rotate(-2deg);
    background: rgba(242, 201, 76, 0.55);
}
/* The daily check is a closed-book test sheet (the sheet itself is styled with the setup's). */
.check-progress { display: flex; gap: 6px; margin: 0 0 2px; }
.check-progress-dot { width: 28px; height: 6px; border-radius: 3px; background: #E3E8EF; }
.check-progress-dot.answered { background: #2457C5; }
.check-progress-dot.current { background: #E0B53A; }
.st-key-check_question [data-testid="stText"] { font-size: 1.15rem; font-weight: 600; line-height: 1.5; color: #1E2430; }
.st-key-check_question [data-testid="stForm"] {
    background: #F9FAFC;
    border: 1.5px dashed #C9D0DA;
    border-radius: 8px;
}
.st-key-check_question [role="radiogroup"] { gap: 8px; width: 100%; }
.st-key-check_question [role="radiogroup"] > div { width: 100%; }
.st-key-check_question [data-testid="stRadioOption"] {
    width: 100%;
    box-sizing: border-box;
    margin: 0;
    padding: 10px 14px;
    background: #FFFFFF;
    border: 1px solid #DCE1E8;
    border-radius: 8px;
}
.st-key-check_question [data-testid="stRadioOption"]:hover { border-color: #9FB4E0; }
.st-key-check_question [data-testid="stRadioOption"]:has(input:checked) { background: #FFF4C2; border-color: #E0B53A; }
.st-key-check_panel [data-testid="stFormSubmitButton"] button,
.st-key-check_panel button[data-testid="stBaseButton-primary"] {
    background: #F2C94C;
    border-color: #E0B53A;
    color: #1E2430;
    font-weight: 600;
}
.st-key-check_panel [data-testid="stFormSubmitButton"] button:hover,
.st-key-check_panel button[data-testid="stBaseButton-primary"]:hover {
    background: #F5D56E;
    border-color: #C99A1E;
    color: #1E2430;
}
/* Feedback on the last answer is a note stuck to the sheet. */
[class*="st-key-check_last_feedback_"] {
    background: #FFF9E0;
    border: none !important;
    border-radius: 4px 4px 4px 18px;
    box-shadow: 0 6px 14px rgba(30, 36, 48, 0.10);
    transform: rotate(-0.3deg);
}
/* The result: a handwritten verdict over ruled lines. */
.st-key-check_result strong { font-family: Caveat, cursive; font-size: 1.9rem; font-weight: 700; }
.st-key-check_result [data-testid="stCaptionContainer"] { padding: 4px 0; border-bottom: 1px solid #DCE6F2; }
/* Whether the check's first question is ready. */
.check-status { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 0.9rem; color: #3E4756; }
.check-dot { flex: none; width: 10px; height: 10px; border-radius: 50%; }
.check-dot.preparing { background: #E0B53A; animation: check-pulse 1.2s ease-in-out infinite; }
.check-dot.ready { background: #2E9E5B; }
@keyframes check-pulse { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .check-dot.preparing { animation: none; } }
.check-heading { margin: 0; font-family: Caveat, cursive; font-size: 1.8rem; font-weight: 700; line-height: 1.1; }
.st-key-daily_check_box button {
    height: 48px;
    background: #F2C94C;
    border-color: #E0B53A;
    color: #1E2430;
    font-weight: 600;
}
.st-key-daily_check_box button:hover { background: #F5D56E; border-color: #C99A1E; color: #1E2430; }
[class*="st-key-card_"][class*="_point_"][class*="_note"] {
    padding: 14px 16px 10px;
    border-radius: 4px 4px 4px 18px;
    box-shadow: 0 6px 14px rgba(30, 36, 48, 0.10);
}
[class*="_point_"][class*="_note"] p, [class*="_point_"][class*="_note"] ul { margin: 0 0 0.35rem; }
[class*="_point_"][class*="_note"] [data-testid="stExpander"] details {
    background: rgba(255, 255, 255, 0.55);
    border-color: rgba(30, 36, 48, 0.12);
}
[class*="_point_"][class*="_note"] button { background: rgba(255, 255, 255, 0.7); }
[class*="_point_"][class*="_note0"] { background: #FFF4C2; transform: rotate(-0.4deg); }
[class*="_point_"][class*="_note1"] { background: #DDEEFF; transform: rotate(0.3deg); }
[class*="_point_"][class*="_note2"] { background: #FFE1EC; transform: rotate(-0.2deg); }
[class*="_point_"][class*="_note3"] { background: #DDF5E6; transform: rotate(0.4deg); }
[class*="_point_"][class*="_note4"] { background: #FFE8D1; transform: rotate(-0.3deg); }
[class*="_point_"][class*="_note5"] { background: #ECE3FF; transform: rotate(0.2deg); }
.note-title { display: flex; align-items: center; gap: 8px; font-size: 1.02rem; }
.note-number {
    flex: none;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #1E2430;
    color: #FFFFFF;
    font-size: 0.8rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
/* Keep the arrow buttons' text labels accessible to screen readers. */
.st-key-pdf_page_controls button:not([data-variant="segmented_control"]) [data-testid="stMarkdownContainer"] {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
}
</style>
"""


def render_header(studying: bool, setup_step: int) -> str | None:
    """The app's name and material, the workspace pages while studying, and the settings.

    Returns the open workspace page while studying."""
    page = None
    with st.container(key="header", horizontal=True, horizontal_alignment="distribute",
                      vertical_alignment="center"):
        name = st.session_state.get("pdf_name")
        st.markdown(f"**Adaptive Tutor**{f' · {name}' if name and setup_step != 1 else ''}")
        if studying:
            page = navigation.render_page_picker()
        # In the first step the key and model are on the page itself.
        if setup_step != 1:
            with st.popover("Settings", icon=":material/settings:"):
                settings.render_settings()
                st.divider()
                st.button("Start over with another PDF", key="start_over", on_click=material.start_over,
                          help="Clears the outline, the plan and your progress. Your key and model stay.")
    return page


def main() -> None:
    st.set_page_config(page_title="Adaptive Tutor", layout="wide", initial_sidebar_state="collapsed")
    st.html(_LAYOUT_CSS)
    studying = st.session_state.get("planned_days") is not None and material.pages() is not None
    step = 0 if studying else wizard.current()
    page = render_header(studying, step)
    # Every model call in this run, including those in background threads, uses this session's
    # key and model.
    with llm.using(settings.current_key(), settings.current_model()):
        if studying:
            workspace.render(page, material.current_outline(), material.pages(), material.pdf())
        else:
            wizard.render(step)
    pdf = material.pdf()
    if pdf is not None and material.pages() is not None:
        render_page_window(pdf[0], pdf[1], material.pages())


if __name__ == "__main__":
    main()
