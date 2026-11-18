import streamlit as st

from tutor.materials.ingest import PdfInputError, read_pdf_pages


def reset_preview() -> None:
    st.session_state.pop("pdf_pages", None)
    st.session_state.pop("pdf_page_number", None)


def main() -> None:
    st.set_page_config(page_title="PDF preview · Adaptive Tutor")
    st.title("PDF text preview")
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
    page_number = st.selectbox("Page", range(1, len(pages) + 1), key="pdf_page_number")
    page = pages[page_number - 1]
    st.text(f"{upload.name} · Page {page.number} of {len(pages)}")
    if page.error:
        st.warning(page.error)
    elif page.text.strip():
        st.code(page.text, language=None)
    else:
        st.info("No selectable text on this page. It may be blank or scanned. Scanned pages need OCR.")


if __name__ == "__main__":
    main()
