"""OpenAI Responses client for typed model outputs and tool calls, with per-call tracing."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import re
import time
from typing import Any, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)
DEFAULT_MODEL = "gpt-4.1-mini"
# Details of failed requests go to the server log (the terminal running the app), never to the page.
logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """A model request failed; the message is safe to show to the learner."""


@dataclass
class Span:
    """One model call or tool call within a run."""

    name: str
    seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    detail: str = ""
    error: str | None = None


@dataclass
class Trace:
    """The spans of one run, such as one diagnosis session."""

    spans: list[Span] = field(default_factory=list)

    @property
    def model_calls(self) -> int:
        return sum(span.name.startswith("model:") for span in self.spans)

    @property
    def total_tokens(self) -> int:
        return sum(span.input_tokens + span.output_tokens for span in self.spans)

    @property
    def model_seconds(self) -> float:
        return sum(span.seconds for span in self.spans if span.name.startswith("model:"))


_active_trace: ContextVar[Trace | None] = ContextVar("active_trace", default=None)


@dataclass(frozen=True)
class Credentials:
    """The learner's own key and model for this session. The app has no key of its own."""

    api_key: str | None = None
    model: str | None = None


# Per-session credentials, entered by the learner. They are never read from or written to the process
# environment, which every session of the app shares; background threads that copy the context see them.
_active_credentials: ContextVar[Credentials] = ContextVar("active_credentials", default=Credentials())


@contextmanager
def using(api_key: str | None = None, model: str | None = None) -> Iterator[Credentials]:
    """Make model calls inside the block use this key and model."""
    credentials = Credentials(api_key or None, model or None)
    token = _active_credentials.set(credentials)
    try:
        yield credentials
    finally:
        _active_credentials.reset(token)


def current_model() -> str:
    return _active_credentials.get().model or DEFAULT_MODEL


def _api_key() -> str | None:
    return _active_credentials.get().api_key


def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url="https://api.openai.com/v1", timeout=60.0, max_retries=1)


@contextmanager
def tracing(trace: Trace) -> Iterator[Trace]:
    """Record every model call made inside the block, including calls in nested helpers."""
    token = _active_trace.set(trace)
    try:
        yield trace
    finally:
        _active_trace.reset(token)


def record_span(span: Span) -> None:
    trace = _active_trace.get()
    if trace is not None:
        trace.spans.append(span)


def _safe_error(exc: Exception) -> LLMError | None:
    """Translate SDK failures without exposing request content or provider details."""
    if isinstance(exc, AuthenticationError):
        return LLMError("OpenAI rejected the credentials. Check the app's API key.")
    if isinstance(exc, RateLimitError):
        return LLMError("OpenAI reported a usage limit. Check your quota or try again later.")
    if isinstance(exc, APIConnectionError):
        return LLMError("Could not reach OpenAI. Check your connection and try again.")
    if isinstance(exc, APIStatusError):
        return LLMError(f"OpenAI returned HTTP {exc.status_code}. Check model access or retry later.")
    if isinstance(exc, ValidationError):
        return LLMError("The model returned data that did not match the requested format.")
    if isinstance(exc, (OpenAIError, ValueError)):
        return LLMError("The OpenAI request failed. Check the model configuration and retry.")
    return None


def _request(name: str, send: Callable[[OpenAI, str], Any]) -> Any:
    """Send one request with this session's key and model, and record its span."""
    api_key = _api_key()
    if not api_key:
        raise LLMError("Enter your OpenAI API key in the sidebar to use the tutor.")
    model = current_model()
    start = time.perf_counter()
    try:
        with _client(api_key) as client:
            response = send(client, model)
    except Exception as exc:
        error = _safe_error(exc)
        if error is None:
            raise
        logger.warning("OpenAI request %s failed: %s: %s", name, type(exc).__name__, exc)
        record_span(Span(name, time.perf_counter() - start, error=str(error)))
        raise error from None
    usage = getattr(response, "usage", None)
    record_span(Span(
        name, time.perf_counter() - start,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    ))
    return response


def generate_structured(*, instructions: str, content: str, schema: type[T]) -> T:
    """Request a validated model result using credentials in the process environment."""
    response = _request(f"model:{schema.__name__}", lambda client, model: client.responses.parse(
        model=model,
        instructions=instructions,
        input=content,
        text_format=schema,
        store=False,
    ))
    result = response.output_parsed
    if response.status != "completed" or not isinstance(result, schema):
        raise LLMError("The model did not return a complete result in the requested format.")
    return result


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolTurn:
    """The tools the model chose, and the output items to append to the conversation."""

    calls: tuple[ToolCall, ...]
    items: tuple[dict[str, Any], ...]


def call_with_tools(
    *, instructions: str, items: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]], name: str = "model:agent",
) -> ToolTurn:
    """Ask the model for exactly one tool call. Nothing is stored by OpenAI between turns."""
    response = _request(name, lambda client, model: client.responses.create(
        model=model,
        instructions=instructions,
        input=list(items),
        tools=list(tools),
        tool_choice="required",
        parallel_tool_calls=False,
        store=False,
    ))
    if response.status != "completed":
        raise LLMError("The model did not return a complete result.")
    calls = []
    output = []
    for item in response.output:
        if item.type == "function_call":
            try:
                arguments = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                raise LLMError("The model returned tool arguments that were not valid JSON.") from None
            if not isinstance(arguments, dict):
                raise LLMError("The model returned tool arguments in an unexpected format.")
            calls.append(ToolCall(item.call_id, item.name, arguments))
            output.append({
                "type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments,
            })
        elif item.type == "message":
            text = "".join(getattr(part, "text", "") for part in item.content)
            if text:
                output.append({"role": "assistant", "content": text})
    if not calls:
        raise LLMError("The model did not choose a tool.")
    return ToolTurn(tuple(calls), tuple(output))


# Models that cannot answer in text with tools, and dated snapshots, are left out of the picker.
_NOT_CHAT = ("embedding", "tts", "whisper", "dall-e", "image", "audio", "realtime", "moderation",
             "transcribe", "babbage", "davinci", "sora", "search", "gpt-live")
_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def list_models(api_key: str | None = None) -> list[str]:
    """Chat model IDs the key can use, for a model picker. Errors are safe to show."""
    api_key = api_key or _api_key()
    if not api_key:
        raise LLMError("Enter your OpenAI API key in the sidebar to use the tutor.")
    try:
        with _client(api_key) as client:
            ids = [model.id for model in client.models.list()]
    except Exception as exc:
        error = _safe_error(exc)
        if error is None:
            raise
        logger.warning("Listing OpenAI models failed: %s: %s", type(exc).__name__, exc)
        raise error from None
    return sorted(i for i in ids if not any(part in i for part in _NOT_CHAT) and not _SNAPSHOT.search(i))
