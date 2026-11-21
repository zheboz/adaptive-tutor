"""Page links: they open the page in the PDF reader when it is on screen, and in a window otherwise."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar

import streamlit as st

from .reader import open_page_window, show_page


# Each session's script runs in its own thread, so this follows the part of the page being drawn.
_TARGET: ContextVar[str] = ContextVar("page_link_target", default="window")


@contextmanager
def links_open_in_reader() -> Iterator[None]:
    """Inside this block the PDF reader is beside the links, so they turn its page."""
    token = _TARGET.set("reader")
    try:
        yield
    finally:
        _TARGET.reset(token)


def _follow(number: int, target: str) -> None:
    show_page(number)
    if target == "window":
        open_page_window(number)


def render_sources(source_ids: Sequence[str], key_prefix: str) -> None:
    target = _TARGET.get()
    with st.container(horizontal=True):
        for source_id in source_ids:
            number = int(source_id[1:])
            st.button(
                f"Page {number}", key=f"{key_prefix}_{source_id}",
                on_click=_follow, args=(number, target),
            )
