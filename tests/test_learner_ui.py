import re
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tests.test_planning_ui import create_plan, visible_text
from tutor.assessment.questions import Question
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


class LearnerUITests(unittest.TestCase):
    def setUp(self):
        topics = [
            Topic(title="Assignment", summary="Store a value.", source_ids=["p1"]),
            Topic(title="Iteration", summary="Repeat a block.", source_ids=["p2"]),
            Topic(title="Loop counts", summary="Count iterations.", source_ids=["p3"]),
        ]
        outline = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        outline.return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain it.")
                            for n, t in enumerate(topics, 1)]),
        ]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions"))
        self.app = AppTest.from_file(APP).run()
        upload(self.app, "Assignment: x = 2.", "Iteration: loop twice.", "Counting: range(3).")
        button(self.app.sidebar, "Generate outline").click().run()

    def status_text(self):
        html = visible_text(self.app.main.container("learning_status_panel"))
        return re.sub(r"\s*<br>\s*", "\n", re.sub(r"</?(?:p|strong|small)>", "", html))

    def plan(self, days, *weak):
        for index in weak:
            self.app.checkbox(key=f"weak_topic_{index}").check()
        create_plan(self.app, days)
        self.assertFalse(self.app.exception)

    def plan_text(self):
        return visible_text(self.app.main.container("plan_panel"))

    def test_weak_topics_on_the_outline_get_more_time(self):
        self.assertEqual(len(self.app.main.container("outline_panel").checkbox), 3)
        self.plan(2, 1)
        self.assertIn("More time for: Iteration", self.plan_text())
        self.assertIn("Iteration · Marked weak · not checked yet", self.status_text())
        self.assertIn("Assignment · Not checked yet", self.status_text())
        self.assertFalse(self.app.sidebar.text_area)
        # A long plan gives the weak unit a review day.
        self.plan(6)
        kinds = [(a.unit.title, a.kind) for day in self.app.session_state["study_plan"] for a in day.assignments]
        self.assertIn(("Iteration", "review"), kinds)
        self.assertNotIn(("Assignment", "review"), kinds)

    def test_checked_topics_take_effect_when_the_plan_is_created(self):
        self.plan(3, 0, 2)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-3"))
        self.assertIn("Loop counts · Marked weak · not checked yet", self.status_text())
        # Unchecking alone changes nothing until the plan is created again.
        self.app.checkbox(key="weak_topic_0").uncheck().run()
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-3"))
        self.plan(3)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-3",))
        self.assertIn("Assignment · Not checked yet", self.status_text())
        self.assertNotIn("More time for: Assignment", self.plan_text())

    def test_practice_answers_update_the_unit_status(self):
        question = Question(
            kind="multiple_choice", prompt="Which value is assigned?", options=("2", "3"), correct_index=0,
            explanation="x = 2 stores 2.", origin="generated", source_ids=("p1",), answer_origin="reference",
        )
        self.generate.side_effect = [(question,), (), ()]
        self.plan(1)
        button(self.app.main.container("plan_panel"), "Generate daily practice").click().run()
        self.app.radio[0].set_value("3").run()
        button(self.app, "Check answer").click().run()
        self.assertIn("Assignment · Needs more evidence", self.status_text())
        self.assertIn("0 of 1 answers correct", self.status_text())
        state = self.app.session_state["learner_state"]
        (answer,) = state.answers()
        self.assertEqual((answer.unit_id, answer.correct, answer.source), ("unit-1", False, "practice"))
