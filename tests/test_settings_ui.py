import os
from unittest.mock import patch

from tests.ui_helpers import UITestCase, add_material, begin
from tutor import llm
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic


def one_topic(pages):
    return Outline(topics=[Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])


class SettingsUITests(UITestCase):
    def setUp(self):
        super().setUp()
        self.env = self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.models = self.list_models
        self.models.return_value = ["gpt-4.1-mini", "gpt-5.6-luna", "gpt-6-luna", "o3", "chat-latest"]
        # These tests are about the key and model; planning units in the background is not.
        self.enterContext(patch("tutor.ui.units.start_planning"))
        self.app = self.new_app()

    def fields(self):
        """In the first step; afterwards in the Settings menu at the top."""
        state = self.app.session_state
        if "setup_step" not in state or state["setup_step"] == 1:
            return self.app.main.container("material_settings")
        return self.app.main.container("header")

    def key_input(self):
        return self.fields().text_input(key="api_key_input")

    def model(self):
        return self.fields().selectbox(key="model_choice")

    def test_the_key_and_model_are_in_the_first_step_and_load_the_learners_models(self):
        self.assertFalse(self.app.sidebar.children)
        self.assertEqual(self.key_input().label, "OpenAI API key")
        self.assertEqual(self.key_input().value, "")
        # Hidden as typed; the field's own eye button shows it.
        self.assertEqual(self.key_input().proto.type, self.key_input().proto.PASSWORD)
        self.assertEqual(self.model().value, "gpt-6-luna")
        # In the first step the fields are on the page, not in a menu.
        self.assertFalse(self.app.main.container("header").text_input)
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
            begin(self.app, "Loops: range(3).", key=None)
        self.assertEqual(seen, [("sk-learner", "gpt-5.6-luna")])
        self.assertNotIn("sk-learner", os.environ.values())
        # Past the first step, the same values are in the Settings menu at the top.
        self.assertEqual(self.key_input().value, "sk-learner")
        self.assertEqual(self.model().value, "gpt-5.6-luna")
        self.models.assert_called_once()

    def test_a_model_changed_in_the_settings_menu_is_used_from_then_on(self):
        with patch("tutor.materials.outline.generate_outline", side_effect=one_topic):
            begin(self.app, "Loops: range(3).")
        self.model().set_value("o3").run()
        self.assertEqual(self.app.session_state["setup_step"], 2)
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages: seen.append(llm.current_model()) or one_topic(pages)):
            # Make the outline again, as after replacing the material.
            del self.app.session_state["study_outline"]
            self.app.run()
        self.assertEqual(seen, ["o3"])

    def test_an_account_without_the_default_falls_back(self):
        self.models.return_value = ["gpt-4.1-mini", "gpt-4o", "o3"]
        self.key_input().set_value("sk-learner").run()
        self.assertEqual(self.model().options, ["gpt-4.1-mini (default)", "o3", "gpt-4o", "Other…"])
        self.assertEqual(self.model().value, "gpt-4.1-mini")

    def test_any_model_id_can_be_typed(self):
        self.key_input().set_value("sk-learner").run()
        self.model().set_value("Other…").run()
        self.fields().text_input(key="model_other").set_value("gpt-5.4-nano").run()
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages: seen.append(llm.current_model()) or one_topic(pages)):
            begin(self.app, "Loops: range(3).", key=None)
        self.assertEqual(seen, ["gpt-5.4-nano"])
        self.assertEqual(self.fields().text_input(key="model_other").value, "gpt-5.4-nano")

    def test_a_rejected_key_is_reported(self):
        self.models.side_effect = LLMError("OpenAI rejected the credentials. Check the app's API key.")
        self.key_input().set_value("sk-wrong").run()
        self.assertIn("rejected the credentials", self.fields().error[0].value)
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
        self.app = self.new_app()
        self.assertEqual(self.key_input().value, "")
        self.assertEqual(self.model().value, "gpt-6-luna")
        self.models.assert_not_called()
        # Without the learner's key, the outline waits for it and nothing is sent.
        with patch("tutor.llm.OpenAI") as sdk:
            add_material(self.app, "Loops: range(3).", key=None)
            self.app.button(key="step_2").click().run()
        self.assertIn("Enter your OpenAI API key in the settings", self.app.info[0].value)
        sdk.assert_not_called()
