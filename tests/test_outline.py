import json
import unittest
from unittest.mock import patch

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
        chunks = [chunk for call in generate.call_args_list for chunk in json.loads(call.kwargs["content"])]
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
