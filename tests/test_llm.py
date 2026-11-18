import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openai import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import BaseModel

from tutor.llm import DEFAULT_MODEL, LLMError, generate_structured


class ExampleOutput(BaseModel):
    title: str


class StructuredCallTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True))
        self.sdk = self.enterContext(patch("tutor.llm.OpenAI"))
        self.parse = self.sdk.return_value.__enter__.return_value.responses.parse

    def request(self):
        return generate_structured(instructions="Make a title.", content="A lesson.", schema=ExampleOutput)

    def test_typed_output_and_routing(self):
        result = ExampleOutput(title="Variables")
        self.parse.return_value = SimpleNamespace(status="completed", output_parsed=result)
        os.environ["OPENAI_BASE_URL"] = "https://unrelated.invalid/"
        self.assertIs(self.request(), result)
        self.assertEqual(self.sdk.call_args.kwargs["base_url"], "https://api.openai.com/v1")
        self.parse.assert_called_once_with(
            model=DEFAULT_MODEL, instructions="Make a title.", input="A lesson.",
            text_format=ExampleOutput, store=False,
        )
        os.environ["OPENAI_MODEL"] = "user-selected-model"
        self.request()
        self.assertEqual(self.parse.call_args.kwargs["model"], "user-selected-model")

    def test_missing_key(self):
        del os.environ["OPENAI_API_KEY"]
        with self.assertRaisesRegex(LLMError, "OPENAI_API_KEY"):
            self.request()
        self.sdk.assert_not_called()

    def test_rejects_partial_or_missing_output(self):
        for status, value in (("incomplete", ExampleOutput(title="Part")), ("completed", None)):
            with self.subTest(status=status):
                self.parse.return_value = SimpleNamespace(status=status, output_parsed=value)
                with self.assertRaisesRegex(LLMError, "complete result"):
                    self.request()

    def test_sdk_error_details_do_not_reach_ui(self):
        sensitive_message = "private request content"
        for error, hint in (
            (AuthenticationError(sensitive_message, response=Mock(status_code=401), body=None), "credentials"),
            (RateLimitError(sensitive_message, response=Mock(status_code=429), body=None), "limit"),
            (APIConnectionError(message=sensitive_message, request=Mock()), "connection"),
        ):
            with self.subTest(error=type(error).__name__):
                self.parse.side_effect = error
                with self.assertRaisesRegex(LLMError, hint) as raised:
                    self.request()
                self.assertNotIn(sensitive_message, str(raised.exception))
