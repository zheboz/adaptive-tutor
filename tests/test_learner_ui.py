import re
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tests.test_planning_ui import create_plan, visible_text
from tutor.agent.intake import NoteMapping
from tutor.assessment.questions import Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


class LearnerUITests(unittest.TestCase):
    def setUp(self):
        topics = [
            Topic(title="Assignment", summary="Store a value.", source_ids=["p1"]),
            Topic(title="Iteration", summary="Repeat a block.", source_ids=["p2"]),
        ]
        outline = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        outline.return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain it.")
                            for n, t in enumerate(topics, 1)]),
        ]
        self.mapper = self.enterContext(patch("tutor.agent.intake.generate_structured"))
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions"))
        self.app = AppTest.from_file(APP).run()
        upload(self.app, "Assignment: x = 2.", "Iteration: loop twice.")
        button(self.app.sidebar, "Generate outline").click().run()

    def status_text(self):
        html = visible_text(self.app.main.container("learning_status_panel"))
        return re.sub(r"\s*<br>\s*", "\n", re.sub(r"</?(?:p|strong|small)>", "", html))

    def test_self_report_is_saved_and_shown_as_a_suspicion(self):
        self.assertFalse(self.app.sidebar.multiselect)
        create_plan(self.app, 1)
        self.assertIn("Assignment · Not checked yet", self.status_text())
        self.mapper.return_value = NoteMapping(unit_ids=["unit-2"], not_in_material=True, missing_topic="while loops")
        self.app.sidebar.multiselect(key="self_report_units").set_value(["unit-1"])
        self.app.sidebar.text_area(key="self_report_note").set_value("Loops, especially while loops")
        button(self.app.sidebar, "Save").click().run()
        self.assertFalse(self.app.exception)
        text = self.status_text()
        self.assertIn("Assignment · Marked unclear · not checked yet", text)
        self.assertIn("Iteration · Marked unclear · not checked yet", text)
        self.assertIn("your note: “Loops, especially while loops”", text)
        self.assertIn("Your note matches: Iteration", visible_text(self.app.sidebar))
        self.assertIn("while loops", self.app.sidebar.info[0].value)
        # Changing the duration keeps the same units and the same report.
        create_plan(self.app, 2)
        self.assertIn("Assignment · Marked unclear", self.status_text())

    def test_a_failed_note_match_keeps_the_previous_report(self):
        create_plan(self.app, 1)
        self.app.sidebar.multiselect(key="self_report_units").set_value(["unit-2"])
        button(self.app.sidebar, "Save").click().run()
        self.mapper.assert_not_called()
        self.mapper.side_effect = LLMError("Could not reach OpenAI.")
        self.app.sidebar.text_area(key="self_report_note").set_value("loops")
        button(self.app.sidebar, "Save").click().run()
        self.assertIn("Could not reach OpenAI.", self.app.sidebar.error[0].value)
        self.assertIn("Iteration · Marked unclear", self.status_text())

    def test_practice_answers_update_the_unit_status(self):
        question = Question(
            kind="multiple_choice", prompt="Which value is assigned?", options=("2", "3"), correct_index=0,
            explanation="x = 2 stores 2.", origin="generated", source_ids=("p1",), answer_origin="reference",
        )
        self.generate.side_effect = [(question,), ()]
        create_plan(self.app, 1)
        button(self.app.main.container("plan_panel"), "Generate daily practice").click().run()
        self.app.radio[0].set_value("3").run()
        button(self.app, "Check answer").click().run()
        self.assertIn("Assignment · Needs more evidence", self.status_text())
        self.assertIn("0 of 1 answers correct", self.status_text())
        state = self.app.session_state["learner_state"]
        (answer,) = state.answers()
        self.assertEqual((answer.unit_id, answer.correct, answer.source), ("unit-1", False, "practice"))
