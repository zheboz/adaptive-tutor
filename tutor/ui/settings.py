"""The learner's own OpenAI key and model, in the sidebar.

The key stays in this browser session only: it is never shown pre-filled, never written to the
process environment shared by every session, and the app's own key (if any) is never displayed.
"""

from hashlib import sha256
import os

import streamlit as st

from tutor.llm import DEFAULT_MODEL, LLMError, list_models


OTHER = "Other…"
# Offered before the learner's own model list is loaded.
SUGGESTED_MODELS = ("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-5-mini")
SETTINGS_KEYS = ("api_key_input", "show_api_key", "model_choice", "model_other", "model_options",
                 "model_options_for", "model_options_error")


def _fingerprint(api_key: str) -> str:
    """Which key the loaded model list belongs to, without keeping the key a second time."""
    return sha256(api_key.encode()).hexdigest()[:16]


def _load_models(api_key: str | None) -> None:
    owner = _fingerprint(api_key or "app")
    try:
        with st.spinner("Loading the models your key can use…"):
            st.session_state.model_options = list_models(api_key)
        st.session_state.model_options_error = None
    except LLMError as error:
        st.session_state.model_options = []
        st.session_state.model_options_error = str(error)
    st.session_state.model_options_for = owner


def _model_choices() -> list[str]:
    default = os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    loaded = st.session_state.get("model_options") or []
    return list(dict.fromkeys([default, *(loaded or SUGGESTED_MODELS), OTHER]))


def render_settings() -> tuple[str | None, str]:
    """Return the session's API key (None to use the app's) and model."""
    app_key = bool(os.environ.get("OPENAI_API_KEY"))
    typed = (st.session_state.get("api_key_input") or "").strip()
    with st.expander("OpenAI settings", expanded=not (typed or app_key)):
        show = st.toggle("Show API key", key="show_api_key")
        api_key = st.text_input(
            "OpenAI API key", type="default" if show else "password", key="api_key_input",
            placeholder="sk-…", autocomplete="off",
            help="Used only in this browser session to call OpenAI. It is not saved.",
        ).strip()
        if api_key:
            st.caption("Using your key.")
        elif app_key:
            st.caption("Using the app's key. Enter your own to use your account.")
        else:
            st.caption("Enter your key to generate outlines, quizzes and answers.")

        # Load the learner's models once per key they type; the app's key loads on request.
        if api_key and st.session_state.get("model_options_for") != _fingerprint(api_key):
            _load_models(api_key)
        elif not api_key and app_key and st.button("Load models for the app's key", key="load_app_models"):
            _load_models(None)
        if st.session_state.get("model_options_error"):
            st.error(st.session_state.model_options_error)

        choices = _model_choices()
        if st.session_state.get("model_choice") not in choices:
            st.session_state.model_choice = choices[0]
        choice = st.selectbox(
            "Model", choices, key="model_choice",
            help="The tutor needs a model that supports tool calls and structured outputs. "
                 "If a model fails, switch back to the default.",
        )
        model = choice
        if choice == OTHER:
            model = st.text_input("Model ID", key="model_other", placeholder="for example gpt-5.6-luna").strip()
            model = model or choices[0]
    return api_key or None, model
