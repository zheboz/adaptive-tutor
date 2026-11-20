"""The learner's own OpenAI key and model, in the sidebar. The app has no key of its own.

The key stays in this browser session only: it is not saved, and never written to the process
environment shared by every session.
"""

from hashlib import sha256

import streamlit as st

from tutor.llm import DEFAULT_MODEL, LLMError, list_models


OTHER = "Other…"
# Recommended models, newest first. Each was checked with structured outputs and tool calls, the two
# things the tutor needs. Pro models (about 50 s a call) and code-only models are left out here but
# still appear among the learner's other models once their key is entered.
RECOMMENDED_MODELS = (
    "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra",
    "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
    "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "gpt-4.1", "gpt-4o", "gpt-4o-mini",
)
SETTINGS_KEYS = ("api_key_input", "show_api_key", "model_choice", "model_other", "model_options",
                 "model_options_for", "model_options_error")


def _fingerprint(api_key: str) -> str:
    """Which key the loaded model list belongs to, without keeping the key a second time."""
    return sha256(api_key.encode()).hexdigest()[:16]


def _load_models(api_key: str) -> None:
    try:
        with st.spinner("Loading the models your key can use…"):
            st.session_state.model_options = list_models(api_key)
        st.session_state.model_options_error = None
    except LLMError as error:
        st.session_state.model_options = []
        st.session_state.model_options_error = str(error)
    st.session_state.model_options_for = _fingerprint(api_key)


def _model_choices() -> list[str]:
    """The default first, then recommended models newest first, then the account's other models.

    Once the learner's key is loaded, recommended models their account lacks are left out.
    """
    loaded = st.session_state.get("model_options") or []
    if loaded:
        ordered = [model for model in RECOMMENDED_MODELS if model in loaded]
        ordered += [model for model in loaded if model not in RECOMMENDED_MODELS]
    else:
        ordered = list(RECOMMENDED_MODELS)
    return list(dict.fromkeys([DEFAULT_MODEL, *ordered, OTHER]))


def _label(model: str) -> str:
    return f"{model} (default)" if model == DEFAULT_MODEL else model


def render_settings() -> tuple[str | None, str]:
    """Return the learner's API key (None until entered) and model."""
    typed = (st.session_state.get("api_key_input") or "").strip()
    with st.expander("OpenAI settings", expanded=not typed):
        show = st.toggle("Show API key", key="show_api_key")
        api_key = st.text_input(
            "OpenAI API key", type="default" if show else "password", key="api_key_input",
            placeholder="sk-…", autocomplete="off",
            help="Used only in this browser session to call OpenAI. It is not saved.",
        ).strip()
        if api_key:
            st.caption("Using your key.")
        else:
            st.caption("Enter your key to generate outlines, quizzes and answers.")

        # Load the learner's models once per key they enter.
        if api_key and st.session_state.get("model_options_for") != _fingerprint(api_key):
            _load_models(api_key)
        if api_key and st.session_state.get("model_options_error"):
            st.error(st.session_state.model_options_error)

        choices = _model_choices()
        if st.session_state.get("model_choice") not in choices:
            st.session_state.model_choice = DEFAULT_MODEL
        choice = st.selectbox(
            "Model", choices, key="model_choice", format_func=_label,
            help=f"Newest models are listed first after the default, {DEFAULT_MODEL}. The tutor needs a model "
                 "that supports tool calls and structured outputs; if a model fails, switch back to the default.",
        )
        model = choice
        if choice == OTHER:
            model = st.text_input("Model ID", key="model_other", placeholder="for example gpt-5.6-luna").strip()
            model = model or DEFAULT_MODEL
    return api_key or None, model
