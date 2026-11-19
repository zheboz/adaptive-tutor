import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openai import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import BaseModel

from tutor.llm import DEFAULT_MODEL, LLMError, ToolCall, Trace, call_with_tools, generate_structured, tracing


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

    def test_trace_records_usage_and_failures(self):
        self.parse.return_value = SimpleNamespace(
            status="completed", output_parsed=ExampleOutput(title="Loops"),
            usage=SimpleNamespace(input_tokens=120, output_tokens=8),
        )
        trace = Trace()
        self.request()  # outside a trace: nothing is recorded
        with tracing(trace):
            self.request()
            self.parse.side_effect = RateLimitError("quota", response=Mock(status_code=429), body=None)
            with self.assertRaises(LLMError):
                self.request()
        self.assertEqual([span.name for span in trace.spans], ["model:ExampleOutput"] * 2)
        self.assertEqual((trace.spans[0].input_tokens, trace.spans[0].output_tokens), (120, 8))
        self.assertIn("limit", trace.spans[1].error)
        self.assertEqual((trace.model_calls, trace.total_tokens), (2, 128))


def function_call(call_id, name, arguments):
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=arguments)


class ToolCallTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}, clear=True))
        self.sdk = self.enterContext(patch("tutor.llm.OpenAI"))
        self.create = self.sdk.return_value.__enter__.return_value.responses.create
        self.tools = [{"type": "function", "name": "finish", "parameters": {}}]

    def respond(self, *output, status="completed"):
        self.create.return_value = SimpleNamespace(
            status=status, output=list(output), usage=SimpleNamespace(input_tokens=50, output_tokens=10),
        )

    def call(self):
        return call_with_tools(instructions="Diagnose.", items=[{"role": "user", "content": "Go."}], tools=self.tools)

    def test_one_required_tool_call_without_stored_state(self):
        self.respond(
            SimpleNamespace(type="message", content=[SimpleNamespace(text="Checking assignment first.")]),
            function_call("c1", "ask_question", '{"unit_id": "unit-1", "reason": "Start."}'),
        )
        trace = Trace()
        with tracing(trace):
            result = self.call()
        self.assertEqual(result.calls, (ToolCall("c1", "ask_question", {"unit_id": "unit-1", "reason": "Start."}),))
        self.assertEqual(result.items[0], {"role": "assistant", "content": "Checking assignment first."})
        self.assertEqual(result.items[1]["call_id"], "c1")
        kwargs = self.create.call_args.kwargs
        self.assertEqual((kwargs["tool_choice"], kwargs["parallel_tool_calls"], kwargs["store"]),
                         ("required", False, False))
        self.assertEqual(kwargs["tools"], self.tools)
        self.assertEqual([(s.name, s.input_tokens) for s in trace.spans], [("model:agent", 50)])

    def test_malformed_or_missing_tool_calls(self):
        for output, status, hint in (
            ([function_call("c1", "finish", "{not json")], "completed", "valid JSON"),
            ([function_call("c1", "finish", "[1]")], "completed", "unexpected format"),
            ([SimpleNamespace(type="message", content=[SimpleNamespace(text="Done.")])], "completed", "did not choose"),
            ([function_call("c1", "finish", "{}")], "incomplete", "complete result"),
        ):
            with self.subTest(hint=hint):
                self.respond(*output, status=status)
                with self.assertRaisesRegex(LLMError, hint):
                    self.call()

    def test_missing_key_stops_before_a_request(self):
        del os.environ["OPENAI_API_KEY"]
        with self.assertRaisesRegex(LLMError, "OPENAI_API_KEY"):
            self.call()
        self.sdk.assert_not_called()
