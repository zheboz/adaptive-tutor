import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button, previewed_pdf
from tests.test_planning_ui import create_plan, show_view, visible_text
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


class QuizUITests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = OUTLINE
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title="Variables", topic_ids=[1, 2]), UnitStep(title="Loops", topic_ids=[3])]),
            Solution(tasks=[UnitTask(unit_number=1, objective="Store and update.", activity="Trace x."),
                            UnitTask(unit_number=2, objective="Repeat.", activity="Trace a loop.")]),
        ]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions", side_effect=by_topic))
        self.app = AppTest.from_file(APP, default_timeout=10).run()
        self.document = upload(self.app, *[page.text for page in PAGES])

    def panel(self):
        return self.app.main.container("quiz_panel")

    def text(self):
        panel = self.panel()
        extra = [i.value for group in (panel.markdown, panel.info, panel.warning, panel.success) for i in group]
        return "\n".join([visible_text(panel), *extra])

    def plan_controls(self):
        return [w.label for w in self.app.button if w.label == "Create study plan"]

    def start(self):
        return self.app.main.container("quiz_start")

    def test_checked_topics_are_quizzed_in_order_then_answers_then_the_plan(self):
        # The quiz starts below the outline, where the topics are checked; there is no sidebar.
        self.assertIn("**Initial quiz**", [m.value for m in self.start().markdown])
        self.assertFalse(self.app.sidebar.children)
        self.assertFalse(self.plan_controls())
        self.app.checkbox(key="weak_topic_2").check().run()      # Loops first
        self.app.checkbox(key="weak_topic_0").check().run()      # then Assignment
        self.assertIn("One question for each topic you checked (2)", visible_text(self.start()))
        button(self.start(), "Start initial quiz").click().run()
        self.assertEqual(self.app.segmented_control(key="right_view").value, "Initial quiz")
        self.assertFalse(self.app.exception)
        self.assertEqual([m.value for m in self.panel().markdown][:2],
                         ["**Question 1 · Loops**", "**Question 2 · Assignment**"])
        self.assertFalse(self.plan_controls())
        self.assertNotIn("Correct answer", self.text())

        self.app.radio(key="quiz_choice_quiz-1").set_value("3")    # wrong
        button(self.panel(), "Submit answers").click().run()
        self.assertIn("Answer every question before submitting.", self.text())
        self.app.radio(key="quiz_choice_quiz-2").set_value("2")    # right
        button(self.panel(), "Submit answers").click().run()

        text = self.text()
        self.assertIn("1 of 2 correct.", text)
        self.assertIn("Question 1 · Loops: Not quite.", text)
        self.assertIn("Correct answer: 2", text)
        self.assertIn("In your material, page 3: “The loops rule.”", text)
        self.assertIn("Question 2 · Assignment: Correct.", text)
        self.assertIn("marked this topic as not understood but answered correctly", text)
        button(self.panel(), "Page 3").click().run()
        self.assertEqual(previewed_pdf(self.app), (self.document, [3]))
        # The plan is created right below the results.
        self.assertTrue(self.panel().number_input(key="study_target_days"))
        self.assertTrue(self.plan_controls())
        self.assertEqual(self.app.segmented_control(key="right_view").options,
                         ["Outline", "Initial quiz", "Progress"])
        show_view(self.app, "Outline")
        self.assertIn("Done: 1 of 2 correct. More time for: Loops.", visible_text(self.start()))

        create_plan(self.app, 4)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-2"))
        show_view(self.app, "Plan")
        plan = visible_text(self.app.main.container("plan_overview_panel"))
        self.assertIn("Initial quiz: 1 of 2 correct. More time for: Loops.", plan)
        # Unit names show the outline topics they cover.
        self.assertIn("More time for: Variables (topics: Assignment; Updates); Loops", plan)
        self.assertNotIn("Start initial quiz", [b.label for b in self.app.button])
        show_view(self.app, "Progress")
        self.assertIn("Initial quiz: 1 of 2 correct", [e.label for e in self.app.main.expander])

    def test_with_nothing_checked_up_to_three_topics_are_quizzed(self):
        self.assertIn("up to 3 questions", visible_text(self.start()))
        button(self.start(), "Start initial quiz").click().run()
        self.assertEqual(len(self.panel().radio), 3)
        for item, option in (("quiz-1", "2"), ("quiz-2", "2"), ("quiz-3", "2")):
            self.app.radio(key=f"quiz_choice_{item}").set_value(option)
        button(self.panel(), "Submit answers").click().run()
        self.assertIn("3 of 3 correct.", self.text())
        create_plan(self.app, 2)
        self.assertEqual(self.app.session_state["planned_weak"], ())

    def test_an_outage_can_be_retried(self):
        self.generate.side_effect = LLMError("Could not reach OpenAI.")
        button(self.start(), "Start initial quiz").click().run()
        self.assertIn("Could not reach OpenAI.", self.panel().error[0].value)
        self.assertFalse(self.plan_controls())
        self.generate.side_effect = by_topic
        button(self.panel(), "Try again").click().run()
        self.assertEqual(len(self.panel().radio), 3)

    def test_the_quiz_can_be_skipped(self):
        self.app.checkbox(key="weak_topic_2").check().run()
        button(self.start(), "Skip the quiz").click().run()
        self.generate.assert_not_called()
        self.assertEqual(self.app.segmented_control(key="right_view").value, "Initial quiz")
        self.assertIn("You skipped the initial quiz", self.text())
        self.assertFalse(self.panel().radio)
        self.assertTrue(self.plan_controls())
        self.assertIn("**4 · Plan**", self.app.main.container("steps").markdown[0].value)
        create_plan(self.app, 3)
        # Checked topics still get more time.
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-2",))
        show_view(self.app, "Plan")
        self.assertIn("Initial quiz: skipped.", visible_text(self.app.main.container("plan_overview_panel")))
        show_view(self.app, "Progress")
        self.assertFalse([e for e in self.app.main.expander if e.label.startswith("Initial quiz")])
