import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button, previewed_pdf
from tests.test_planning_ui import create_plan, document_row, visible_text
from tutor.assessment import questions
from tutor.assessment.questions import Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


def practice_text(app):
    panel = app.main.container("plan_panel")
    feedback = [item.value for group in (panel.success, panel.warning, panel.error, panel.info) for item in group]
    return "\n".join([visible_text(panel), *(radio.label for radio in panel.radio), *feedback])


class PracticeUITests(unittest.TestCase):
    def setUp(self):
        topics = [
            Topic(title="Assignment", summary="Trace the value of x.", source_ids=["p1"]),
            Topic(title="Iteration", summary="Trace loop iterations.", source_ids=["p2"]),
        ]
        self.outline = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        self.outline.return_value = Outline(topics=topics)
        self.planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        self.plan = UnitPlan(steps=[
            UnitStep(title=topic.title, topic_ids=[n]) for n, topic in enumerate(topics, 1)
        ])
        self.solution = Solution(tasks=[
            UnitTask(unit_number=n, objective=topic.summary, activity=f"Explain {topic.title.lower()}.")
            for n, topic in enumerate(topics, 1)
        ])
        self.planner.side_effect = [self.plan, self.solution]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions"))
        self.assignment = Question(
            kind="multiple_choice", prompt="Which value is assigned to x?", options=("2", "3", "4"),
            correct_index=0, explanation="The right side of the assignment is 2.", origin="generated",
            source_ids=("p1",), answer_origin="reference",
        )
        self.iteration = Question(
            kind="true_false", prompt="A loop can execute twice.", options=("True", "False"),
            correct_index=0, explanation="The example loops over two items.", origin="pdf",
            source_ids=("p2", "p3"), answer_origin="pdf",
        )
        self.app = AppTest.from_file(APP).run()
        self.document = upload(
            self.app, "Assignment: x = 2.", "Iteration: loop over two items.",
            "Practice: True or false? A loop can execute twice. Answer: True.",
        )
        button(self.app.sidebar, "Generate outline").click().run()

    def generate_daily(self):
        button(self.app.main.container("plan_panel"), "Generate daily practice").click().run()
        self.assertFalse(self.app.exception)

    def test_answer_and_citation_follow_a_unit_to_another_day(self):
        app = self.app
        self.assertEqual([col.proto.weight for col in document_row(app).children.values()], [0.5, 0.5])
        create_plan(app, 1)
        left, right = document_row(app).children.values()
        self.assertAlmostEqual(left.proto.weight / right.proto.weight, 1.5)
        self.generate.assert_not_called()
        self.generate.side_effect = [(self.assignment,), (self.iteration,)]
        self.generate_daily()
        self.assertEqual([call.args[0].unit.title for call in self.generate.call_args_list],
                         ["Assignment", "Iteration"])
        self.assertEqual([radio.options for radio in app.radio],
                         [list(self.assignment.options), list(self.iteration.options)])
        self.assertIn(self.assignment.prompt, practice_text(app))
        self.assertIn(self.iteration.prompt, practice_text(app))
        self.assertIn("From PDF", practice_text(app))
        self.assertIn("Generated from PDF", practice_text(app))
        self.assertNotIn(self.iteration.explanation, practice_text(app))

        app.radio[1].set_value("False").run()
        checks = [widget for widget in app.button if widget.label == "Check answer"]
        checks[1].click().run()
        self.assertIn(self.iteration.explanation, practice_text(app))
        self.assertIn("Correct answer", practice_text(app))
        self.assertIn("PDF answer key", practice_text(app))
        button(app.main.container("plan_panel"), "Page 3").click().run()
        self.assertEqual(previewed_pdf(app), (self.document, [3]))
        self.assertEqual(self.generate.call_count, 2)

        create_plan(app, 2)
        self.assertIn(self.assignment.prompt, practice_text(app))
        self.assertNotIn(self.iteration.prompt, practice_text(app))
        app.radio[0].set_value("2").run()
        button(app, "Check answer").click().run()
        self.assertIn("Correct.", practice_text(app))
        self.assertIn("Model reference answer", practice_text(app))
        app.number_input(key="study_day").set_value(2).run()
        self.assertIn(self.iteration.explanation, practice_text(app))
        self.assertEqual(app.radio[0].index, 1)
        self.assertTrue(app.radio[0].disabled)
        self.assertEqual(self.generate.call_count, 2)

    def test_partial_failure_only_retries_unavailable_assignment(self):
        self.generate.side_effect = [(self.assignment,), LLMError("Retry this exercise."), (self.iteration,)]
        create_plan(self.app, 1)
        self.generate_daily()
        self.assertIn("Retry this exercise.", practice_text(self.app))
        self.assertIn(self.assignment.prompt, practice_text(self.app))
        self.assertNotIn(self.iteration.prompt, practice_text(self.app))
        self.generate_daily()
        self.assertIn(self.iteration.prompt, practice_text(self.app))
        self.assertEqual([call.args[0].unit.title for call in self.generate.call_args_list],
                         ["Assignment", "Iteration", "Iteration"])

    def test_insufficient_material_is_separate_from_a_retryable_verification_error(self):
        self.generate.side_effect = [
            questions.InsufficientEvidence("The page is only an agenda."), questions.PracticeError("Unverifiable citation."),
            (self.iteration,),
        ]
        create_plan(self.app, 1)
        self.generate_daily()
        panel = self.app.main.container("plan_panel")
        self.assertEqual(len(panel.error), 1)
        self.assertIn("verify a question for Iteration", panel.error[0].value)
        self.assertEqual(len(panel.info), 1)
        self.assertEqual(panel.info[0].value, "No practice for this item. The page is only an agenda.")
        self.app.run()
        self.assertIn("verify a question for Iteration", practice_text(self.app))
        self.generate_daily()
        panel = self.app.main.container("plan_panel")
        self.assertFalse(panel.error)
        self.assertTrue(panel.info)
        self.assertNotIn("Generate daily practice", [widget.label for widget in panel.button])
        self.assertIn(self.iteration.prompt, practice_text(self.app))
        self.assertEqual([call.args[0].unit.title for call in self.generate.call_args_list],
                         ["Assignment", "Iteration", "Iteration"])

    def test_request_failure_names_the_item_and_other_items_can_succeed(self):
        self.generate.side_effect = [LLMError("Could not reach OpenAI."), (self.iteration,), (self.assignment,)]
        create_plan(self.app, 1)
        self.generate_daily()
        self.assertIn("request for Assignment failed. Could not reach OpenAI.", practice_text(self.app))
        self.assertIn(self.iteration.prompt, practice_text(self.app))
        self.generate_daily()
        self.assertFalse(self.app.main.container("plan_panel").error)
        self.assertEqual([call.args[0].unit.title for call in self.generate.call_args_list],
                         ["Assignment", "Iteration", "Assignment"])

    def test_the_full_assigned_reading_remains_available_after_retrieval(self):
        self.generate.side_effect = [(self.assignment,), (self.iteration,)]
        create_plan(self.app, 1)
        with patch("tutor.assessment.retrieval.retrieve", return_value=()):
            self.generate_daily()
        seen = []
        for call in self.generate.call_args_list:
            self.assertEqual(call.args[1], ())
            seen.append([p.source_id for p in call.kwargs["assigned_reading"]])
        self.assertEqual(seen, [["p1"], ["p2"]])

    def test_reading_different_pages_of_one_unit_has_different_practice(self):
        self.planner.side_effect = [
            UnitPlan(steps=[UnitStep(title="Trace a loop variable", topic_ids=[1, 2])]),
            Solution(tasks=[UnitTask(unit_number=1, objective="Trace a variable.", activity="Follow a loop.")]),
        ]
        self.generate.side_effect = [(self.assignment,), (self.iteration,)]
        create_plan(self.app, 3)
        self.generate_daily()
        self.app.number_input(key="study_day").set_value(2).run()
        self.assertNotIn(self.assignment.prompt, practice_text(self.app))
        self.generate_daily()
        self.assertIn(self.iteration.prompt, practice_text(self.app))
        assignments = [call.args[0] for call in self.generate.call_args_list]
        self.assertEqual([part.source_ids for part in assignments], [("p1",), ("p2",)])
        self.assertEqual(assignments[0].unit.unit_id, assignments[1].unit.unit_id)
        self.app.number_input(key="study_day").set_value(1).run()
        self.assertIn(self.assignment.prompt, practice_text(self.app))
        self.assertNotIn(self.iteration.prompt, practice_text(self.app))
        self.assertEqual(self.generate.call_count, 2)

    def test_review_days_and_replacement_do_not_reuse_unrelated_questions(self):
        app = self.app
        self.generate.side_effect = [(self.assignment,), (self.iteration,)]
        create_plan(app, 1)
        self.generate_daily()
        create_plan(app, 5)
        app.number_input(key="study_day").set_value(5).run()
        self.assertFalse(app.radio)
        self.assertNotIn("Generate daily practice", [widget.label for widget in app.button])

        self.planner.side_effect = [self.plan, self.solution]
        upload(app, "New assignment: x = 5.", "New iteration: loop over five items.")
        button(app.sidebar, "Generate outline").click().run()
        create_plan(app, 1)
        self.assertFalse(app.radio)
        self.assertNotIn(self.assignment.prompt, practice_text(app))
        self.assertEqual(self.generate.call_count, 2)
        app.sidebar.file_uploader[0].clear().run()
        self.assertFalse(app.radio)
        self.assertNotIn("Generate daily practice", [widget.label for widget in app.button])
        self.assertFalse(app.exception)
