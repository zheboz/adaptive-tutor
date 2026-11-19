import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button, previewed_pdf
from tests.test_planning_ui import create_plan, visible_text
from tutor.assessment.questions import Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


PAGES = {"Assignment": "p1", "Updates": "p2", "Loops": "p3"}


def mc(title, letter):
    page = PAGES[title]
    return Question("multiple_choice", f"{title} {letter}?", ("2", "3", "4"), 0, f"{title} works this way.",
                    "generated", (page,), "reference", evidence=f"The {title.lower()} rule from the notes.",
                    evidence_source_id=page)


class CheckUITests(unittest.TestCase):
    def setUp(self):
        topics = [Topic(title=t, summary=f"Learn {t.lower()}.", source_ids=[page]) for t, page in PAGES.items()]
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain.")
                            for n, t in enumerate(topics, 1)]),
        ]
        self.planner = planner
        # Practice and diagnostic questions both come from the question pipeline.
        self.enterContext(patch("tutor.assessment.questions.generate_questions",
                                side_effect=lambda assignment, *a, **k: (
                                    mc(assignment.unit.title, "A"), mc(assignment.unit.title, "B"))))
        self.model = ScriptedModel()
        self.enterContext(patch("tutor.agent.loop.call_with_tools", side_effect=self.model))
        self.app = AppTest.from_file(APP, default_timeout=10).run()
        self.document = upload(self.app, "Assignment: x = 2.", "Updates: x = x + 1.", "Loops: range(3).")
        button(self.app.sidebar, "Generate outline").click().run()
        self.app.checkbox(key="weak_topic_2").check()

    def panel(self, key):
        return self.app.main.container(key)

    def text(self, key):
        panel = self.panel(key)
        extra = [item.value for group in (panel.markdown, panel.info, panel.warning, panel.error, panel.success)
                 for item in group]
        return "\n".join([visible_text(panel), *extra])

    def answer(self, key, question_id, option):
        self.app.radio(key=f"check_choice_{question_id}").set_value(option)
        button(self.panel(key), "Submit answer").click().run()
        self.assertFalse(self.app.exception)

    def plan_button(self):
        return button(self.app.sidebar, "Create study plan")

    def test_initial_check_comes_between_the_outline_and_the_plan(self):
        self.assertIn("Initial check", [s.value for s in self.app.sidebar.subheader])
        self.assertFalse(self.plan_button().disabled)
        self.model.turns += [
            turn("get_learner_state", 1),
            turn("ask_question", 2, unit_id="unit-3", reason="You marked loops."),
            turn("ask_question", 3, unit_id="unit-2", reason="Loops build on updates."),
            turn("ask_question", 4, unit_id="unit-2", reason="Confirm updates."),
            turn("finish", 5, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1", "unit-2:q2"],
                 next_step="review_gap", summary="Updates are the difficulty, not loops."),
        ]
        button(self.app.sidebar, "Start initial check").click().run()
        self.assertFalse(self.app.exception)
        # The units exist, the check replaces the outline beside the PDF, and no plan exists yet.
        self.assertNotIn("planned_days", self.app.session_state)
        self.assertIn("Why this question: You marked loops.", self.text("check_panel"))
        self.assertIn("Question 1 of up to 5 · Loops", self.text("check_panel"))
        self.assertTrue(self.plan_button().disabled)
        self.assertEqual(self.app.session_state["learner_state"].focus_units(), ("unit-3",))

        self.answer("check_panel", "unit-3:q1", "2")      # right
        text = self.text("check_panel")
        self.assertIn("Question 1 · Loops: Correct.", text)
        self.assertIn("In your material, page 3: “The loops rule from the notes.”", text)
        self.assertIn("Loops build on updates.", text)
        self.answer("check_panel", "unit-2:q1", "3")      # wrong
        text = self.text("check_panel")
        self.assertIn("Question 2 · Updates: Not quite.", text)
        self.assertIn("Correct answer: 2", text)
        self.assertIn("Updates works this way.", text)
        button(self.panel("check_panel"), "Page 2").click().run()
        self.assertEqual(previewed_pdf(self.app), (self.document, [2]))
        self.answer("check_panel", "unit-2:q2", "4")      # wrong

        text = self.text("check_panel")
        self.assertIn("Likely gap: Updates.", text)
        self.assertIn("For your plan · Updates will get more time (0 of 2 answers correct).", text)
        self.assertIn("Your answers in this check (3)", [e.label for e in self.panel("check_panel").expander])
        button(self.panel("check_panel"), "Continue").click().run()
        self.assertIn("Done. Updates will get more time", visible_text(self.app.sidebar))
        self.assertIn("Check again", [b.label for b in self.app.sidebar.button])
        self.assertIn("Likely gap", visible_text(self.panel("learning_status_panel")))

        create_plan(self.app, 3)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-2", "unit-3"))
        plan = visible_text(self.panel("plan_panel"))
        self.assertIn("More time for: Updates; Loops", plan)
        self.assertIn("From your initial check: Updates will get more time", plan)
        self.assertNotIn("Start initial check", [b.label for b in self.app.sidebar.button])
        self.assertNotIn("Check again", [b.label for b in self.app.sidebar.button])
        # The units were built once, for the check, and reused by the plan.
        self.assertEqual(self.planner.call_count, 2)

    def test_daily_checks_give_feedback_and_adjust_the_rest_of_the_plan(self):
        create_plan(self.app, 3)
        self.assertIn("Goal: 3 days · plan: 3 study days · 0 checked · 3 to go", self.text("plan_panel"))

        # Day 1: practice is fine, the check continues without a change.
        self.model.turns += [turn("finish", 1, primary_gap="none", status="uncertain", evidence=[],
                                  next_step="continue", summary="Assignment looks fine so far.")]
        button(self.panel("plan_panel"), "Check my understanding").click().run()
        self.assertIn("The plan is unchanged.", self.text("plan_panel"))
        button(self.panel("plan_panel"), "Continue").click().run()
        self.assertIn("Day 1 · checked", [s.value for s in self.panel("plan_panel").subheader])
        self.assertIn("1 checked · 2 to go", self.text("plan_panel"))

        # Day 2: two wrong answers, each with feedback, lead to a review day.
        self.app.number_input(key="study_day").set_value(2).run()
        self.model.turns += [
            turn("ask_question", 2, unit_id="unit-2", reason="Check updates."),
            turn("ask_question", 3, unit_id="unit-2", reason="Once more."),
            turn("finish", 4, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1", "unit-2:q2"],
                 next_step="review_today", summary="x = x + 1 is not clear yet."),
        ]
        button(self.panel("plan_panel"), "Check my understanding").click().run()
        self.answer("plan_panel", "unit-2:q1", "3")
        self.assertIn("Question 1 · Updates: Not quite.", self.text("plan_panel"))
        self.answer("plan_panel", "unit-2:q2", "3")
        text = self.text("plan_panel")
        self.assertIn("Added a review of Updates as day 3", text)
        self.assertIn("In your material, page 2", text)
        button(self.panel("plan_panel"), "Continue").click().run()
        text = self.text("plan_panel")
        self.assertIn("plan: 4 study days · 2 checked · 2 to go", text)
        self.assertIn("The plan now needs 4 days, 1 more than your goal", text)
        self.assertIn("Plan changes (1)", [e.label for e in self.panel("plan_panel").expander])
        self.app.number_input(key="study_day").set_value(3).run()
        self.assertIn("Review · Updates", visible_text(self.panel("plan_panel")))
        self.assertEqual(self.app.number_input(key="study_day").max, 4)

    def test_an_outage_can_be_retried_or_the_check_stopped(self):
        self.model.turns += [LLMError("Could not reach OpenAI."),
                             turn("ask_question", 1, unit_id="unit-1", reason="Start.")]
        button(self.app.sidebar, "Start initial check").click().run()
        self.assertIn("Could not reach OpenAI.", self.text("check_panel"))
        button(self.panel("check_panel"), "Try again").click().run()
        self.assertIn("Why this question: Start.", self.text("check_panel"))
        button(self.panel("check_panel"), "Stop check").click().run()
        self.assertEqual(self.app.session_state["initial_check"], "skipped")
        self.assertIn("Study outline", [h.value for h in self.app.main.header])
        self.assertFalse(self.plan_button().disabled)
        create_plan(self.app, 3)
        self.assertIn("Goal: 3 days", self.text("plan_panel"))
