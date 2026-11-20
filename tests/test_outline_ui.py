from html import escape
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_pdf_preview import APP, button, make_pdf, previewed_pdf
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


def upload(app, *pages):
    document = make_pdf(*pages)
    app.file_uploader[0].set_value(("lesson.pdf", document, "application/pdf")).run()
    return document


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
    def test_generated_once_on_upload_and_follow_source(self, generate):
        generate.return_value = self.outline
        self.app.run()
        generate.assert_not_called()
        document = upload(self.app, "Course introduction", "Running totals")
        # No button: the outline is the only next step, so it is generated as soon as the PDF is in.
        generate.assert_called_once()
        self.assertNotIn("Generate outline", [item.label for item in self.app.button])
        topic_html = self.app.main.container("outline_panel").html[0].value
        self.assertIn(self.topic.title, topic_html)
        self.assertIn(escape(self.topic.summary), topic_html)
        button(self.app, "Page 2").click().run()
        self.assertEqual(self.app.selectbox(key="pdf_page_number").value, 2)
        self.assertEqual(previewed_pdf(self.app), (document, [2]))
        self.assertEqual(self.app.code[0].value.strip(), "Running totals")
        self.app.selectbox(key="pdf_page_number").select(1).run()
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_replacement_and_removal_drop_outline(self, generate):
        generate.return_value = self.outline
        self.app.run()
        upload(self.app, "First page", "Running totals")
        self.assertIn("Page 2", [item.label for item in self.app.button])
        upload(self.app, "")
        self.assertNotIn("Page 2", [item.label for item in self.app.button])
        self.assertIn("no readable text", self.app.main.container("outline_panel").warning[0].value)
        self.app.file_uploader[0].clear().run()
        self.assertNotIn("Page 2", [item.label for item in self.app.button])
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_a_failed_request_waits_for_try_again(self, generate):
        generate.side_effect = [LLMError("The request failed."), self.outline]
        self.enterContext(patch("tutor.ui.settings.list_models", return_value=[]))
        self.enterContext(patch("tutor.ui.units.start_planning"))
        self.app.run()
        self.app.text_input(key="api_key_input").set_value("sk-learner").run()
        upload(self.app, "Course introduction", "Running totals")
        self.assertEqual(self.app.main.container("outline_panel").error[0].value, "The request failed.")
        self.assertIn("could not be generated", self.app.main.container("steps").caption[0].value)
        # Other interactions do not repeat the failed request.
        self.app.selectbox(key="pdf_page_number").select(1).run()
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(self.app.exception)
        button(self.app, "Try again").click().run()
        self.assertEqual(generate.call_count, 2)
        self.assertFalse(self.app.error)
        self.assertIn("Page 2", [item.label for item in self.app.button])

    @patch("tutor.materials.outline.generate_outline")
    def test_without_a_key_the_outline_waits_for_it(self, generate):
        generate.side_effect = LLMError("Enter your OpenAI API key at the top of the page to use the tutor.")
        self.app.run()
        upload(self.app, "Course introduction", "Running totals")
        self.assertIn("Enter your OpenAI API key at the top of the page",
                      self.app.main.container("outline_panel").info[0].value)
        self.assertNotIn("Try again", [item.label for item in self.app.button])
        self.assertNotIn("outline_error", self.app.session_state)
