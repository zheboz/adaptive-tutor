import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button
from tests.test_planning_ui import create_plan, metrics, open_day, show_view, visible_text
from tutor.assessment.questions import InsufficientEvidence, PracticeError, Question
from tutor.llm import LLMError
from tutor.materials.cards import KnowledgePoint, UnitCard
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


PAGES = {"Assignment": "p1", "Updates": "p2", "Loops": "p3"}


def mc(title, letter):
    page = PAGES[title]
    return Question("multiple_choice", f"{title} {letter}?", ("2", "3", "4"), 0, f"{title} works this way.",
                    "generated", (page,), "reference", evidence=f"The {title.lower()} rule from the notes.",
                    evidence_source_id=page)


def three_questions(assignment, *args, **kwargs):
    return mc(assignment.unit.title, "A"), mc(assignment.unit.title, "B"), mc(assignment.unit.title, "C")


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
            patch("tutor.assessment.questions.generate_questions", side_effect=three_questions))
        self.model = ScriptedModel()
        self.enterContext(patch("tutor.agent.loop.call_with_tools", side_effect=self.model))
        self.enterContext(patch("tutor.materials.cards.build_card", side_effect=lambda title, *_: UnitCard((
            KnowledgePoint(f"{title} rule", "What it does.", ("A detail.",), "p1", "x = 2"),))))
        self.app = AppTest.from_file(APP, default_timeout=10).run()
        upload(self.app, "Assignment: x = 2.", "Updates: x = x + 1.", "Loops: range(3).")
        create_plan(self.app, 3)

    def panel(self):
        return self.app.main.container("plan_panel")

    def text(self):
        panel = self.panel()
        extra = [item.value for group in (panel.markdown, panel.info, panel.warning, panel.error, panel.success)
                 for item in group]
        return "\n".join([visible_text(panel), *extra])

    def questions_fail(self, error):
        """Today's questions were prepared when the day opened; prepare them again, failing."""
        self.generate.side_effect = error
        self.app.session_state["day_banks"] = {}

    def answer(self, question_id, option):
        self.app.radio(key=f"check_choice_{question_id}").set_value(option)
        button(self.panel(), "Submit answer").click().run()
        self.assertFalse(self.app.exception)

    def test_the_day_shows_no_practice_only_a_check(self):
        labels = [b.label for b in self.panel().button]
        self.assertNotIn("Generate daily practice", labels)
        self.assertIn("Check my understanding", labels)
        self.assertIn("asks up to 8 questions from today's pages, at most 3 per unit", self.text())
        # Opening the day starts preparing its questions in the background.
        self.assertEqual(len(self.app.session_state["day_banks"]), 1)

    def test_daily_checks_ask_from_the_days_pages_and_adjust_the_plan(self):
        show_view(self.app, "Plan")
        self.assertEqual(metrics(self.app), {"Goal": "3 days", "Plan": "3 days", "Checked": "0", "To go": "3"})
        show_view(self.app, "Today")

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
        self.assertIn("1 of 3 days checked", self.text())
        self.assertEqual(self.app.segmented_control(key="day_picker").options, ["1 ✓", "2", "3"])

        # Day 2: one wrong answer and two right ones add no review.
        open_day(self.app, 2)
        self.model.turns += [
            turn("ask_question", 3, unit_id="unit-2", reason="Check updates."),
            turn("ask_question", 4, unit_id="unit-2", reason="Once more."),
            turn("ask_question", 5, unit_id="unit-2", reason="A third time."),
            turn("finish", 6, primary_gap="unit-2", status="uncertain",
                 evidence=[qid("unit-2", 1)], next_step="review_today",
                 summary="One slip on x = x + 1."),
        ]
        button(self.panel(), "Check my understanding").click().run()
        self.answer(qid("unit-2", 1), "3")
        text = self.text()
        self.assertIn("Question 1 · Updates: Not quite.", text)
        self.assertIn("Correct answer: 2", text)
        self.answer(qid("unit-2", 2), "2")
        self.answer(qid("unit-2", 3), "2")
        text = self.text()
        self.assertIn("No review was added: no unit studied today ended this check as a gap", text)
        self.assertIn("Updates: mixed answers (2 of 3 correct)", text)
        self.assertNotIn("Plan change", text)
        button(self.panel(), "Continue").click().run()
        self.assertIn("2 of 3 days checked", self.text())

        # Day 3: two wrong answers out of three add a review at the end of the plan.
        open_day(self.app, 3)
        self.model.turns += [
            turn("ask_question", 7, unit_id="unit-3", reason="Check loops."),
            turn("ask_question", 8, unit_id="unit-3", reason="Again."),
            turn("ask_question", 9, unit_id="unit-3", reason="Last one."),
            turn("finish", 10, primary_gap="unit-3", status="confirmed",
                 evidence=[qid("unit-3", 1), qid("unit-3", 2)], next_step="review_today",
                 summary="Loop counting is not clear yet."),
        ]
        button(self.panel(), "Check my understanding").click().run()
        for n, option in ((1, "4"), (2, "2"), (3, "4")):
            self.answer(qid("unit-3", n), option)
        text = self.text()
        self.assertIn("Added a review of Loops as day 4 (today's answers show it needs another session; "
                      "1 of 3 correct in this check), at the end of the plan.", text)
        self.assertIn("Loops: needs review (1 of 3 correct)", text)
        self.assertIn("Your answers in this check (3)", [e.label for e in self.panel().expander])
        button(self.panel(), "Continue").click().run()
        self.assertIn("3 of 4 days checked", self.text())
        show_view(self.app, "Plan")
        overview = self.app.main.container("plan_overview_panel")
        self.assertEqual(metrics(self.app)["Plan"], "4 days")
        self.assertIn("The plan now needs 4 days, 1 more than your goal", overview.warning[0].value)
        self.assertIn("Plan changes (1)", [e.label for e in overview.expander])
        rows = self.app.dataframe[0].value.to_dict("records")
        self.assertEqual(rows[3]["Study"], "Review: Loops")
        self.assertEqual([r["Status"] for r in rows], ["✓ checked"] * 3 + [""])
        open_day(self.app, 4)
        self.assertIn("Review · Loops", visible_text(self.panel()))
        self.assertEqual(self.app.segmented_control(key="day_picker").options, ["1 ✓", "2 ✓", "3 ✓", "4 ↻"])

    def test_a_day_with_nothing_to_ask_says_why(self):
        self.questions_fail(InsufficientEvidence("The assigned pages have no teaching point to assess."))
        button(self.panel(), "Check my understanding").click().run()
        text = self.text()
        self.assertIn("There is nothing to check from today's material. When you continue, the day is "
                      "marked as checked", text)
        self.assertIn("Assignment: The assigned pages have no teaching point to assess.", text)
        self.assertNotIn("Try again", [b.label for b in self.panel().button])
        self.assertEqual(self.model.seen, [])
        button(self.panel(), "Continue").click().run()
        self.assertIn("Day 1 · checked", [s.value for s in self.panel().subheader])
        self.assertIn("1 of 3 days checked", self.text())

    def test_questions_that_fail_verification_can_be_prepared_again(self):
        self.questions_fail(PracticeError("A question referenced a learning point that is not in the "
                                          "assigned reading."))
        button(self.panel(), "Check my understanding").click().run()
        text = self.text()
        self.assertIn("No question could be prepared from today's material this time.", text)
        self.assertIn("No question passed verification this time", text)
        self.generate.side_effect = three_questions
        self.model.turns += [turn("ask_question", 1, unit_id="unit-1", reason="Now there are questions.")]
        button(self.panel(), "Try again").click().run()
        self.assertIn("Why this question: Now there are questions.", self.text())

    def test_an_outage_can_be_retried_or_the_check_stopped(self):
        self.questions_fail(LLMError("Could not reach OpenAI."))
        button(self.panel(), "Check my understanding").click().run()
        self.assertIn("Could not reach OpenAI.", self.text())
        self.generate.side_effect = three_questions
        self.model.turns += [turn("ask_question", 1, unit_id="unit-1", reason="Start.")]
        button(self.panel(), "Try again").click().run()
        self.assertIn("Why this question: Start.", self.text())
        button(self.panel(), "Stop check").click().run()
        self.assertNotIn("check", self.app.session_state)
        self.assertIn("Day 1", [s.value for s in self.panel().subheader])


