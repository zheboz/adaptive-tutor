import json
import unittest
from unittest.mock import patch

from eval.baseline import BaselineAnswer, ask_baseline
from tutor.agent.qa import Citation
from tutor.assessment.retrieval import build_index
from tutor.llm import Trace, tracing
from tutor.materials.ingest import PdfPage


PAGES = [
    PdfPage(1, "Assignment\nAfter x = 2, the variable x holds the value 2."),
    PdfPage(2, "Updating\nThe statement x = x + 1 reads x, adds 1, and stores the result back in x."),
    PdfPage(3, "Loops\nThe loop for i in range(3) runs its body 3 times."),
]


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index(PAGES)

    def model(self, **fields):
        answer = BaselineAnswer(**{"citations": [], "missing_topic": None, **fields})
        return self.enterContext(patch("eval.baseline.generate_structured", return_value=answer))

    def test_answers_from_one_search_and_one_model_call(self):
        model = self.model(kind="answer", text=" It adds one to x. ", citations=[
            {"page": "p2", "quote": "reads x,  adds 1"}, {"page": "p2", "quote": "reads x, adds 1"},
        ])
        trace = Trace()
        with tracing(trace):
            reply = ask_baseline(self.index, "  What does the updating   statement do? ")

        self.assertEqual(reply.kind, "answer")
        self.assertEqual(reply.text, "It adds one to x.")
        self.assertEqual(reply.citations, (Citation("p2", "reads x, adds 1"),))
        model.assert_called_once()
        sent = json.loads(model.call_args.kwargs["content"])
        self.assertEqual(sent["question"], "What does the updating statement do?")
        self.assertEqual([p["page"] for p in sent["passages"]][0], "p2")
        self.assertEqual([s.name for s in trace.spans], ["tool:search_material"])

    def test_declines_and_names_the_missing_topic(self):
        self.model(kind="declined", text="The material covers loops, not recursion.", missing_topic=" recursion ")
        reply = ask_baseline(self.index, "What is recursion?")
        self.assertEqual((reply.kind, reply.missing_topic, reply.citations), ("declined", "recursion", ()))

    def test_still_asks_the_model_when_nothing_matches(self):
        model = self.model(kind="declined", text="Not covered.", missing_topic="recursion")
        ask_baseline(self.index, "recursion")
        self.assertEqual(json.loads(model.call_args.kwargs["content"])["passages"], [])

    def test_searches_with_the_whole_question_and_cannot_rephrase(self):
        # The agent can retry with the fragment "x = x + 1"; the baseline searches the question as asked,
        # whose single letters are not indexed and which does not appear verbatim in the material.
        model = self.model(kind="declined", text="Not covered.", missing_topic="updating")
        ask_baseline(self.index, "What does x = x + 1 do?")
        self.assertEqual(json.loads(model.call_args.kwargs["content"])["passages"], [])

    def test_rejects_an_empty_question(self):
        with self.assertRaises(ValueError):
            ask_baseline(self.index, "   ")


if __name__ == "__main__":
    unittest.main()
