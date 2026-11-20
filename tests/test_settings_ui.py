import os
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP
from tutor import llm
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


def one_topic(pages):
    return Outline(topics=[Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])


class SettingsUITests(unittest.TestCase):
    def setUp(self):
        self.env = self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.models = self.enterContext(patch("tutor.ui.settings.list_models"))
        self.models.return_value = ["gpt-4.1-mini", "gpt-5.6-luna", "gpt-6-luna", "o3", "chat-latest"]
        # These tests are about the key and model; planning units in the background is not.
        self.enterContext(patch("tutor.ui.units.start_planning"))
        self.app = AppTest.from_file(APP).run()

    def bar(self):
        return self.app.main.container("topbar")

    def key_input(self):
        return self.bar().text_input(key="api_key_input")

    def model(self):
        return self.bar().selectbox(key="model_choice")

    def test_the_key_and_model_are_in_the_top_bar_and_load_the_learners_models(self):
        self.assertFalse(self.app.sidebar.children)
        self.assertEqual(self.key_input().label, "OpenAI API key")
        self.assertEqual(self.key_input().value, "")
        # Hidden as typed; the field's own eye button shows it.
        self.assertEqual(self.key_input().proto.type, self.key_input().proto.PASSWORD)
        self.assertEqual(self.model().value, "gpt-6-luna")
        self.models.assert_not_called()

        self.key_input().set_value("sk-learner").run()
        self.models.assert_called_once_with("sk-learner")
        # The default, then recommended models the account has (newest first), then its other models.
        self.assertEqual(self.model().options, ["gpt-6-luna (default)", "gpt-5.6-luna", "o3", "gpt-4.1-mini",
                                                "chat-latest", "Other…"])
        self.model().set_value("gpt-5.6-luna").run()
        self.app.run()
        self.models.assert_called_once()  # loaded once per key

        # Model calls in this session use the learner's key and model.
        seen = []

        def outline(pages):
            seen.append((llm._api_key(), llm.current_model()))
            return one_topic(pages)

        with patch("tutor.materials.outline.generate_outline", side_effect=outline):
            upload(self.app, "Loops: range(3).")
        self.assertEqual(seen, [("sk-learner", "gpt-5.6-luna")])
        self.assertNotIn("sk-learner", os.environ.values())

    def test_an_account_without_the_default_falls_back(self):
        self.models.return_value = ["gpt-4.1-mini", "gpt-4o", "o3"]
        self.key_input().set_value("sk-learner").run()
        self.assertEqual(self.model().options, ["gpt-4.1-mini (default)", "o3", "gpt-4o", "Other…"])
        self.assertEqual(self.model().value, "gpt-4.1-mini")

    def test_any_model_id_can_be_typed(self):
        self.key_input().set_value("sk-learner").run()
        self.model().set_value("Other…").run()
        self.bar().text_input(key="model_other").set_value("gpt-5.4-nano").run()
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages: seen.append(llm.current_model()) or one_topic(pages)):
            upload(self.app, "Loops: range(3).")
        self.assertEqual(seen, ["gpt-5.4-nano"])

    def test_a_rejected_key_is_reported(self):
        self.models.side_effect = LLMError("OpenAI rejected the credentials. Check the app's API key.")
        self.key_input().set_value("sk-wrong").run()
        self.assertIn("rejected the credentials", self.bar().error[0].value)
        self.assertEqual(self.model().options[0], "gpt-6-luna (default)")

    def test_before_a_key_the_newest_recommended_models_are_offered(self):
        options = self.model().options
        self.assertEqual(options[:3], ["gpt-6-luna (default)", "gpt-6.2-sol", "gpt-6.2-astra"])
        self.assertIn("gpt-5.6-luna", options)
        self.assertIn("gpt-4.1-mini", options)
        self.assertEqual(options[-1], "Other…")
        self.assertEqual(len(options), 25)

    def test_a_server_key_is_never_used_or_shown(self):
        self.env["OPENAI_API_KEY"] = "sk-server-secret"
        self.env["OPENAI_MODEL"] = "server-model"
        self.app = AppTest.from_file(APP).run()
        self.assertEqual(self.key_input().value, "")
        self.assertEqual(self.model().value, "gpt-6-luna")
        self.models.assert_not_called()
        # Without the learner's key, the outline waits for it and nothing is sent.
        with patch("tutor.llm.OpenAI") as sdk:
            upload(self.app, "Loops: range(3).")
        self.assertIn("Enter your OpenAI API key at the top of the page",
                      self.app.main.container("outline_panel").info[0].value)
        sdk.assert_not_called()
