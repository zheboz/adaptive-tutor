"""The PDF reader in the study workspace, and the window that shows one page everywhere else."""

from collections.abc import Sequence

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from tutor.materials.ingest import PdfPage


READER_PANEL_HEIGHT = 560
_ARROW_WIDTH = 40
_WINDOW_KEY = "page_window"
_MODE_KEY = "reader_mode"
READER_KEYS = ("pdf_page_number", _WINDOW_KEY, _MODE_KEY)


def show_page(number: int) -> None:
    st.session_state.pdf_page_number = number


def open_page_window(number: int) -> None:
    """Show this page in a window on the next run; see `render_page_window`."""
    st.session_state[_WINDOW_KEY] = number


def _render_page_text(page: PdfPage, height: int) -> None:
    with st.container(key="extracted_text_panel", height=height, border=False):
        if page.error:
            st.warning(page.error)
        elif page.text.strip():
            st.code(page.text, language=None)
        else:
            st.info("No selectable text on this page. It may be blank or scanned. Scanned pages need OCR.")


def render_pdf_preview(pdf: bytes, pdf_id: str, pages: Sequence[PdfPage]) -> PdfPage:
    """The page, or the text read from it, with the page controls below, in one panel as tall as the
    panel beside it; both fill the window's height (see the layout CSS in app.py)."""
    count = len(pages)
    page = pages[st.session_state.get("pdf_page_number", 1) - 1]
    with st.container(key="pdf_preview_panel", height=READER_PANEL_HEIGHT, border=True, gap="xsmall"):
        if st.session_state.get(_MODE_KEY) == "Text":
            _render_page_text(page, READER_PANEL_HEIGHT - 72)
        else:
            # The whole page at the panel's width; it scrolls inside the panel when taller.
            with st.container(key="pdf_page_view", height=READER_PANEL_HEIGHT - 72, border=False):
                pdf_viewer(pdf, pages_to_render=[page.number], render_text=True, zoom_level="auto",
                           key=f"original_pdf_{pdf_id}_{page.number}")
        with st.container(key="pdf_page_controls", horizontal=True, horizontal_alignment="center", gap=4):
            st.button(
                "Previous page", icon=":material/arrow_upward:", help="Previous page", width=_ARROW_WIDTH,
                disabled=page.number == 1, on_click=show_page, args=(page.number - 1,),
            )
            st.button(
                "Next page", icon=":material/arrow_downward:", help="Next page", width=_ARROW_WIDTH,
                disabled=page.number == count, on_click=show_page, args=(page.number + 1,),
            )
            st.selectbox(
                "Page", range(1, count + 1), key="pdf_page_number", label_visibility="collapsed",
                format_func=lambda number: f"Page {number} of {count}", width=144,
            )
            st.segmented_control("Show", ("Page", "Text"), key=_MODE_KEY, default="Page", required=True,
                                 label_visibility="collapsed",
                                 help="Text shows what the tutor reads from this page.")
    return page


@st.dialog("Source page", width="large")
def _page_window(pdf: bytes, pdf_id: str, page: PdfPage) -> None:
    st.subheader(f"Page {page.number}", anchor=False)
    with st.container(key="page_window_view", height=520, border=False):
        pdf_viewer(pdf, pages_to_render=[page.number], render_text=True, zoom_level="auto",
                   key=f"window_pdf_{pdf_id}_{page.number}")
    with st.expander("Text the tutor reads from this page"):
        _render_page_text(page, 200)


def render_page_window(pdf: bytes, pdf_id: str, pages: Sequence[PdfPage]) -> None:
    """Open the page a link asked for, when the reader is not on screen. Call once, at the end of a run."""
    number = st.session_state.pop(_WINDOW_KEY, None)
    if number is not None and 1 <= number <= len(pages):
        _page_window(pdf, pdf_id, pages[number - 1])
