import unittest
from unittest.mock import patch

from tests.test_pdf_preview import button, previewed_pdf
from tests.ui_helpers import (
    UITestCase, answer_quiz, begin, create_plan, go_to_step, labels, show_page, start_quick_check, visible_text,
)
from tutor.agent.quiz import Quiz, QuizItem, build_quiz, choose_topics, grade_quiz
from tutor.agent.state import LearnerState
from tutor.assessment.questions import InsufficientEvidence, Question
from tutor.assessment.retrieval import build_index
from tutor.llm import LLMError
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline, Topic
from tutor.planning import StudyUnit
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


TOPICS = [("Assignment", "p1"), ("Updates", "p2"), ("Loops", "p3")]
OUTLINE = Outline(topics=[Topic(title=t, summary=f"Learn {t.lower()}.", source_ids=[p]) for t, p in TOPICS])
# Two units: Assignment and Updates share unit-1, Loops is unit-2.
UNITS = (StudyUnit("unit-1", "Variables", "Store and update.", ("p1", "p2"), "Trace x.", (1, 2)),
         StudyUnit("unit-2", "Loops", "Repeat.", ("p3",), "Trace a loop.", (3,)))
PAGES = [PdfPage(1, "Assignment: x = 2 stores 2."), PdfPage(2, "Updates: x = x + 1 adds one."),
         PdfPage(3, "Loops: range(3) runs 3 times.")]


def question(title, kind="multiple_choice"):
    page = dict(TOPICS)[title]
    options = ("True", "False") if kind == "true_false" else ("2", "3", "4")
    return Question(kind, f"About {title}?", options, 0, f"{title} works this way.", "generated", (page,),
                    "reference", evidence=f"The {title.lower()} rule.", evidence_source_id=page)


def by_topic(assignment, *args, **kwargs):
    return (question(assignment.unit.title, "true_false"), question(assignment.unit.title))


class QuizLogicTests(unittest.TestCase):
    def test_checked_topics_in_order_or_three_across_the_outline(self):
        self.assertEqual(choose_topics(13, [9, 2, 9, 40]), [9, 2])
        self.assertEqual(choose_topics(13, []), [1, 7, 13])
        self.assertEqual(choose_topics(4, []), [1, 3, 4])
        self.assertEqual(choose_topics(2, []), [1, 2])

    def test_each_question_is_built_from_its_topic(self):
        with patch("tutor.assessment.questions.generate_questions", side_effect=by_topic) as generate:
            quiz = build_quiz(OUTLINE, UNITS, build_index(PAGES), [3, 2])
        self.assertEqual([(i.id, i.topic_title, i.unit_id) for i in quiz.items],
                         [("quiz-1", "Loops", "unit-2"), ("quiz-2", "Updates", "unit-1")])
        self.assertTrue(all(i.question.kind == "multiple_choice" for i in quiz.items))
        focus = {call.args[0].unit.title: call.args[0] for call in generate.call_args_list}
        self.assertEqual(focus["Updates"].source_ids, ("p2",))
        self.assertEqual(focus["Updates"].unit.unit_id, "unit-1")
        self.assertEqual(generate.call_args.kwargs["questions_wanted"], 1)

    def test_topics_without_a_question_are_skipped_and_outages_surface(self):
        def mixed(assignment, *args, **kwargs):
            if assignment.unit.title == "Assignment":
                raise InsufficientEvidence("Only a heading.")
            if assignment.unit.title == "Updates":
                raise LLMError("Could not reach OpenAI.")
            return by_topic(assignment)
        with patch("tutor.assessment.questions.generate_questions", side_effect=mixed):
            quiz = build_quiz(OUTLINE, UNITS, build_index(PAGES), [1, 2, 3])
        self.assertEqual([i.topic_title for i in quiz.items], ["Loops"])
        self.assertEqual([(n, reason) for n, _, reason in quiz.skipped],
                         [(1, "Only a heading."), (2, "Could not reach OpenAI.")])
        with patch("tutor.assessment.questions.generate_questions", side_effect=LLMError("Down.")):
            with self.assertRaises(LLMError):
                build_quiz(OUTLINE, UNITS, build_index(PAGES), [1, 3])

    def test_grading_records_answers_and_marks_wrong_units(self):
        state = LearnerState(UNITS)
        quiz = Quiz((QuizItem("quiz-1", 3, "Loops", "unit-2", question("Loops")),
                     QuizItem("quiz-2", 1, "Assignment", "unit-1", question("Assignment"))))
        results = grade_quiz(state, quiz, [1, 0])
        self.assertEqual([r.correct for r in results], [False, True])
        self.assertEqual([(a.question_id, a.source) for a in state.answers()], [("quiz-2", "quiz"), ("quiz-1", "quiz")])
        self.assertEqual(state.focus_units(), ("unit-2",))


