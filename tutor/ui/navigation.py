"""Where the learner is: the setup step, the workspace page, and the open study day.

All three are kept in plain session keys rather than only in their widgets: Streamlit drops a
widget's state while the widget is not drawn, and each of these widgets is hidden at times.
"""

import streamlit as st


# Setup: 1 Material, 2 Topics, 3 Quick check, 4 Plan.
STEP_KEY = "setup_step"
SETUP_STEPS = ("Material", "Topics", "Quick check", "Plan")
# The study workspace: Today, Plan or Progress.
PAGE_KEY = "workspace_page"
WORKSPACE_PAGES = ("Today", "Plan", "Progress")
# Beside the PDF on Today: the day's material, or the chat.
PANEL_KEY = "today_tab"
TODAY_PANELS = ("Study", "Ask the tutor")
DAY_KEY = "current_day"
_DAY_PICKER = "day_picker"
NAVIGATION_KEYS = (STEP_KEY, PAGE_KEY, f"{PAGE_KEY}_choice", PANEL_KEY, f"{PANEL_KEY}_choice", DAY_KEY,
                   _DAY_PICKER)


def current_step() -> int:
    return st.session_state.get(STEP_KEY, 1)


def go_to_step(step: int) -> None:
    st.session_state[STEP_KEY] = step


def _remembered(key: str, options: tuple[str, ...]) -> str:
    choice = st.session_state.get(f"{key}_choice")
    return choice if choice in options else options[0]


def _keep_choice(key: str) -> None:
    st.session_state[f"{key}_choice"] = st.session_state[key]


def _render_choice(label: str, key: str, options: tuple[str, ...]) -> str:
    """A row of buttons whose choice is kept while the row is hidden."""
    st.session_state[key] = _remembered(key, options)
    st.segmented_control(label, options, key=key, required=True, on_change=_keep_choice, args=(key,),
                         label_visibility="collapsed")
    return _remembered(key, options)


def current_page() -> str:
    return _remembered(PAGE_KEY, WORKSPACE_PAGES)


def show_page(name: str) -> None:
    st.session_state[f"{PAGE_KEY}_choice"] = name


def render_page_picker() -> str:
    return _render_choice("Page", PAGE_KEY, WORKSPACE_PAGES)


def render_panel_picker() -> str:
    return _render_choice("Beside the PDF", PANEL_KEY, TODAY_PANELS)


def current_day() -> int:
    return st.session_state.get(DAY_KEY, 1)


def open_day(day: int) -> None:
    st.session_state[DAY_KEY] = day


def _day_picked() -> None:
    st.session_state[DAY_KEY] = st.session_state[_DAY_PICKER]


def render_day_picker(last_day: int, label) -> int:
    """Days as a row of buttons, each labeled by `label(day)`. Returns the open day."""
    day = min(max(current_day(), 1), last_day)
    open_day(day)
    st.session_state[_DAY_PICKER] = day
    st.segmented_control("Study day", list(range(1, last_day + 1)), key=_DAY_PICKER, format_func=label,
                         required=True, on_change=_day_picked, label_visibility="collapsed")
    return day