class KnowledgeCardUITests(CheckUITests):
    """The Today view lists each unit's knowledge points before the check."""

    def test_each_unit_lists_its_knowledge_points_with_their_page(self):
        panel = self.panel()
        self.assertIn("<strong>1. Assignment rule</strong><br>What it does.", "\n".join(h.value for h in panel.html))
        self.assertIn("<li>A detail.</li>", "\n".join(h.value for h in panel.html))
        self.assertIn("From page 1", [e.label for e in panel.expander])
        self.assertIn("“x = 2”", [c.value for c in panel.caption])
        panel.button(key="card_1_0_point_1_p1").click().run()
        self.assertEqual(self.app.selectbox(key="pdf_page_number").value, 1)
        # The next day's cards were started in the background; opening it shows them.
        self.assertEqual(len(self.app.session_state["day_cards"]), 2)
        open_day(self.app, 2)
        self.assertIn("<strong>1. Updates rule</strong>", "\n".join(h.value for h in self.panel().html))

    def test_a_failed_card_waits_for_try_again(self):
        self.app.session_state["day_cards"] = {}
        failures = [LLMError("Could not reach OpenAI.")]

        def build_card(title, *_):
            # Today's and the next day's cards are made in parallel, so answer by unit, not call order.
            if title == "Assignment" and failures:
                raise failures.pop()
            return UnitCard((KnowledgePoint("Again" if title == "Assignment" else "Next day", "Works now.", (),
                                            "p1", "x = 2"),))

        with patch("tutor.materials.cards.build_card", side_effect=build_card) as build:
            self.app.run()
            self.assertIn("The knowledge points could not be prepared. Could not reach OpenAI.",
                          [w.value for w in self.panel().warning])
            show_view(self.app, "Plan")
            show_view(self.app, "Today")
            self.assertEqual(build.call_count, 2)  # today's failure, and the next day in the background
            button(self.panel(), "Try again").click().run()
        self.assertIn("<strong>1. Again</strong><br>Works now.", "\n".join(h.value for h in self.panel().html))

    # The check tests run once, in CheckUITests.
    test_the_day_shows_no_practice_only_a_check = None
    test_daily_checks_ask_from_the_days_pages_and_adjust_the_plan = None
    test_a_day_with_nothing_to_ask_says_why = None
    test_questions_that_fail_verification_can_be_prepared_again = None
    test_an_outage_can_be_retried_or_the_check_stopped = None
