"""Render the original PDF page, and the text read from it in a collapsed section."""

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
from streamlit_pdf_viewer import pdf_viewer

from tutor.materials.ingest import PdfPage


READER_PANEL_HEIGHT = 520
_ARROW_WIDTH = 40


def show_page(number: int) -> None:
    st.session_state.pdf_page_number = number


def render_pdf_preview(upload: UploadedFile, pages: list[PdfPage]) -> PdfPage:
    """Page controls in a row above the page, level with the view bar beside it; the page below,
    in a panel as tall as the view panel."""
    count = len(pages)
    page = pages[st.session_state.get("pdf_page_number", 1) - 1]
    with st.container(key="pdf_page_controls", horizontal=True, gap=4):
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
    with st.container(key="pdf_preview_panel", height=READER_PANEL_HEIGHT, border=True):
        pdf_viewer(
            upload.getvalue(), pages_to_render=[page.number], render_text=True,
            height=READER_PANEL_HEIGHT - 50, zoom_level="auto", key=f"original_pdf_{upload.file_id}_{page.number}",
        )
    return page


def render_extracted_text(page: PdfPage) -> None:
    """The text read from the page, for checking what the tutor works from; collapsed by default."""
    with st.expander(f"Extracted text · page {page.number}"):
        with st.container(key="extracted_text_panel", height=240, border=False):
            if page.error:
                st.warning(page.error)
            elif page.text.strip():
                st.code(page.text, language=None)
            else:
                st.info("No selectable text on this page. It may be blank or scanned. Scanned pages need OCR.")
