from html import escape

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages


def reset_preview() -> None:
    st.session_state.pop("pdf_pages", None)
    st.session_state.pop("pdf_page_number", None)
    st.session_state.pop("study_outline", None)


def show_page(number: int) -> None:
    st.session_state.pdf_page_number = number


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
        with st.container(horizontal=True):
            for source_id in topic.source_ids:
                number = int(source_id[1:])
                st.button(
                    f"Page {number}",
                    key=f"citation_{index}_{source_id}",
                    on_click=show_page,
                    args=(number,),
                )


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
