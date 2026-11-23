"""The learner's PDF and its outline, for the whole session.

The upload widget is drawn only in the first setup step, and Streamlit drops a widget's file while
it is not drawn, so the file is copied into plain session keys as soon as it is chosen.
"""

from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
import contextvars
from html import escape
import time

import streamlit as st

from tutor.llm import LLMError
from tutor.materials import outline
from tutor.materials.ingest import PdfInputError, PdfPage, read_pdf_pages
from tutor.ui import cards, check, learner, navigation, quiz, settings, units
from tutor.ui.reader import READER_KEYS


UPLOAD_KEY = "pdf_upload"
# The outline is made in the background from the moment there is a PDF and a key.
_OUTLINE_JOB = "outline_job"
_OUTLINE_STARTED = "outline_started"
_OUTLINE_PROGRESS = "outline_progress"
# One pool for the whole server: the app script itself runs again on every interaction.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="outline")
_PDF_KEYS = ("pdf_bytes", "pdf_name", "pdf_id", "pdf_error", "pdf_pages")
_STUDY_KEYS = (
    "study_outline", "outline_error", "study_plan", "study_target_days", "draft_days", "planned_days",
    "passage_index", "learner_state", "planned_weak", "qa_session", _OUTLINE_JOB, _OUTLINE_STARTED,
    _OUTLINE_PROGRESS,
)


def reset() -> None:
    """Forget the material and everything made from it; the chosen model stays."""
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


class OutlineProgress:
    """What the background job has read so far; written by the job's thread, read by the page."""

    def __init__(self) -> None:
        self.topics: tuple[outline.Topic, ...] = ()
        self.done = 0
        self.total = 0

    def update(self, topics: list[outline.Topic], done: int, total: int) -> None:
        self.topics, self.done, self.total = tuple(topics), done, total


def start_outline(pages: Sequence[PdfPage], has_key: bool) -> None:
    """Start making the outline in the background, once, as soon as there is readable text and a key.
    Call inside `llm.using(...)`: the job uses this session's key and model."""
    if (not has_key or current_outline() is not None or _OUTLINE_JOB in st.session_state
            or "outline_error" in st.session_state or not readable(pages)):
        return
    context = contextvars.copy_context()
    progress = OutlineProgress()
    st.session_state[_OUTLINE_PROGRESS] = progress
    st.session_state[_OUTLINE_JOB] = _POOL.submit(context.run, outline.generate_outline, list(pages),
                                                  progress.update)
    st.session_state[_OUTLINE_STARTED] = time.monotonic()


def outline_running() -> bool:
    job = st.session_state.get(_OUTLINE_JOB)
    return job is not None and not job.done()


def _collect(job: Future) -> None:
    """Keep the finished job's outline, or why it failed: a failure waits for Try again rather than
    repeating on every interaction."""
    st.session_state.pop(_OUTLINE_JOB, None)
    st.session_state.pop(_OUTLINE_PROGRESS, None)
    try:
        st.session_state.study_outline = job.result()
    except (LLMError, outline.OutlineError) as error:
        st.session_state.outline_error = str(error)


def _page_range(source_ids: Sequence[str]) -> str:
    numbers = [int(source_id[1:]) for source_id in source_ids]
    if len(numbers) > 1 and numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"Pages {numbers[0]}–{numbers[-1]}"
    return ("Pages " if len(numbers) > 1 else "Page ") + ", ".join(map(str, numbers))


def _progress(page_count: int, progress: OutlineProgress, seconds: int) -> str:
    """The job working, then the topics found so far, as they will be listed."""
    if progress.total > 1:
        status = f"Read {progress.done} of {progress.total} parts of your PDF"
    else:
        status = f"Going through {page_count} page{'s' if page_count != 1 else ''}"
    card = (
        '<div class="outline-progress"><p class="outline-progress-title">The tutor is reading your PDF</p>'
        f"<p>{status} · {seconds} s</p>"
        '<div class="outline-progress-bar"><span></span></div>'
        '<p class="outline-progress-note">Topics appear below as each part is read. When all are listed, '
        "you can mark the ones that are unclear. You can go back to step 1 meanwhile.</p></div>"
    )
    topics = "".join(
        f'<div class="topic-preview"><h4>{number}. {escape(topic.title)}</h4><p>{escape(topic.summary)}</p>'
        f'<p class="topic-preview-pages">{_page_range(topic.source_ids)}</p></div>'
        for number, topic in enumerate(progress.topics, start=1)
    )
    return card + topics


# A job that ends this soon is shown finished at once, without a progress card first.
_GRACE_SECONDS = 0.5


@st.fragment(run_every=0.5)
def render_outline_progress(page_count: int) -> None:
    """The job working and the topics it has found, refreshed on its own twice a second while the
    rest of the page stays as it is; when the job ends, the whole page is drawn again with the
    outline. Show it while `outline_running()`."""
    job = st.session_state.get(_OUTLINE_JOB)
    if job is None or job.done():
        st.rerun()
    progress = st.session_state.get(_OUTLINE_PROGRESS) or OutlineProgress()
    seconds = int(time.monotonic() - st.session_state.get(_OUTLINE_STARTED, time.monotonic()))
    st.html(_progress(page_count, progress, seconds))


def prepare_outline(pages: Sequence[PdfPage], has_key: bool) -> outline.Outline | None:
    """The outline once it is made; None while it is being made (see `render_outline_progress`), or
    when it cannot be. Without a key nothing is sent.

    As soon as the outline is ready, the study units are planned in the background."""
    start_outline(pages, has_key)
    job = st.session_state.get(_OUTLINE_JOB)
    if job is not None:
        wait([job], timeout=_GRACE_SECONDS)
        if job.done():
            _collect(job)
    result = current_outline()
    if result is not None:
        units.start_planning(result)
    return result


def render_outline_status(pages: Sequence[PdfPage], has_key: bool) -> None:
    """Why there is no outline yet."""
    if not readable(pages):
        st.warning("This PDF has no readable text, so no outline can be made from it. Go back and choose a "
                   "PDF with selectable text.")
    elif not has_key:
        st.error(settings.NO_KEY)
    elif "outline_error" in st.session_state:
        st.error(st.session_state.outline_error)
        st.button("Try again", key="outline_retry", type="primary",
                  on_click=lambda: st.session_state.pop("outline_error", None))
