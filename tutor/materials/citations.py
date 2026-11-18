"""Link outline topics, planned readings, and practice questions to the PDF reader."""

from collections.abc import Sequence

import streamlit as st

from .reader import show_page


def render_sources(source_ids: Sequence[str], key_prefix: str) -> None:
    with st.container(horizontal=True):
        for source_id in source_ids:
            number = int(source_id[1:])
            st.button(
                f"Page {number}", key=f"{key_prefix}_{source_id}",
                on_click=show_page, args=(number,),
            )
