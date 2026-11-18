import unittest
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import button, upload
from tests.test_pdf_preview import APP, previewed_pdf
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


def create_plan(app, days):
    app.number_input(key="study_target_days").set_value(days)
    button(app, "Create study plan").click().run()


def visible_text(app):
    return "\n".join(
        item.value
        for group in (app.subheader, app.text, app.caption, app.html, app.markdown, app.info)
        for item in group
    )


class PlanningUITests(unittest.TestCase):
    def setUp(self):
        self.outline = Outline(topics=[
            Topic(title="Update a variable", summary="Assign a new value.", source_ids=["p1"]),
            Topic(title="Trace a loop", summary="Follow each iteration.", source_ids=["p2"]),
        ])
        self.plan = UnitPlan(steps=[
            UnitStep(title="Read an assignment", topic_ids=[1]),
            UnitStep(title="Follow the loop", topic_ids=[2]),
        ])
        self.solution = Solution(tasks=[
            UnitTask(unit_number=1, objective="Describe an update.", activity="Find the assigned value."),
            UnitTask(unit_number=2, objective="Track each iteration.", activity="Trace the loop in the notes."),
        ])
        self.model = self.enterContext(patch("tutor.planning.units.generate_structured"))
        self.model.side_effect = [self.plan, self.solution]
        self.app = AppTest.from_file(APP).run()

    @patch("tutor.materials.outline.generate_outline")
    def test_reschedule_and_follow_a_planned_reading(self, generate):
        app = self.app
        generate.return_value = self.outline
        document = upload(app, "Variable updates", "Loop tracing")
        self.assertFalse(app.number_input)
        button(app, "Generate outline").click().run()
        target = app.number_input(key="study_target_days")
        self.assertEqual(target.label, "Target duration (days)")
        self.assertEqual(target.value, 7)
        self.model.assert_not_called()

        create_plan(app, 5)
        units = app.session_state["study_units"]
        five_days = app.session_state["study_plan"]
        self.assertEqual(len(five_days), 4)
        self.assertEqual(app.number_input(key="study_day").value, 1)
        self.assertIn("Day 1", [item.value for item in app.subheader])
        reading = visible_text(app)
        self.assertIn("5-day plan", reading)
        self.assertIn("Read an assignment", reading)
        self.assertIn("Describe an update.", reading)
        self.assertNotIn("Find the assigned value.", reading)
        self.assertNotRegex(reading, r"(?i)\b(?:mins?|minutes?)\b")
        self.assertEqual(app.button(key=f"plan_citation_1_{units[0].unit_id}_p1").label, "Page 1")

        app.number_input(key="study_day").set_value(2).run()
        self.assertIn("Find the assigned value.", visible_text(app))
        app.number_input(key="study_day").set_value(4).run()
        practice = visible_text(app)
        self.assertIn("Follow the loop", practice)
        self.assertIn("Trace the loop in the notes.", practice)
        self.assertNotRegex(practice, r"(?i)\b(?:mins?|minutes?)\b")
        app.button(key=f"plan_citation_4_{units[1].unit_id}_p2").click().run()
        self.assertEqual(previewed_pdf(app), (document, [2]))
        self.assertEqual(app.number_input(key="study_day").value, 4)
        self.assertEqual(app.session_state["study_plan"], five_days)

        create_plan(app, 10)
        ten_days = app.session_state["study_plan"]
        self.assertEqual(app.session_state["planned_days"], 10)
        self.assertEqual(app.session_state["study_units"], units)
        self.assertEqual(ten_days, five_days)
        app.number_input(key="study_day").set_value(10).run()
        self.assertIn("Day 10", [item.value for item in app.subheader])
        self.assertRegex(visible_text(app), r"(?i)\breview\b")
        self.assertFalse(any((item.key or "").startswith("plan_citation_") for item in app.button))
        create_plan(app, 2)
        self.assertEqual(app.number_input(key="study_day").value, 1)
        self.assertIn("Find the assigned value.", visible_text(app))
        generate.assert_called_once()
        self.assertEqual([call.kwargs["schema"] for call in self.model.call_args_list], [UnitPlan, Solution])
        self.assertFalse(app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_replacing_or_removing_a_document_clears_its_plan(self, generate):
        app = self.app
        replacement = Outline(topics=[
            Topic(title="Sort a list", summary="Arrange values in order.", source_ids=["p1"]),
        ])
        sort_plan = UnitPlan(steps=[UnitStep(title="Order a list", topic_ids=[1])])
        sort_solution = Solution(tasks=[
            UnitTask(unit_number=1, objective="Recognize sorted order.", activity="Compare two lists."),
        ])
        self.model.side_effect = [self.plan, self.solution, sort_plan, sort_solution]
        generate.side_effect = [self.outline, replacement]
        upload(app, "Variable updates", "Loop tracing")
        button(app, "Generate outline").click().run()
        create_plan(app, 3)

        upload(app, "Sorting")
        self.assert_plan_cleared()
        button(app, "Generate outline").click().run()
        self.assertEqual(app.number_input(key="study_target_days").value, 7)
        create_plan(app, 20)
        self.assertEqual(app.session_state["unit_plan"], sort_plan)
        self.assertEqual([unit.title for unit in app.session_state["study_units"]], ["Order a list"])
        self.assertEqual(len(app.session_state["study_plan"]), 2)
        app.number_input(key="study_day").set_value(20).run()
        self.assertRegex(visible_text(app), r"(?i)\breview\b")
        app.file_uploader[0].clear().run()
        self.assert_plan_cleared()
        self.assertFalse(app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_retry_continues_from_the_last_validated_stage(self, generate):
        app = self.app
        generate.return_value = self.outline
        self.model.side_effect = [
            LLMError("Could not plan units."), self.plan, LLMError("Could not prepare tasks."), self.solution,
        ]
        upload(app, "Variable updates", "Loop tracing")
        button(app, "Generate outline").click().run()

        create_plan(app, 5)
        self.assertIn("Could not plan units.", [item.value for item in app.error])
        self.assertNotIn("unit_plan", app.session_state)
        self.assertNotIn("study_plan", app.session_state)

        create_plan(app, 5)
        self.assertIn("Could not prepare tasks.", [item.value for item in app.error])
        self.assertEqual(app.session_state["unit_plan"], self.plan)
        self.assertNotIn("study_units", app.session_state)
        self.assertNotIn("study_plan", app.session_state)
        app.selectbox(key="pdf_page_number").select(2).run()
        self.assertEqual(self.model.call_count, 3)

        create_plan(app, 10)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["planned_days"], 10)
        self.assertEqual(len(app.session_state["study_plan"]), 4)
        self.assertEqual([call.kwargs["schema"] for call in self.model.call_args_list],
                         [UnitPlan, UnitPlan, Solution, Solution])
        generate.assert_called_once()

    @patch("tutor.materials.outline.generate_outline")
    def test_existing_session_redistributes_legacy_segments_without_model_calls(self, generate):
        app = self.app
        generate.return_value = self.outline
        upload(app, "Variable updates", "Loop tracing")
        button(app, "Generate outline").click().run()
        create_plan(app, 5)
        units = app.session_state["study_units"]
        expected_days = app.session_state["study_plan"]
        app.session_state["study_plan"] = (SimpleNamespace(number=1, segments=(), minutes=30),)
        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["study_units"], units)
        self.assertEqual(app.session_state["study_plan"], expected_days)
        self.assertIn("Read an assignment", visible_text(app))
        self.assertNotRegex(visible_text(app), r"(?i)\b(?:mins?|minutes?)\b")
        self.assertEqual(self.model.call_count, 2)
        generate.assert_called_once()

    def assert_plan_cleared(self):
        self.assertFalse(self.app.number_input)
        self.assertNotIn("Create study plan", [item.label for item in self.app.button])
        for key in ("unit_plan", "study_units", "study_plan", "planned_days", "study_target_days", "study_day"):
            self.assertNotIn(key, self.app.session_state)
