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


# Each knowledge point has a color: its note beside the PDF, and its highlight on the page.
NOTE_COLORS = 6


def color_of(number: int) -> int:
    return (number - 1) % NOTE_COLORS


def day_highlights(day: StudyDay) -> list[tuple[str, str, int]]:
    """The page, quote and color of each knowledge point of the day whose card is ready, numbered as
    `render_card` numbers them. Never waits for a card."""
    highlights = []
    number = 0
    for assignment in day.assignments:
        entry = _store().get(_key(assignment))
        if isinstance(entry, Future) and entry.done() and entry.exception() is None:
            entry = entry.result()
        if isinstance(entry, cards.UnitCard):
            for point in entry.points:
                number += 1
                highlights.append((point.source_id, point.quote, color_of(number)))
    return highlights


def render_card(assignment: StudyAssignment, pages: Sequence[PdfPage], key: str, first: int = 1) -> int:
    """The unit's knowledge points as notes: explanation, details, the page, and the quote behind
    them, highlighted on the page in the note's color. Numbers them from `first`; returns the next."""
    _submit(assignment, pages)
    card = _card(assignment)
    if isinstance(card, str):
        st.warning(f"The knowledge points could not be prepared. {card}")
        st.button("Try again", key=f"{key}_retry", on_click=_forget, args=(_key(assignment),))
        return first
    if not card.points:
        st.caption(card.problem or "No knowledge points for these pages.")
        return first
    for number, point in enumerate(card.points, start=first):
        # The key's ending picks the note's color in the layout CSS.
        with st.container(key=f"{key}_point_{number - first + 1}_note{color_of(number)}", gap="xsmall"):
            details = "".join(f"<li>{escape(detail)}</li>" for detail in point.details)
            st.html(f'<p class="note-title"><span class="note-number">{number}</span>'
                    f"<strong>{escape(point.title)}</strong></p><p>{escape(point.explanation)}</p>"
                    + (f"<ul>{details}</ul>" if details else ""))
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                render_sources([point.source_id], f"{key}_point_{number - first + 1}")
                with st.expander(f"From page {point.source_id[1:]}"):
                    st.caption(f"“{point.quote}”")
    return first + len(card.points)
