"""The OpenAI key and the model. The key is the server's: `OPENAI_API_KEY` in the environment, or in a
`.env` file at the project root (on Streamlit Cloud, a root-level secret of that name). Learners only
choose the model: in the first setup step, then in the settings at the top of the page. The field is
drawn in different places at different times, and Streamlit drops a widget's value while it is not
drawn, so its value is also kept in a plain session key.
"""

from hashlib import sha256
import os
from pathlib import Path

import streamlit as st

from tutor.llm import DEFAULT_MODEL, FALLBACK_MODEL, LLMError, list_models


OTHER = "Other…"
# Recommended models, newest first. Each was checked with structured outputs and tool calls, the two
# things the tutor needs. Pro models (about 50 s a call) and code-only models are left out here but
# still appear among the account's other models.
RECOMMENDED_MODELS = (
    "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra",
    "gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
    "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "gpt-4.1", "gpt-4.1-mini", "gpt-4o",
    "gpt-4o-mini",
)
_FIELDS = ("model_choice", "model_other")
# Read once, for values the environment does not already have.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NO_KEY = ("No OpenAI API key is set for this app. Set OPENAI_API_KEY in the environment or in the .env "
          "file at the project root, then restart the app.")
_SAVED = "saved_settings"
SETTINGS_KEYS = (*_FIELDS, _SAVED, "model_options", "model_options_for", "model_options_error")


def _fingerprint(api_key: str) -> str:
    """Which key the loaded model list belongs to, without keeping the key a second time."""
    return sha256(api_key.encode()).hexdigest()[:16]


def _load_models(api_key: str) -> None:
    try:
        with st.spinner("Loading the available models…"):
            st.session_state.model_options = list_models(api_key)
        st.session_state.model_options_error = None
    except LLMError as error:
        st.session_state.model_options = []
        st.session_state.model_options_error = str(error)
    st.session_state.model_options_for = _fingerprint(api_key)


def default_model() -> str:
    """gpt-6-luna, unless the key's account is known to lack it."""
    loaded = st.session_state.get("model_options") or []
    if not loaded or DEFAULT_MODEL in loaded:
        return DEFAULT_MODEL
    return FALLBACK_MODEL if FALLBACK_MODEL in loaded else loaded[0]


def _model_choices() -> list[str]:
    """The default first, then recommended models newest first, then the account's other models.

    Once the key's models are loaded, recommended models the account lacks are left out.
    """
    loaded = st.session_state.get("model_options") or []
    if loaded:
        ordered = [model for model in RECOMMENDED_MODELS if model in loaded]
        ordered += [model for model in loaded if model not in RECOMMENDED_MODELS]
    else:
        ordered = list(RECOMMENDED_MODELS)
    return list(dict.fromkeys([default_model(), *ordered, OTHER]))


def _label(model: str) -> str:
    return f"{model} (default)" if model == default_model() else model


def _restore() -> None:
    saved = st.session_state.get(_SAVED, {})
    for key in _FIELDS:
        if key not in st.session_state and key in saved:
            st.session_state[key] = saved[key]


def _save() -> None:
    saved = st.session_state.setdefault(_SAVED, {})
    for key in _FIELDS:
        if key in st.session_state:
            saved[key] = st.session_state[key]


def render_settings(horizontal: bool = False) -> None:
    """The model field; in the first step, beside a note on the key."""
    _restore()
    _ensure_models()
    if horizontal:
        model_column, _ = st.columns([2, 3])
    else:
        model_column = st.container()
    with model_column:
        render_model()
    if current_key() is None:
        st.error(NO_KEY)
    elif st.session_state.get("model_options_error"):
        st.error(st.session_state.model_options_error)
    _save()


def _value(key: str):
    """The field's latest value: its widget's, when drawn in the previous run, or the kept one."""
    if key in st.session_state:
        return st.session_state[key]
    return st.session_state.get(_SAVED, {}).get(key)


def _read_env_file(path: Path) -> dict[str, str]:
    """`NAME=value` lines; blank lines, comments and `export ` are allowed, quotes are removed."""
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        values[name.strip()] = value.strip().strip("\"'")
    return values


def current_key() -> str | None:
    """The server's OpenAI key, or None when none is set."""
    key = os.environ.get("OPENAI_API_KEY") or _read_env_file(ENV_FILE).get("OPENAI_API_KEY")
    return (key or "").strip() or None


def current_model() -> str:
    choice = _value("model_choice") or default_model()
    if choice != OTHER:
        return choice
    return (_value("model_other") or "").strip() or default_model()


def _ensure_models() -> None:
    """Load the models the key's account has, once per key."""
    api_key = current_key()
    if api_key and st.session_state.get("model_options_for") != _fingerprint(api_key):
        _load_models(api_key)


def render_model() -> str:
    """The model picker; with Other…, a field for any model ID."""
    choices = _model_choices()
    if st.session_state.get("model_choice") not in choices:
        st.session_state.model_choice = choices[0]
    choice = st.selectbox(
        "Model", choices, key="model_choice", format_func=_label,
        help=f"The default is {DEFAULT_MODEL} ({FALLBACK_MODEL} when the account does not have it); newer "
             "models follow. The tutor needs a model that supports tool calls and structured outputs; if a "
             "model fails, switch back to the default.",
    )
    if choice != OTHER:
        return choice
    model = st.text_input("Model ID", key="model_other", placeholder="for example gpt-5.6-luna").strip()
    return model or default_model()
