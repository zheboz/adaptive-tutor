import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tests.test_planning_ui import create_plan, visible_text
from tutor.assessment.questions import InsufficientEvidence, Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


PAGES = {"Assignment": "p1", "Updates": "p2", "Loops": "p3"}


def mc(title, letter):
    page = PAGES[title]
    return Question("multiple_choice", f"{title} {letter}?", ("2", "3", "4"), 0, f"{title} works this way.",
                    "generated", (page,), "reference", evidence=f"The {title.lower()} rule from the notes.",
                    evidence_source_id=page)


def two_questions(assignment, *args, **kwargs):
    return mc(assignment.unit.title, "A"), mc(assignment.unit.title, "B")


def qid(unit_id, n):
    """Daily check question IDs carry the day's material: kind, review round and pages."""
    page = {"unit-1": "p1", "unit-2": "p2", "unit-3": "p3"}[unit_id]
    return f"study0-{page}:{unit_id}:q{n}"


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
        self.generate = self.enterContext(
            patch("tutor.assessment.questions.generate_questions", side_effect=two_questions))
        self.model = ScriptedModel()
        self.enterContext(patch("tutor.agent.loop.call_with_tools", side_effect=self.model))
        self.app = AppTest.from_file(APP, default_timeout=10).run()
        upload(self.app, "Assignment: x = 2.", "Updates: x = x + 1.", "Loops: range(3).")
        button(self.app.sidebar, "Generate outline").click().run()
        create_plan(self.app, 3)

    def panel(self):
        return self.app.main.container("plan_panel")

    def text(self):
        panel = self.panel()
        extra = [item.value for group in (panel.markdown, panel.info, panel.warning, panel.error, panel.success)
                 for item in group]
        return "\n".join([visible_text(panel), *extra])

    def answer(self, question_id, option):
        self.app.radio(key=f"check_choice_{question_id}").set_value(option)
        button(self.panel(), "Submit answer").click().run()
        self.assertFalse(self.app.exception)

    def test_the_day_shows_no_practice_only_a_check(self):
        labels = [b.label for b in self.panel().button]
        self.assertNotIn("Generate daily practice", labels)
        self.assertIn("Check my understanding", labels)
        self.assertIn("asks up to 3 questions from today's pages", self.text())
        self.generate.assert_not_called()

    def test_daily_checks_ask_from_the_days_pages_and_adjust_the_plan(self):
        self.assertIn("Goal: 3 days · plan: 3 study days · 0 checked · 3 to go", self.text())

        # Day 1: one right answer; the check continues without a change.
        self.model.turns += [
            turn("ask_question", 1, unit_id="unit-1", reason="Check today's unit."),
            turn("finish", 2, primary_gap="none", status="uncertain", evidence=[qid("unit-1", 1)],
                 next_step="continue", summary="Assignment looks fine so far."),
        ]
        button(self.panel(), "Check my understanding").click().run()
        assignment = self.generate.call_args.args[0]
        self.assertEqual((assignment.unit.unit_id, assignment.source_ids), ("unit-1", ("p1",)))
        self.assertIn('"units_you_can_ask_about": ["unit-1"]', self.model.seen[0][0]["content"])
        self.answer(qid("unit-1", 1), "2")
        text = self.text()
        self.assertIn("Question 1 · Assignment: Correct.", text)
        self.assertIn("In your material, page 1: “The assignment rule from the notes.”", text)
        self.assertIn("The plan is unchanged.", text)
        button(self.panel(), "Continue").click().run()
        self.assertIn("Day 1 · checked", [s.value for s in self.panel().subheader])
        self.assertIn("1 checked · 2 to go", self.text())

        # Day 2: two wrong answers, each with feedback, lead to a review day.
        self.app.number_input(key="study_day").set_value(2).run()
        self.model.turns += [
            turn("ask_question", 3, unit_id="unit-2", reason="Check updates."),
            turn("ask_question", 4, unit_id="unit-2", reason="Once more."),
            turn("finish", 5, primary_gap="unit-2", status="confirmed",
                 evidence=[qid("unit-2", 1), qid("unit-2", 2)], next_step="review_today",
                 summary="x = x + 1 is not clear yet."),
        ]
        button(self.panel(), "Check my understanding").click().run()
        self.answer(qid("unit-2", 1), "3")
        text = self.text()
        self.assertIn("Question 1 · Updates: Not quite.", text)
        self.assertIn("Correct answer: 2", text)
        self.answer(qid("unit-2", 2), "3")
        text = self.text()
        self.assertIn("Added a review of Updates as day 3", text)
        self.assertIn("Your answers in this check (2)", [e.label for e in self.panel().expander])
        button(self.panel(), "Continue").click().run()
        text = self.text()
        self.assertIn("plan: 4 study days · 2 checked · 2 to go", text)
        self.assertIn("The plan now needs 4 days, 1 more than your goal", text)
        self.assertIn("Plan changes (1)", [e.label for e in self.panel().expander])
        self.app.number_input(key="study_day").set_value(3).run()
        self.assertIn("Review · Updates", visible_text(self.panel()))

    def test_a_day_with_nothing_to_ask_says_why(self):
        self.generate.side_effect = InsufficientEvidence("The assigned pages have no teaching point to assess.")
        button(self.panel(), "Check my understanding").click().run()
        text = self.text()
        self.assertIn("There is nothing to check from today's material, so the plan is unchanged.", text)
        self.assertIn("Assignment: The assigned pages have no teaching point to assess.", text)
        self.assertEqual(self.model.seen, [])
        button(self.panel(), "Continue").click().run()
        self.assertNotIn("Day 1 · checked", [s.value for s in self.panel().subheader])

    def test_an_outage_can_be_retried_or_the_check_stopped(self):
        self.generate.side_effect = LLMError("Could not reach OpenAI.")
        button(self.panel(), "Check my understanding").click().run()
        self.assertIn("Could not reach OpenAI.", self.text())
        self.generate.side_effect = two_questions
        self.model.turns += [turn("ask_question", 1, unit_id="unit-1", reason="Start.")]
        button(self.panel(), "Try again").click().run()
        self.assertIn("Why this question: Start.", self.text())
        button(self.panel(), "Stop check").click().run()
        self.assertNotIn("check", self.app.session_state)
        self.assertIn("Goal: 3 days", self.text())
