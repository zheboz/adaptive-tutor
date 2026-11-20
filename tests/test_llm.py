import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openai import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import BaseModel

from tutor.llm import (
    DEFAULT_MODEL, LLMError, ToolCall, Trace, call_with_tools, current_model, generate_structured, list_models,
    tracing, using,
)


class ExampleOutput(BaseModel):
    title: str


class StructuredCallTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(using("test-only"))
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
        self.assertEqual(self.sdk.call_args.kwargs["api_key"], "test-only")
        with using("test-only", "user-selected-model"):
            self.request()
        self.assertEqual(self.parse.call_args.kwargs["model"], "user-selected-model")

    def test_missing_key(self):
        with using(None), self.assertRaisesRegex(LLMError, "top of the page"):
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
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(using("test-only"))
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
        with using(None), self.assertRaisesRegex(LLMError, "top of the page"):
            self.call()
        self.sdk.assert_not_called()


class CredentialTests(unittest.TestCase):
    def setUp(self):
        # A server key in the environment must never be used: only the learner's key is.
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": "server-key", "OPENAI_MODEL": "server-model"},
                                     clear=True))
        self.sdk = self.enterContext(patch("tutor.llm.OpenAI"))
        self.parse = self.sdk.return_value.__enter__.return_value.responses.parse
        self.parse.return_value = SimpleNamespace(status="completed", output_parsed=ExampleOutput(title="T"))

    def request(self):
        return generate_structured(instructions="Make a title.", content="A lesson.", schema=ExampleOutput)

    def test_only_the_learners_key_and_model_are_used(self):
        with using("learner-key", "gpt-5.6-luna"):
            self.request()
            self.assertEqual(current_model(), "gpt-5.6-luna")
        self.assertEqual(self.sdk.call_args.kwargs["api_key"], "learner-key")
        self.assertEqual(self.parse.call_args.kwargs["model"], "gpt-5.6-luna")
        # Without a model the default is gpt-6-luna, whatever the environment says.
        with using("learner-key"):
            self.request()
        self.assertEqual(self.parse.call_args.kwargs["model"], "gpt-6-luna")
        self.assertNotIn("learner-key", os.environ.values())

    def test_without_the_learners_key_nothing_is_sent(self):
        for block in (using(None), using("", "gpt-6-luna")):
            with self.subTest(block=block), block, self.assertRaisesRegex(LLMError, "top of the page"):
                self.request()
        with self.assertRaisesRegex(LLMError, "top of the page"):
            self.request()
        self.sdk.assert_not_called()

    def test_background_threads_that_copy_the_context_use_the_session_key(self):
        import contextvars
        from concurrent.futures import ThreadPoolExecutor
        with using("learner-key", "gpt-6-luna"):
            context = contextvars.copy_context()
        with ThreadPoolExecutor(1) as pool:
            self.assertEqual(pool.submit(context.run, current_model).result(), "gpt-6-luna")
            self.assertEqual(pool.submit(current_model).result(), "gpt-6-luna")

    def test_model_list_keeps_chat_models_without_snapshots(self):
        models = self.sdk.return_value.__enter__.return_value.models.list
        models.return_value = [SimpleNamespace(id=i) for i in (
            "gpt-4.1-mini", "gpt-6-luna", "text-embedding-3-small", "gpt-4o-2024-08-06", "tts-1", "o3",
            "gpt-image-1", "gpt-5.6-luna", "gpt-live-1",
        )]
        self.assertEqual(list_models("learner-key"), ["gpt-4.1-mini", "gpt-5.6-luna", "gpt-6-luna", "o3"])
        self.assertEqual(self.sdk.call_args.kwargs["api_key"], "learner-key")
        models.side_effect = AuthenticationError("bad key", response=Mock(status_code=401), body=None)
        with self.assertRaisesRegex(LLMError, "credentials"):
            list_models("wrong-key")
