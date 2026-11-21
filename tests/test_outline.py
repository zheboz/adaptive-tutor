import json
import threading
import time
import unittest
from unittest.mock import patch

from tutor.materials import outline as outline_module
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline, OutlineError, Topic, generate_outline


class OutlineTests(unittest.TestCase):
    @patch("tutor.materials.outline.generate_structured")
    def test_short_document_keeps_physical_page_ids_and_ignores_unreadable_pages(self, generate):
        pages = [
            PdfPage(1, "Assign a value."),
            PdfPage(2, "  "),
            PdfPage(3, "Unreliable content", "Read error"),
            PdfPage(4, "Update a value."),
        ]
        generate.return_value = Outline(topics=[
            Topic(title=" Update  variables ", summary="Trace a value. ", source_ids=["p4", "p1", "p4"]),
        ])
        outline = generate_outline(pages)
        generate.assert_called_once()
        args = generate.call_args.kwargs
        self.assertIs(args["schema"], Outline)
        self.assertEqual(json.loads(args["content"]), [
            {"id": "p1", "text": "Assign a value."}, {"id": "p4", "text": "Update a value."}
        ])
        self.assertEqual(outline.topics, [
            Topic(title="Update variables", summary="Trace a value.", source_ids=["p1", "p4"])
        ])

    @patch("tutor.materials.outline._BATCH_CHARS", 8)
    @patch("tutor.materials.outline.generate_structured")
    def test_long_pages_keep_all_text_and_duplicate_topics_merge(self, generate):
        pages = [PdfPage(1, "abcd\nefghijklmnop"), PdfPage(2, "last")]

        def summarize(*, instructions, content, schema):
            chunks = json.loads(content)
            topic = Topic(
                title="Loops",
                summary="Trace updates.",
                source_ids=[chunk["id"] for chunk in chunks],
            )
            return Outline(topics=[topic])

        generate.side_effect = summarize
        result = generate_outline(pages)
        self.assertGreater(generate.call_count, 1)
        # Batches are read in parallel, so the calls may come in any order; each batch is sent once.
        sent = sorted(call.kwargs["content"] for call in generate.call_args_list)
        batches = list(outline_module._batches(pages))
        self.assertEqual(sent, sorted(json.dumps(batch, ensure_ascii=False) for batch in batches))
        chunks = [chunk for batch in batches for chunk in batch]
        for page in pages:
            self.assertEqual("".join(c["text"] for c in chunks if c["id"] == f"p{page.number}"), page.text)
        self.assertEqual(result.topics, [Topic(title="Loops", summary="Trace updates.", source_ids=["p1", "p2"])])

    @patch("tutor.materials.outline.generate_structured")
    def test_no_readable_text_never_calls_model(self, generate):
        with self.assertRaises(OutlineError):
            generate_outline([PdfPage(1, ""), PdfPage(2, "", "Read error")])
        generate.assert_not_called()

    @patch("tutor.materials.outline._BATCH_PAGES", 1)
    @patch("tutor.materials.outline.generate_structured")
    def test_refuses_empty_topics_missing_content_and_invalid_citations(self, generate):
        pages = [PdfPage(1, "First lesson."), PdfPage(2, "Other lesson.")]
        for topics in (
            [],
            [Topic(title=" ", summary="Text.", source_ids=["p1"])],
            [Topic(title="Lesson", summary="", source_ids=["p1"])],
            [Topic(title="Lesson", summary="Text.", source_ids=[])],
            [Topic(title="Lesson", summary="Text.", source_ids=["p2"])],  # Real page, wrong batch.
        ):
            with self.subTest(topics=topics):
                generate.return_value = Outline(topics=topics)
                with self.assertRaises(OutlineError):
                    generate_outline(pages)


class ParallelOutlineTests(unittest.TestCase):
    """Batches are read at the same time and reported in page order."""

    def setUp(self):
        self.enterContext(patch("tutor.materials.outline._BATCH_PAGES", 1))
        self.pages = [PdfPage(n, f"Lesson {n}.") for n in (1, 2, 3)]
        self.later_batches_done = threading.Event()
        self.lock = threading.Lock()
        self.finished = []
        self.fail_second = False

    def summarize(self, *, instructions, content, schema):
        page = json.loads(content)[0]["id"]
        if page == "p1":
            # The first batch is the slowest: it ends after the other two.
            self.later_batches_done.wait(5)
            time.sleep(0.05)
        else:
            with self.lock:
                self.finished.append(page)
                if len(self.finished) == 2:
                    self.later_batches_done.set()
        if page == "p2" and self.fail_second:
            raise OutlineError("A topic cited a missing or unreadable page. Please try again.")
        return Outline(topics=[Topic(title=f"Topic {page}", summary="Text.", source_ids=[page])])

    def test_progress_lists_topics_in_page_order_while_later_batches_finish_first(self):
        reports = []
        with patch("tutor.materials.outline.generate_structured", side_effect=self.summarize) as generate:
            result = generate_outline(self.pages, lambda topics, done, total: reports.append(
                ([t.title for t in topics], done, total)))
        self.assertEqual(generate.call_count, 3)
        titles = [t.title for t in result.topics]
        self.assertEqual(titles, ["Topic p1", "Topic p2", "Topic p3"])
        self.assertEqual(reports[0], ([], 0, 3))
        self.assertEqual(reports[-1], (titles, 3, 3))
        # Until the first batch is done, nothing is shown, although later batches are finished.
        self.assertIn(([], 2, 3), reports)
        for shown, done, total in reports:
            self.assertEqual(shown, titles[:len(shown)])
        self.assertEqual([done for _, done, _ in reports], sorted({done for _, done, _ in reports}))

    def test_a_failed_batch_fails_the_outline(self):
        self.fail_second = True
        with patch("tutor.materials.outline.generate_structured", side_effect=self.summarize):
            with self.assertRaises(OutlineError):
                generate_outline(self.pages)
