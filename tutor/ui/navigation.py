"""Which view is shown beside the PDF, and which study day is open.

Both are kept in plain session keys rather than only in their widgets: Streamlit drops a widget's
state while the widget is not drawn, and the day picker is hidden whenever another view is open.
"""

import streamlit as st


VIEW_KEY = "right_view"
_NEXT_VIEW = "next_view"
DAY_KEY = "current_day"
_DAY_PICKER = "day_picker"
NAVIGATION_KEYS = (VIEW_KEY, _NEXT_VIEW, DAY_KEY, _DAY_PICKER)


def show_view(name: str) -> None:
    """Open this view the next time the view bar is drawn; follow with `st.rerun()`.

    The buttons that switch views sit inside a view, below the bar that is already drawn.
    """
    st.session_state[_NEXT_VIEW] = name


def render_view_bar(options: list[str]) -> str:
    if st.session_state.get(_NEXT_VIEW) in options:
        st.session_state[VIEW_KEY] = st.session_state.pop(_NEXT_VIEW)
    if st.session_state.get(VIEW_KEY) not in options:
        st.session_state[VIEW_KEY] = options[0]
    return st.segmented_control("View", options, key=VIEW_KEY, required=True, label_visibility="collapsed")


def current_day() -> int:
    return st.session_state.get(DAY_KEY, 1)


def open_day(day: int) -> None:
    st.session_state[DAY_KEY] = day


def _picked() -> None:
    st.session_state[DAY_KEY] = st.session_state[_DAY_PICKER]


def render_day_picker(last_day: int, label) -> int:
    """Days as a row of buttons, each labeled by `label(day)`. Returns the open day."""
    day = min(max(current_day(), 1), last_day)
    open_day(day)
    st.session_state[_DAY_PICKER] = day
    st.segmented_control("Study day", list(range(1, last_day + 1)), key=_DAY_PICKER, format_func=label,
                         required=True, on_change=_picked, label_visibility="collapsed")
    return day
