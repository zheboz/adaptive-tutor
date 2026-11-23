from html import escape
import threading
from unittest.mock import patch

from tests.test_pdf_preview import button, previewed_pdf
from tests.ui_helpers import UITestCase, add_material, begin, go_to_step, labels
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


class MaterialStepTests(UITestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch("tutor.ui.units.start_planning"))
        self.generate = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        self.generate.return_value = Outline(topics=[Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])
        self.app = self.new_app()

    def test_the_first_step_takes_the_model_and_the_pdf_then_opens_topics(self):
        app = self.app
        self.assertFalse(app.sidebar.children)
        self.assertEqual(app.main.container("material_upload").file_uploader[0].label, "PDF to study")
        # The key is the app's own: the learner only picks the model.
        self.assertTrue(app.main.container("material_settings").selectbox(key="model_choice"))
        self.assertFalse(app.text_input)
        # Only the first step can be opened, and Next waits for the PDF.
        self.assertEqual([b.disabled for b in app.main.container("steps").button], [False, True, True, True])
        self.assertTrue(app.button(key="material_next").disabled)
        self.assertIn("To continue, add a PDF.", [c.value for c in app.caption])

        add_material(app, "First page", "", "Third page")
        self.assertIn("lesson.pdf · 3 pages, 2 with readable text", app.success[0].value)
        self.assertFalse(app.button(key="material_next").disabled)
        # The topics are listed in the background as soon as there is a PDF.
        self.assertIn("outline_job", app.session_state)
        app.button(key="material_next").click().run()
        self.assertEqual(app.session_state["setup_step"], 2)
        self.assertIn("Loops", app.main.container("outline_panel").html[0].value)
        # Coming back to Topics does not ask again.
        calls = self.generate.call_count
        go_to_step(app, 1)
        go_to_step(app, 2)
        self.assertEqual(self.generate.call_count, calls)
        self.assertIn("✓ Material", labels(app))
        self.assertFalse(app.exception)

    def test_a_damaged_pdf_is_reported_and_removing_it_clears_the_material(self):
        app = self.app
        app.file_uploader[0].set_value(("lesson.pdf", b"damaged", "application/pdf")).run()
        self.assertTrue(app.error)
        self.assertNotIn("pdf_bytes", app.session_state)
        self.assertTrue(app.button(key="material_next").disabled)
        add_material(app, "Fine")
        self.assertFalse(app.error)
        app.file_uploader[0].clear().run()
        self.assertFalse(app.success)
        self.assertNotIn("pdf_bytes", app.session_state)
        self.assertFalse(app.exception)

    def test_the_pdf_is_kept_when_the_learner_comes_back_to_the_first_step(self):
        app = self.app
        begin(app, "Loops: range(3).")
        go_to_step(app, 1)
        # The upload widget is empty again, but the material is still there.
        self.assertIn("lesson.pdf · 1 page", app.success[0].value)
        self.assertIn("Choose another PDF above to replace it.", [c.value for c in app.caption])
        app.button(key="material_next").click().run()
        self.generate.assert_called_once()
        self.assertIn("Loops", app.main.container("outline_panel").html[0].value)


class OutlineUITests(UITestCase):
    def setUp(self):
        super().setUp()
        self.topic = Topic(
            title="Track a running total",
            summary="Update a counter while n < limit.",
            source_ids=["p2"],
        )
        self.outline = Outline(topics=[self.topic])
        self.app = self.new_app()

    @patch("tutor.materials.outline.generate_outline")
    def test_generated_once_when_topics_open_and_page_links_open_a_window(self, generate):
        generate.return_value = self.outline
        document = begin(self.app, "Course introduction", "Running totals")
        # No button: the outline is the only next step, so it is made as soon as Topics opens.
        generate.assert_called_once()
        self.assertNotIn("Generate outline", labels(self.app))
        topic_html = self.app.main.container("outline_panel").html[0].value
        self.assertIn(self.topic.title, topic_html)
        self.assertIn(escape(self.topic.summary), topic_html)
        # There is no reader during setup, so the page opens in a window.
        self.assertFalse(self.app.get("component_instance"))
        button(self.app, "Page 2").click().run()
        self.assertEqual(previewed_pdf(self.app), (document, [2]))
        self.assertIn("Running totals", self.app.code[0].value)
        self.app.run()
        self.assertFalse(self.app.get("component_instance"))
        go_to_step(self.app, 1)
        go_to_step(self.app, 2)
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_replacement_drops_the_outline(self, generate):
        generate.return_value = self.outline
        begin(self.app, "First page", "Running totals")
        self.assertIn("Page 2", labels(self.app))
        go_to_step(self.app, 1)
        begin(self.app, "")
        self.assertNotIn("Page 2", labels(self.app))
        self.assertIn("no readable text", self.app.warning[0].value)
        generate.assert_called_once()
        self.assertFalse(self.app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_a_failed_request_waits_for_try_again(self, generate):
        generate.side_effect = [LLMError("The request failed."), self.outline]
        self.enterContext(patch("tutor.ui.units.start_planning"))
        begin(self.app, "Course introduction", "Running totals")
        self.assertEqual(self.app.error[0].value, "The request failed.")
        # Other interactions do not repeat the failed request.
        go_to_step(self.app, 1)
        go_to_step(self.app, 2)
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(self.app.exception)
        button(self.app, "Try again").click().run()
        self.assertEqual(generate.call_count, 2)
        self.assertFalse(self.app.error)
        self.assertIn("Page 2", labels(self.app))

    @patch("tutor.materials.outline.generate_outline")
    def test_topics_found_so_far_are_shown_while_the_rest_is_read(self, generate):
        self.enterContext(patch("tutor.ui.units.start_planning"))
        rest_read = threading.Event()

        def slow(pages, on_progress):
            on_progress([self.topic], 1, 2)
            rest_read.wait(5)
            return self.outline

        generate.side_effect = slow
        # Not `begin`, which waits for the outline.
        add_material(self.app, "Course introduction", "Running totals")
        self.app.button(key="material_next").click().run()
        try:
            progress = "\n".join(h.value for h in self.app.html)
            self.assertIn("The tutor is reading your PDF", progress)
            self.assertIn("Read 1 of 2 parts of your PDF", progress)
            self.assertIn(f"1. {escape(self.topic.title)}", progress)
            # Marking topics waits until all are listed; going back is possible.
            self.assertFalse(self.app.checkbox)
            self.assertIn("← Back", labels(self.app))
        finally:
            rest_read.set()
        self.app.run()
        self.assertIn(self.topic.title, self.app.main.container("outline_panel").html[0].value)
        self.assertTrue(self.app.checkbox)
        generate.assert_called_once()

    @patch("tutor.materials.outline.generate_outline")
    def test_without_a_key_nothing_is_sent_and_the_page_says_how_to_set_one(self, generate):
        generate.return_value = self.outline
        del self.env["OPENAI_API_KEY"]
        add_material(self.app, "Course introduction", "Running totals")
        settings = self.app.main.container("material_settings")
        self.assertIn("No OpenAI API key is set for this app", settings.error[0].value)
        self.assertTrue(self.app.button(key="material_next").disabled)
        self.assertNotIn("outline_job", self.app.session_state)
        generate.assert_not_called()
        # Once the key is set, the outline starts.
        self.env["OPENAI_API_KEY"] = "sk-test"
        self.app.run()
        self.assertFalse(self.app.error)
        self.assertFalse(self.app.button(key="material_next").disabled)
        self.assertIn("outline_job", self.app.session_state)
