from pathlib import Path
import tempfile
from unittest.mock import patch

from tests.ui_helpers import UITestCase, begin
from tutor import llm
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.ui import settings


def one_topic(pages, *_):
    return Outline(topics=[Topic(title="Loops", summary="Repeat.", source_ids=["p1"])])


class SettingsUITests(UITestCase):
    def setUp(self):
        super().setUp()
        self.env["OPENAI_API_KEY"] = "sk-server"
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

    def model(self):
        return self.fields().selectbox(key="model_choice")

    def test_the_apps_key_is_used_and_only_the_model_is_chosen(self):
        self.assertFalse(self.app.sidebar.children)
        # No key field anywhere, and the key is never shown.
        self.assertFalse(self.app.text_input)
        self.assertNotIn("sk-server", str(self.app.main))
        self.assertEqual(self.model().value, "gpt-6-luna")
        # The key's models are loaded once.
        self.models.assert_called_once_with("sk-server")
        # The default, then recommended models the account has (newest first), then its other models.
        self.assertEqual(self.model().options, ["gpt-6-luna (default)", "gpt-5.6-luna", "o3", "gpt-4.1-mini",
                                                "chat-latest", "Other…"])
        self.model().set_value("gpt-5.6-luna").run()
        self.app.run()
        self.models.assert_called_once()

        # Model calls in this session use the app's key and the chosen model.
        seen = []

        def outline(pages, *_):
            seen.append((llm._api_key(), llm.current_model()))
            return one_topic(pages)

        with patch("tutor.materials.outline.generate_outline", side_effect=outline):
            begin(self.app, "Loops: range(3).")
        self.assertEqual(seen, [("sk-server", "gpt-5.6-luna")])
        # Past the first step, the model is in the Settings menu at the top.
        self.assertEqual(self.model().value, "gpt-5.6-luna")
        self.models.assert_called_once()

    def test_a_model_changed_in_the_settings_menu_is_used_from_then_on(self):
        with patch("tutor.materials.outline.generate_outline", side_effect=one_topic):
            begin(self.app, "Loops: range(3).")
        self.model().set_value("o3").run()
        self.assertEqual(self.app.session_state["setup_step"], 2)
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages, *_: seen.append(llm.current_model()) or one_topic(pages)):
            # Make the outline again, as after replacing the material.
            del self.app.session_state["study_outline"]
            self.app.run()
        self.assertEqual(seen, ["o3"])

    def test_an_account_without_the_default_falls_back(self):
        self.models.return_value = ["gpt-4.1-mini", "gpt-4o", "o3"]
        self.app = self.new_app()
        self.assertEqual(self.model().options, ["gpt-4.1-mini (default)", "o3", "gpt-4o", "Other…"])
        self.assertEqual(self.model().value, "gpt-4.1-mini")

    def test_any_model_id_can_be_typed(self):
        self.model().set_value("Other…").run()
        self.fields().text_input(key="model_other").set_value("gpt-5.4-nano").run()
        seen = []
        with patch("tutor.materials.outline.generate_outline",
                   side_effect=lambda pages, *_: seen.append(llm.current_model()) or one_topic(pages)):
            begin(self.app, "Loops: range(3).")
        self.assertEqual(seen, ["gpt-5.4-nano"])
        self.assertEqual(self.fields().text_input(key="model_other").value, "gpt-5.4-nano")

    def test_a_rejected_key_is_reported(self):
        self.models.side_effect = LLMError("OpenAI rejected the credentials. Check the app's API key.")
        self.app = self.new_app()
        self.assertIn("rejected the credentials", self.fields().error[0].value)
        self.assertEqual(self.model().options[0], "gpt-6-luna (default)")

    def test_without_a_key_the_newest_recommended_models_are_offered(self):
        del self.env["OPENAI_API_KEY"]
        self.models.reset_mock()
        self.app = self.new_app()
        self.assertIn("No OpenAI API key is set for this app", self.fields().error[0].value)
        self.models.assert_not_called()
        options = self.model().options
        self.assertEqual(options[:3], ["gpt-6-luna (default)", "gpt-6.2-sol", "gpt-6.2-astra"])
        self.assertIn("gpt-4.1-mini", options)
        self.assertEqual(options[-1], "Other…")
        self.assertEqual(len(options), 25)


class EnvFileTests(UITestCase):
    def test_the_key_can_come_from_a_dotenv_file(self):
        del self.env["OPENAI_API_KEY"]
        with patch("tutor.ui.settings._read_env_file", return_value={"OPENAI_API_KEY": " sk-file "}):
            self.assertEqual(settings.current_key(), "sk-file")
        # The environment comes first.
        self.env["OPENAI_API_KEY"] = "sk-env"
        with patch("tutor.ui.settings._read_env_file", return_value={"OPENAI_API_KEY": "sk-file"}):
            self.assertEqual(settings.current_key(), "sk-env")

    def test_dotenv_lines_are_read_like_a_shell_would(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text('# a comment\n\nexport OPENAI_API_KEY="sk-quoted"\nOTHER=1\nbroken line\n')
            self.assertEqual(settings._read_env_file(env), {"OPENAI_API_KEY": "sk-quoted", "OTHER": "1"})
            self.assertEqual(settings._read_env_file(Path(folder) / "missing"), {})
