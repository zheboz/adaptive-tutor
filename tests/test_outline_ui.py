from html import escape
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_pdf_preview import APP, make_pdf, previewed_pdf
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


def upload(app, *pages):
    document = make_pdf(*pages)
    app.file_uploader[0].set_value(("lesson.pdf", document, "application/pdf")).run()
    return document


def button(app, label):
    return next(widget for widget in app.button if widget.label == label)


class OutlineUITests(unittest.TestCase):
    def setUp(self):
        self.topic = Topic(
            title="Track a running total",
            summary="Update a counter while n < limit.",
            source_ids=["p2"],
        )
        self.outline = Outline(topics=[self.topic])
        self.app = AppTest.from_file(APP)

    @patch("tutor.materials.outline.generate_outline")
    def test_generate_once_and_follow_source(self, generate):
        generate.return_value = self.outline
        self.app.run()
        document = upload(self.app, "Course introduction", "Running totals")
        generate.assert_not_called()
        button(self.app, "Generate outline").click().run()
        generate.assert_called_once()
        self.assertIn(self.topic.title, self.app.html[0].value)
        self.assertIn(escape(self.topic.summary), self.app.html[0].value)
        button(self.app, "Page 2").click().run()
        self.assertEqual(self.app.selectbox[0].value, 2)
        self.assertEqual(previewed_pdf(self.app), (document, [2]))
        self.assertEqual(self.app.code[0].value.strip(), "Running totals")
        self.app.selectbox[0].select(1).run()
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_replacement_and_removal_drop_outline(self, generate):
        generate.return_value = self.outline
        self.app.run()
        upload(self.app, "First page", "Running totals")
        button(self.app, "Generate outline").click().run()
        self.assertIn("Page 2", [item.label for item in self.app.button])
        upload(self.app, "")
        self.assertNotIn("Page 2", [item.label for item in self.app.button])
        self.assertTrue(button(self.app, "Generate outline").disabled)
        self.app.file_uploader[0].clear().run()
        self.assertNotIn("Page 2", [item.label for item in self.app.button])
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_failed_request_can_be_retried_explicitly(self, generate):
        generate.side_effect = [LLMError("The request failed."), self.outline]
        self.app.run()
        upload(self.app, "Course introduction", "Running totals")
        button(self.app, "Generate outline").click().run()
        self.assertTrue(self.app.error)
        self.assertFalse(self.app.exception)
        button(self.app, "Generate outline").click().run()
        self.assertEqual(generate.call_count, 2)
        self.assertFalse(self.app.error)
        self.assertIn("Page 2", [item.label for item in self.app.button])
