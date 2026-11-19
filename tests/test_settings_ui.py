import os
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tutor import llm
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


class SettingsUITests(unittest.TestCase):
    def setUp(self):
        self.env = self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.models = self.enterContext(patch("tutor.ui.settings.list_models"))
        self.models.return_value = ["gpt-4.1-mini", "gpt-5.6-luna", "gpt-6-luna", "o3"]
        self.app = AppTest.from_file(APP).run()

    def key_input(self):
        return self.app.sidebar.text_input(key="api_key_input")

    def test_the_key_is_hidden_until_shown_and_loads_the_learners_models(self):
        expander = self.app.sidebar.expander[0]
        self.assertEqual(expander.label, "OpenAI settings")
        self.assertTrue(expander.proto.expanded)
        self.assertEqual(self.key_input().value, "")
        self.assertEqual(self.key_input().proto.type, self.key_input().proto.PASSWORD)
        self.app.sidebar.toggle(key="show_api_key").set_value(True).run()
        self.assertEqual(self.key_input().proto.type, self.key_input().proto.DEFAULT)
        self.app.sidebar.toggle(key="show_api_key").set_value(False).run()
        self.assertEqual(self.key_input().proto.type, self.key_input().proto.PASSWORD)
        self.models.assert_not_called()

        self.key_input().set_value("sk-learner").run()
        self.models.assert_called_once_with("sk-learner")
        model = self.app.sidebar.selectbox(key="model_choice")
        self.assertEqual(model.options, ["gpt-4.1-mini", "gpt-5.6-luna", "gpt-6-luna", "o3", "Other…"])
        self.assertIn("Using your key.", [c.value for c in self.app.sidebar.caption])
        model.set_value("gpt-6-luna").run()
        self.app.run()
        self.models.assert_called_once()  # loaded once per key

        # Model calls in this session use the learner's key and model.
        seen = []

        def outline(pages):
            seen.append((llm._api_key(), llm.current_model()))
            return Outline(topics=[Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])

        with patch("tutor.materials.outline.generate_outline", side_effect=outline):
            upload(self.app, "Loops: range(3).")
            button(self.app.sidebar, "Generate outline").click().run()
        self.assertEqual(seen, [("sk-learner", "gpt-6-luna")])
        self.assertNotIn("sk-learner", os.environ.values())

    def test_any_model_id_can_be_typed(self):
        self.key_input().set_value("sk-learner").run()
        self.app.sidebar.selectbox(key="model_choice").set_value("Other…").run()
        self.app.sidebar.text_input(key="model_other").set_value("gpt-5.6-luna").run()
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages: seen.append(llm.current_model()) or Outline(topics=[
                       Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])):
            upload(self.app, "Loops: range(3).")
            button(self.app.sidebar, "Generate outline").click().run()
        self.assertEqual(seen, ["gpt-5.6-luna"])

    def test_a_rejected_key_is_reported(self):
        self.models.side_effect = LLMError("OpenAI rejected the credentials. Check the app's API key.")
        self.key_input().set_value("sk-wrong").run()
        self.assertIn("rejected the credentials", self.app.sidebar.error[0].value)
        self.assertEqual(self.app.sidebar.selectbox(key="model_choice").options[0], "gpt-4.1-mini")

    def test_the_apps_own_key_is_used_but_never_shown(self):
        self.env["OPENAI_API_KEY"] = "sk-app-secret"
        self.app = AppTest.from_file(APP).run()
        self.assertEqual(self.key_input().value, "")
        self.assertFalse(self.app.sidebar.expander[0].proto.expanded)
        self.assertIn("Using the app's key. Enter your own to use your account.",
                      [c.value for c in self.app.sidebar.caption])
        self.models.assert_not_called()
        button(self.app.sidebar, "Load models for the app's key").click().run()
        self.models.assert_called_once_with(None)
