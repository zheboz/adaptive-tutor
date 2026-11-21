"""The learner's PDF and its outline, for the whole session.

The upload widget is drawn only in the first setup step, and Streamlit drops a widget's file while
it is not drawn, so the file is copied into plain session keys as soon as it is chosen.
"""

from collections.abc import Sequence

import streamlit as st

from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.ui import cards, check, learner, navigation, quiz, units
from tutor.ui.reader import READER_KEYS


UPLOAD_KEY = "pdf_upload"
_PDF_KEYS = ("pdf_bytes", "pdf_name", "pdf_id", "pdf_error", "pdf_pages")
_STUDY_KEYS = (
    "study_outline", "outline_error", "study_plan", "study_target_days", "draft_days", "planned_days",
    "passage_index", "learner_state", "planned_weak", "qa_session",
)


def reset() -> None:
    """Forget the material and everything made from it; the learner's key and model stay."""
    for key in (*_PDF_KEYS, *_STUDY_KEYS, *READER_KEYS, *units.UNIT_KEYS, *cards.CARD_KEYS, *check.CHECK_KEYS,
                *quiz.QUIZ_KEYS, *navigation.NAVIGATION_KEYS):
        st.session_state.pop(key, None)
    learner.clear_weak_topics()


def keep_upload() -> None:
    """The upload changed: start over with the new file, or with none when it was removed."""
    upload = st.session_state.get(UPLOAD_KEY)
    reset()
    if upload is not None:
        st.session_state.pdf_bytes = upload.getvalue()
        st.session_state.pdf_name = upload.name
        st.session_state.pdf_id = upload.file_id


def start_over() -> None:
    reset()
    st.session_state.pop(UPLOAD_KEY, None)


def pdf() -> tuple[bytes, str, str] | None:
    """The file's bytes, a stable ID for it, and its name."""
    if "pdf_bytes" not in st.session_state:
        return None
    return st.session_state.pdf_bytes, st.session_state.pdf_id, st.session_state.pdf_name


def pages() -> list[PdfPage] | None:
    """The PDF's pages, read once; None, with the reason kept in `pdf_error`, when it cannot be read."""
    if "pdf_pages" in st.session_state:
        return st.session_state.pdf_pages
    if "pdf_bytes" not in st.session_state:
        return None
    try:
        with st.spinner("Reading PDF…"):
            st.session_state.pdf_pages = read_pdf_pages(st.session_state.pdf_bytes)
    except PdfInputError as error:
        for key in _PDF_KEYS:
            st.session_state.pop(key, None)
        st.session_state.pdf_error = str(error)
        return None
    return st.session_state.pdf_pages


def readable(pages: Sequence[PdfPage]) -> int:
    return sum(1 for page in pages if not page.error and page.text.strip())


def current_outline() -> outline.Outline | None:
    return st.session_state.get("study_outline")


def prepare_outline(pages: Sequence[PdfPage], has_key: bool) -> outline.Outline | None:
    """Generate the outline once; there is nothing to decide first. A failure waits for Try again
    rather than repeating on every interaction. Without a key, the model call stops before any
    request, and the outline follows once the key is entered.

    As soon as the outline is ready, the study units are planned in the background."""
    result = current_outline()
    if result is None and readable(pages) and "outline_error" not in st.session_state:
        try:
            with st.spinner("Reading your material and building the outline…"):
                result = outline.generate_outline(list(pages))
        except (LLMError, outline.OutlineError) as error:
            if has_key:
                st.session_state.outline_error = str(error)
        else:
            st.session_state.study_outline = result
    if result is not None:
        units.start_planning(result)
    return result


def render_outline_status(pages: Sequence[PdfPage], has_key: bool) -> None:
    """Why there is no outline yet."""
    if not readable(pages):
        st.warning("This PDF has no readable text, so no outline can be made from it. Go back and choose a "
                   "PDF with selectable text.")
    elif not has_key:
        st.info("Enter your OpenAI API key in the settings. The outline is made as soon as it is in.")
    elif "outline_error" in st.session_state:
        st.error(st.session_state.outline_error)
        st.button("Try again", key="outline_retry", type="primary",
                  on_click=lambda: st.session_state.pop("outline_error", None))