class QuizUITests(UITestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = OUTLINE
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title="Variables", topic_ids=[1, 2]), UnitStep(title="Loops", topic_ids=[3])]),
            Solution(tasks=[UnitTask(unit_number=1, objective="Store and update.", activity="Trace x."),
                            UnitTask(unit_number=2, objective="Repeat.", activity="Trace a loop.")]),
        ]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions", side_effect=by_topic))
        self.app = self.new_app()
        self.document = begin(self.app, *[page.text for page in PAGES])

    def panel(self):
        return self.app.main.container("quiz_panel")

    def text(self):
        panel = self.panel()
        extra = [i.value for group in (panel.markdown, panel.info, panel.warning, panel.success) for i in group]
        return "\n".join([visible_text(panel), *extra])

    def start(self):
        return self.app.main.container("quiz_start")

    def test_checked_topics_are_asked_one_at_a_time_with_each_answer_shown_at_once(self):
        self.assertIn("**Next: a quick check**", [m.value for m in self.start().markdown])
        self.app.checkbox(key="weak_topic_2").check().run()      # Loops first
        self.app.checkbox(key="weak_topic_0").check().run()      # then Assignment
        self.assertIn("One question for each topic you checked (2)", visible_text(self.start()))
        start_quick_check(self.app)
        self.assertEqual(self.app.session_state["setup_step"], 3)
        self.assertFalse(self.app.exception)
        # One question on screen, and nothing about its answer yet.
        self.assertEqual(len(self.panel().radio), 1)
        self.assertIn("**Loops**", [m.value for m in self.panel().markdown])
        self.assertEqual(self.app.main.progress[0].proto.text, "Question 1 of 2")
        self.assertTrue(self.app.button(key="quiz_submit").disabled)
        self.assertNotIn("Correct answer", self.text())

        self.app.radio(key="quiz_choice_quiz-1").set_value("3").run()     # wrong
        self.app.button(key="quiz_submit").click().run()
        text = self.text()
        self.assertIn("Question 1 · Loops: Not quite.", text)
        self.assertIn("Correct answer: 2", text)
        self.assertIn("In your material, page 3: “The loops rule.”", text)
        self.assertFalse(self.panel().radio)
        # The source page opens in a window; the check stays where it was.
        button(self.panel(), "Page 3").click().run()
        self.assertEqual(previewed_pdf(self.app), (self.document, [3]))
        self.assertIn("Question 1 · Loops: Not quite.", self.text())
        self.assertNotIn("quiz_continue", [b.key for b in self.app.button])
        self.app.button(key="quiz_next").click().run()

        self.assertIn("**Assignment**", [m.value for m in self.panel().markdown])
        self.app.radio(key="quiz_choice_quiz-2").set_value("2").run()     # right
        self.app.button(key="quiz_submit").click().run()
        text = self.text()
        self.assertIn("Question 2 · Assignment: Correct.", text)
        self.assertIn("marked this topic as not understood but answered correctly", text)
        # The answers are recorded only once the last one is in.
        self.assertFalse(self.app.session_state["learner_state"].answers())
        self.assertEqual(self.app.button(key="quiz_next").label, "See my results")
        self.app.button(key="quiz_next").click().run()

        text = self.text()
        self.assertIn("**1 of 2 correct.**", text)
        self.assertIn("The plan gives more time to: Loops.", text)
        self.assertIn("Your answers (2)", [e.label for e in self.panel().expander])
        self.assertEqual(len(self.app.session_state["learner_state"].answers()), 2)
        go_to_step(self.app, 2)
        self.assertIn("Done: 1 of 2 correct. More time for: Loops.", visible_text(self.start()))
        self.assertEqual(self.app.button(key="topics_next").label, "Continue to the plan →")
        self.assertNotIn("Start the quick check →", labels(self.app))

        create_plan(self.app, 4)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-2"))
        show_page(self.app, "Plan")
        plan = visible_text(self.app.main.container("plan_overview_panel"))
        self.assertIn("Quick check: 1 of 2 correct. More time for: Loops.", plan)
        # Unit names show the outline topics they cover.
        self.assertIn("More time for: Variables (topics: Assignment; Updates); Loops", plan)
        show_page(self.app, "Progress")
        self.assertIn("Quick check: 1 of 2 correct", [e.label for e in self.app.main.expander])

    def test_with_nothing_checked_up_to_three_topics_are_asked(self):
        self.assertIn("up to 3 questions", visible_text(self.start()))
        start_quick_check(self.app)
        for item in ("quiz-1", "quiz-2", "quiz-3"):
            answer_quiz(self.app, item, "2")
        self.assertIn("**3 of 3 correct.**", self.text())
        create_plan(self.app, 2)
        self.assertEqual(self.app.session_state["planned_weak"], ())

    def test_leaving_the_check_halfway_keeps_its_place(self):
        start_quick_check(self.app)
        answer_quiz(self.app, "quiz-1", "2")
        go_to_step(self.app, 2)
        self.assertEqual(self.app.button(key="topics_next").label, "Continue the quick check →")
        self.app.button(key="topics_next").click().run()
        self.assertEqual(self.app.main.progress[0].proto.text, "Question 2 of 3")
        # The plan step opens only once the check is done.
        self.assertTrue(self.app.button(key="step_4").disabled)
        self.generate.assert_called()
        self.assertEqual(self.generate.call_count, 3)

    def test_an_outage_can_be_retried(self):
        self.generate.side_effect = LLMError("Could not reach OpenAI.")
        start_quick_check(self.app)
        self.assertIn("Could not reach OpenAI.", self.panel().error[0].value)
        self.assertNotIn("quiz_continue", [b.key for b in self.app.button])
        self.generate.side_effect = by_topic
        button(self.panel(), "Try again").click().run()
        self.assertEqual(self.app.main.progress[0].proto.text, "Question 1 of 3")

    def test_the_check_can_be_skipped(self):
        self.app.checkbox(key="weak_topic_2").check().run()
        self.app.button(key="skip_initial_quiz").click().run()
        self.generate.assert_not_called()
        self.assertEqual(self.app.session_state["setup_step"], 4)
        go_to_step(self.app, 3)
        self.assertIn("You skipped the quick check", self.text())
        self.assertFalse(self.panel().radio)
        # From Topics, the check can still be taken instead.
        go_to_step(self.app, 2)
        self.assertIn("Start the quick check →", labels(self.app))
        create_plan(self.app, 3)
        # Checked topics still get more time.
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-2",))
        show_page(self.app, "Plan")
        self.assertIn("Quick check: skipped.", visible_text(self.app.main.container("plan_overview_panel")))
        show_page(self.app, "Progress")
        self.assertFalse([e for e in self.app.main.expander if e.label.startswith("Quick check")])
