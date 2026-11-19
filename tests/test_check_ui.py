import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tests.test_planning_ui import create_plan, visible_text
from tutor.assessment.questions import Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


def mc(prompt):
    return Question("multiple_choice", prompt, ("2", "3", "4"), 0, "From the reading.", "generated",
                    ("p1",), "reference")


class CheckUITests(unittest.TestCase):
    def setUp(self):
        topics = [Topic(title=t, summary=f"Learn {t.lower()}.", source_ids=[f"p{n}"])
                  for n, t in enumerate(("Assignment", "Updates", "Loops"), 1)]
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain.")
                            for n, t in enumerate(topics, 1)]),
        ]
        # Practice and diagnostic questions both come from the question pipeline.
        self.enterContext(patch("tutor.assessment.questions.generate_questions",
                                side_effect=lambda assignment, *a, **k: (
                                    mc(f"{assignment.unit.title} A?"), mc(f"{assignment.unit.title} B?"))))
        self.model = ScriptedModel()
        self.enterContext(patch("tutor.agent.loop.call_with_tools", side_effect=self.model))
        self.app = AppTest.from_file(APP, default_timeout=10).run()
        upload(self.app, "Assignment: x = 2.", "Updates: x = x + 1.", "Loops: range(3).")
        button(self.app.sidebar, "Generate outline").click().run()
        self.app.checkbox(key="weak_topic_2").check()
        create_plan(self.app, 3)

    def panel(self):
        return self.app.main.container("plan_panel")

    def text(self):
        panel = self.panel()
        extra = [item.value for group in (panel.markdown, panel.info, panel.warning, panel.error) for item in group]
        return "\n".join([visible_text(panel), *extra])

    def answer(self, question_id, option):
        self.app.radio(key=f"check_choice_{question_id}").set_value(option)
        button(self.panel(), "Submit answer").click().run()
        self.assertFalse(self.app.exception)

    def test_initial_check_confirms_a_gap_and_replans(self):
        self.assertIn("Initial check", self.text())
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-3",))
        self.model.turns += [
            turn("get_learner_state", 1),
            turn("ask_question", 2, unit_id="unit-3", reason="You marked loops."),
            turn("ask_question", 3, unit_id="unit-2", reason="Loops build on updates."),
            turn("ask_question", 4, unit_id="unit-2", reason="Confirm updates."),
            turn("finish", 5, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1", "unit-2:q2"],
                 next_step="review_gap", summary="Updates are the difficulty, not loops."),
        ]
        button(self.panel(), "Start initial check").click().run()
        self.assertIn("Why this question: You marked loops.", self.text())
        self.assertIn("Question 1 of up to 5 · Loops", self.text())
        self.assertNotIn("Study day", [w.label for w in self.panel().number_input])
        self.answer("unit-3:q1", "2")      # right
        self.assertIn("Loops build on updates.", self.text())
        self.answer("unit-2:q1", "3")      # wrong
        self.answer("unit-2:q2", "4")      # wrong

        text = self.text()
        self.assertIn("Likely gap: Updates.", text)
        self.assertIn("Updates are the difficulty, not loops.", text)
        self.assertIn("Based on: Updates: wrong; Updates: wrong", text)
        self.assertIn("More time for Updates (0 of 2 answers correct).", text)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-2", "unit-3"))
        self.assertEqual(self.app.session_state["initial_check"], "done")
        button(self.panel(), "Continue").click().run()
        text = self.text()
        self.assertNotIn("Start initial check", [b.label for b in self.panel().button])
        self.assertIn("More time for: Updates; Loops", text)
        self.assertEqual(self.app.number_input(key="study_day").value, 1)
        status = visible_text(self.app.main.container("learning_status_panel"))
        self.assertIn("Likely gap", status)

    def test_skipping_and_daily_checks_adjust_the_rest_of_the_plan(self):
        button(self.panel(), "Skip").click().run()
        self.assertNotIn("Start initial check", [b.label for b in self.panel().button])
        self.assertIn("Goal: 3 days · plan: 3 study days · 0 checked · 3 to go", self.text())

        # Day 1: practice is fine, the check continues without a change.
        self.model.turns += [turn("finish", 1, primary_gap="none", status="uncertain", evidence=[],
                                  next_step="continue", summary="Assignment looks fine so far.")]
        button(self.panel(), "Check my understanding").click().run()
        self.assertIn("The plan is unchanged.", self.text())
        button(self.panel(), "Continue").click().run()
        self.assertIn("Day 1 · checked", [s.value for s in self.panel().subheader])
        self.assertIn("1 checked · 2 to go", self.text())

        # Day 2: two wrong answers lead to a review day after it.
        self.app.number_input(key="study_day").set_value(2).run()
        self.model.turns += [
            turn("ask_question", 2, unit_id="unit-2", reason="Check updates."),
            turn("ask_question", 3, unit_id="unit-2", reason="Once more."),
            turn("finish", 4, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1", "unit-2:q2"],
                 next_step="review_today", summary="x = x + 1 is not clear yet."),
        ]
        button(self.panel(), "Check my understanding").click().run()
        self.answer("unit-2:q1", "3")
        self.answer("unit-2:q2", "3")
        self.assertIn("Added a review of Updates as day 3", self.text())
        button(self.panel(), "Continue").click().run()
        text = self.text()
        self.assertIn("plan: 4 study days · 2 checked · 2 to go", text)
        self.assertIn("The plan now needs 4 days, 1 more than your goal", text)
        self.assertIn("Plan changes (1)", [e.label for e in self.panel().expander])
        self.app.number_input(key="study_day").set_value(3).run()
        self.assertIn("Review · Updates", text + visible_text(self.panel()))
        self.assertEqual(self.app.number_input(key="study_day").max, 4)

    def test_an_outage_can_be_retried_or_the_check_stopped(self):
        self.model.turns += [LLMError("Could not reach OpenAI."),
                             turn("ask_question", 1, unit_id="unit-1", reason="Start.")]
        button(self.panel(), "Start initial check").click().run()
        self.assertIn("Could not reach OpenAI.", self.text())
        button(self.panel(), "Try again").click().run()
        self.assertIn("Why this question: Start.", self.text())
        button(self.panel(), "Stop check").click().run()
        self.assertEqual(self.app.session_state["initial_check"], "skipped")
        self.assertIn("Goal: 3 days", self.text())
