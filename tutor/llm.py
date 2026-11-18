"""OpenAI Responses client for typed model outputs."""

import os
from typing import TypeVar

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


class LLMError(RuntimeError):
    """A model request failed; the message is safe to show to the learner."""


def generate_structured(*, instructions: str, content: str, schema: type[T]) -> T:
    """Request a validated model result using credentials in the process environment."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise LLMError("Set OPENAI_API_KEY in the app environment before using the model.")
    model = os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    try:
        with OpenAI(base_url="https://api.openai.com/v1", timeout=60.0, max_retries=1) as client:
            response = client.responses.parse(
                model=model,
                instructions=instructions,
                input=content,
                text_format=schema,
                store=False,
            )
    except AuthenticationError:
        raise LLMError("OpenAI rejected the credentials. Check the app's API key.") from None
    except RateLimitError:
        raise LLMError("OpenAI reported a usage limit. Check your quota or try again later.") from None
    except APIConnectionError:
        raise LLMError("Could not reach OpenAI. Check your connection and try again.") from None
    except APIStatusError as exc:
        raise LLMError(f"OpenAI returned HTTP {exc.status_code}. Check model access or retry later.") from None
    except ValidationError:
        raise LLMError("The model returned data that did not match the requested format.") from None
    except (OpenAIError, ValueError):
        raise LLMError("The OpenAI request failed. Check the model configuration and retry.") from None

    result = response.output_parsed
    if response.status != "completed" or not isinstance(result, schema):
        raise LLMError("The model did not return a complete result in the requested format.")
    return result
