"""Knowledge-point cards in the Today view.

A day's cards are made when the day is opened and kept for the session; the next day's are made in
the background meanwhile. Cards depend only on a unit and its pages, so a review day reuses them.
"""

from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
import contextvars
from html import escape

import streamlit as st

from tutor.llm import LLMError
from tutor.materials import cards
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyAssignment, StudyDay
from tutor.ui.citations import render_sources


CARD_KEYS = ("day_cards",)
# One pool for the whole server: the app script itself runs again on every interaction.
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="day-cards")

# A card, a request still running, or why it failed.
_Entry = cards.UnitCard | Future | str


def _key(assignment: StudyAssignment) -> tuple[str, tuple[str, ...]]:
    return assignment.unit.unit_id, tuple(assignment.source_ids)


def _store() -> dict[tuple[str, tuple[str, ...]], _Entry]:
    return st.session_state.setdefault("day_cards", {})


def _submit(assignment: StudyAssignment, pages: Sequence[PdfPage]) -> None:
    store = _store()
    if _key(assignment) not in store:
        # The worker uses this session's key and model.
        context = contextvars.copy_context()
        unit = assignment.unit
        store[_key(assignment)] = _POOL.submit(
            context.run, cards.build_card, unit.title, unit.objective, assignment.source_ids, pages,
        )


def prefetch(day: StudyDay, pages: Sequence[PdfPage]) -> None:
    """Start making this day's cards in the background. Call inside `llm.using(...)`."""
    for assignment in day.assignments:
        _submit(assignment, pages)


def _forget(key: tuple[str, tuple[str, ...]]) -> None:
    _store().pop(key, None)


def _card(assignment: StudyAssignment) -> cards.UnitCard | str:
    store = _store()
    entry = store[_key(assignment)]
    if isinstance(entry, Future):
        try:
            with st.spinner(f"Preparing the knowledge points for {assignment.unit.title}…"):
                entry = entry.result()
        except LLMError as error:
            # Kept until Try again, so other interactions do not repeat a failed request.
            entry = str(error)
        store[_key(assignment)] = entry
    return entry


def render_card(assignment: StudyAssignment, pages: Sequence[PdfPage], key: str) -> None:
    """The unit's knowledge points: explanation, details, the page, and the quote behind them."""
    _submit(assignment, pages)
    card = _card(assignment)
    if isinstance(card, str):
        st.warning(f"The knowledge points could not be prepared. {card}")
        st.button("Try again", key=f"{key}_retry", on_click=_forget, args=(_key(assignment),))
        return
    if not card.points:
        st.caption(card.problem or "No knowledge points for these pages.")
        return
    for number, point in enumerate(card.points, start=1):
        with st.container(border=True, key=f"{key}_point_{number}"):
            details = "".join(f"<li>{escape(detail)}</li>" for detail in point.details)
            st.html(f"<p><strong>{number}. {escape(point.title)}</strong><br>{escape(point.explanation)}</p>"
                    + (f"<ul>{details}</ul>" if details else ""))
            with st.expander(f"From page {point.source_id[1:]}"):
                st.caption(f"“{point.quote}”")
            render_sources([point.source_id], f"{key}_point_{number}")
