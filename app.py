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
[data-testid="stMainBlockContainer"] {
    padding-inline: clamp(0.75rem, 2vw, 1.5rem);
    padding-top: 3.5rem;
}
.st-key-wizard, .st-key-check_panel, .st-key-progress_panel { max-width: 880px; margin-inline: auto; }
.st-key-plan_overview_panel { max-width: 1100px; margin-inline: auto; }
:root { --panel-height: max(480px, calc(100vh - 210px)); }
.st-key-pdf_preview_panel, .st-key-today_panel { height: var(--panel-height) !important; }
.st-key-pdf_page_view, .st-key-pdf_preview_panel .st-key-extracted_text_panel {
    height: calc(var(--panel-height) - 72px) !important;
}
.st-key-study_panel { height: calc(var(--panel-height) - 80px) !important; }
.st-key-today_panel .st-key-tutor_chat_panel { height: calc(var(--panel-height) - 150px) !important; }
.st-key-steps button { flex: 1 1 0; }
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
