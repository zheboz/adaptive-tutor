import json
import unittest
from unittest.mock import patch

from tutor.llm import LLMError
from tutor.materials.cards import MAX_DETAILS, MAX_POINTS, CardDraft, PointDraft, build_card
from tutor.materials.ingest import PdfPage


PAGES = [
    PdfPage(1, "Evaluation\npass@k counts a task as solved\nwhen any of k trials succeeds."),
    PdfPage(2, "pass^k needs all k trials to succeed, so it measures consistency."),
    PdfPage(3, "Unanswerable tasks check that the agent says it does not know."),
    PdfPage(4, "", error="unreadable"),
]


def point(title, page, quote, details=("A detail.",)):
    return PointDraft(title=title, explanation=f"{title} explained.", details=list(details), page=page, quote=quote)


class BuildCardTests(unittest.TestCase):
    def build(self, *drafts, source_ids=("p1", "p2", "p3")):
        with patch("tutor.materials.cards.generate_structured", side_effect=list(drafts)) as model:
            card = build_card("Evaluation", "Explain pass@k.", source_ids, PAGES)
        return card, model

    def test_points_keep_only_quotes_found_on_the_pages(self):
        card, model = self.build(CardDraft(points=[
            point("pass^k", "p2", "pass^k needs all k trials to succeed"),
            # Line breaks and curly quotes in the PDF text do not matter.
            point("pass@k", "p1", "counts a task as solved when any of k trials succeeds"),
            # Cited the wrong page: moved to the page that has the quote.
            point("Unanswerable", "p1", "agent says it does not know"),
            point("Invented", "p2", "pass@k is always higher than accuracy"),
            point("pass@k", "p1", "pass@k counts a task as solved"),          # same title again
        ]))
        self.assertIsNone(card.problem)
        # In page order, whatever order the model used.
        self.assertEqual([(p.title, p.source_id) for p in card.points],
                         [("pass@k", "p1"), ("pass^k", "p2"), ("Unanswerable", "p3")])
        self.assertEqual(card.points[0].details, ("A detail.",))
        request = json.loads(model.call_args.kwargs["content"])
        self.assertEqual(request["unit"], {"title": "Evaluation", "objective": "Explain pass@k."})
        self.assertEqual([page["id"] for page in request["pages"]], ["p1", "p2", "p3"])
        model.assert_called_once()

    def test_when_no_point_survives_the_model_is_told_why_once(self):
        card, model = self.build(
            CardDraft(points=[point("Invented", "p1", "a sentence that is not in the notes at all")]),
            CardDraft(points=[point("pass^k", "p2", "it measures consistency")]),
        )
        self.assertEqual([p.title for p in card.points], ["pass^k"])
        retry = json.loads(model.call_args.kwargs["content"])
        self.assertIn("Invented: the words of the quote", retry["rejected_last_time"][0])
        failed, model = self.build(*[CardDraft(points=[point("Invented", "p1", "not in the notes at all, sorry")])] * 2)
        self.assertEqual(failed.points, ())
        self.assertIn("No knowledge point could be checked against the pages", failed.problem)
        self.assertEqual(model.call_count, 2)

    def test_short_quotes_and_long_lists_are_trimmed(self):
        many = [point(f"Point {n}", "p2", "pass^k needs all k trials", details=["a", "b", "c", "d", " "])
                for n in range(MAX_POINTS + 2)]
        many.append(point("Tiny", "p2", "pass"))
        card, _ = self.build(CardDraft(points=many))
        self.assertEqual(len(card.points), MAX_POINTS)
        self.assertEqual(len(card.points[0].details), MAX_DETAILS)
        self.assertNotIn("Tiny", [p.title for p in card.points])

    def test_pages_without_text_or_points(self):
        card, model = self.build(source_ids=("p4", "p9"))
        self.assertEqual(card.problem, "These pages have no readable text.")
        model.assert_not_called()
        card, _ = self.build(CardDraft(points=[]), source_ids=("p1",))
        self.assertIn("no knowledge point to list", card.problem)

    def test_model_errors_reach_the_caller(self):
        with self.assertRaises(LLMError):
            self.build(LLMError("Could not reach OpenAI."))

    def test_symbols_and_stray_characters_in_the_pdf_text_do_not_matter(self):
        pages = [PdfPage(1, "SHORT-TERM · THE CONTEXT\nThis session\x7fs items are sent with every call."),
                 PdfPage(2, "短期记忆就是上下文窗口，每次调用都会发送。")]
        drafts = CardDraft(points=[
            point("Context", "p1", "This session's items are sent with every call."),
            point("Escaped", "p1", "SHORT-TERM \\u00b7 THE CONTEXT This session"),
            point("Partial word", "p1", "ession items are sent with every"),
            point("中文", "p2", "就是上下文窗口，每次调用"),
        ])
        with patch("tutor.materials.cards.generate_structured", return_value=drafts):
            card = build_card("Memory", "", ("p1", "p2"), pages)
        self.assertEqual([p.title for p in card.points], ["Escaped", "Context", "中文"])
        self.assertEqual(card.points[0].quote, "SHORT-TERM · THE CONTEXT This session")

    def test_a_sentence_read_across_interleaved_slide_columns_is_found(self):
        page = PdfPage(1, "SHORT-TERM · THE CONTEXT        LONG-TERM · THE STORE\n"
                          "This session's items: messages, tool      Facts, events and lessons in a file\n"
                          "calls, results and notes.                 or database that outlive the session.")
        drafts = CardDraft(points=[
            point("Short-term", "p1", "This session's items: messages, tool calls, results and notes."),
            point("Long-term", "p1", "Facts, events and lessons in a file or database that outlive the session."),
            # Real words from the page, but not in the order of any of its sentences.
            point("Scrambled", "p1", "lessons in a database that outlive messages and tool calls"),
        ])
        with patch("tutor.materials.cards.generate_structured", return_value=drafts):
            card = build_card("Memory", "", ("p1",), [page])
        self.assertEqual([p.title for p in card.points], ["Short-term", "Long-term"])
