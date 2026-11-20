import unittest
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button, previewed_pdf
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


def finish_quiz(app):
    """Take the initial quiz with no questions, which leads straight to the plan controls."""
    with patch("tutor.assessment.questions.generate_questions", return_value=()):
        button(app.sidebar, "Start initial quiz").click().run()


def create_plan(app, days):
    if not any(widget.label == "Create study plan" for widget in app.sidebar.button):
        finish_quiz(app)
    app.sidebar.number_input(key="study_target_days").set_value(days)
    button(app.sidebar, "Create study plan").click().run()


def show_view(app, name):
    app.segmented_control(key="right_view").set_value(name).run()


def open_day(app, day):
    show_view(app, "Today")
    app.segmented_control(key="day_picker").set_value(day).run()


def metrics(app):
    return {metric.label: metric.value for metric in app.main.metric}


def visible_text(app):
    return "\n".join(
        item.value
        for group in (app.subheader, app.text, app.caption, app.html, app.markdown, app.info)
        for item in group
    )


def document_row(app):
    return next(
        block for block in app.main.children.values()
        if block.type == "flex_container" and block.get("component_instance")
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
    def test_views_beside_the_pdf_follow_the_steps(self, generate):
        app = self.app
        generate.return_value = self.outline
        document = upload(app, "Variable updates", "Loop tracing")
        self.assertIn("**2 · Outline**", app.main.container("steps").markdown[0].value)
        button(app.sidebar, "Generate outline").click().run()
        left, right = document_row(app).children.values()
        self.assertEqual(previewed_pdf(left), (document, [1]))
        self.assertEqual(app.segmented_control(key="right_view").options, ["Outline"])
        self.assertIn("Ask the tutor", [h.value for h in app.main.header])
        self.assertIn("Update a variable", visible_text(right.container("outline_panel")))
        self.assertIn("**3 · Mark & quiz**", app.main.container("steps").markdown[0].value)
        # Each column is a single panel of the same height, so the two line up exactly. The page
        # controls are inside the PDF panel, and the view bar inside the view panel.
        left_panel, = left.children.values()
        right_panel, = right.children.values()
        self.assertEqual((left_panel.key, right_panel.key), ("pdf_preview_panel", "view_panel"))
        self.assertEqual(left_panel.proto.height_config.pixel_height, right_panel.proto.height_config.pixel_height)
        self.assertTrue(left_panel.container("pdf_page_controls").button)
        self.assertEqual(list(right_panel.children.values())[0].key, "right_view")
        # The extracted text is a collapsed section at the bottom of the page, after Ask the tutor.
        order = [getattr(block, "label", None) or getattr(block, "value", None)
                 for block in app.main.children.values()]
        self.assertTrue(str(order[-1]).startswith("Extracted text"))
        (extracted,) = [e for e in app.main.expander if e.label.startswith("Extracted text")]
        self.assertEqual(extracted.label, "Extracted text · page 1")
        self.assertEqual(app.main.container("extracted_text_panel").code[0].value.strip(), "Variable updates")

        create_plan(app, 2)
        left, right = document_row(app).children.values()
        self.assertEqual(previewed_pdf(left), (document, [1]))
        self.assertEqual(app.segmented_control(key="right_view").value, "Today")
        self.assertEqual(app.segmented_control(key="right_view").options, ["Today", "Plan", "Progress"])
        self.assertIn("Read an assignment", visible_text(right.container("plan_panel")))
        self.assertIn("**5 · Study**", app.main.container("steps").markdown[0].value)
        self.assertTrue(app.main.container("plan_panel").proto.height_config.pixel_height > 0)

        show_view(app, "Plan")
        button(app.main.container("plan_overview_panel"), "Page 2").click().run()
        self.assertEqual(previewed_pdf(app), (document, [2]))
        self.assertEqual(app.main.container("extracted_text_panel").code[0].value.strip(), "Loop tracing")
        self.assertEqual(app.session_state["current_day"], 1)
        generate.assert_called_once()
        self.assertEqual(self.model.call_count, 2)
        self.assertFalse(app.exception)

    @patch("tutor.materials.outline.generate_outline")
    def test_reschedule_and_follow_a_planned_reading(self, generate):
        app = self.app
        generate.return_value = self.outline
        document = upload(app, "Variable updates", "Loop tracing")
        self.assertFalse(app.number_input)
        button(app, "Generate outline").click().run()
        # The plan controls appear only after the initial quiz, which builds the units.
        self.assertNotIn("study_target_days", [w.key for w in app.sidebar.number_input])
        self.model.assert_not_called()
        finish_quiz(app)
        target = app.number_input(key="study_target_days")
        self.assertEqual(target.label, "Target duration (days)")
        self.assertEqual(target.value, 7)

        create_plan(app, 5)
        units = app.session_state["study_units"]
        five_days = app.session_state["study_plan"]
        self.assertEqual(len(five_days), 4)
        self.assertEqual(app.segmented_control(key="day_picker").value, 1)
        self.assertIn("Day 1", [item.value for item in app.subheader])
        reading = visible_text(app)
        self.assertIn("Read an assignment", reading)
        self.assertIn("Describe an update.", reading)
        self.assertNotIn("Find the assigned value.", reading)
        self.assertNotRegex(reading, r"(?i)\b(?:mins?|minutes?)\b")
        self.assertEqual(app.button(key=f"plan_citation_1_{units[0].unit_id}_p1").label, "Page 1")

        open_day(app, 2)
        self.assertIn("Find the assigned value.", visible_text(app))
        open_day(app, 4)
        practice = visible_text(app)
        self.assertIn("Follow the loop", practice)
        self.assertIn("Trace the loop in the notes.", practice)
        self.assertNotRegex(practice, r"(?i)\b(?:mins?|minutes?)\b")
        app.button(key=f"plan_citation_4_{units[1].unit_id}_p2").click().run()
        self.assertEqual(previewed_pdf(app), (document, [2]))
        self.assertEqual(app.segmented_control(key="day_picker").value, 4)
        self.assertEqual(app.session_state["study_plan"], five_days)
        show_view(app, "Plan")
        self.assertEqual(metrics(app)["Goal"], "5 days")
        self.assertEqual(metrics(app)["Plan"], "4 days")
        self.assertEqual([row["Day"] for row in app.dataframe[0].value.to_dict("records")], [1, 2, 3, 4, 5])

        create_plan(app, 10)
        ten_days = app.session_state["study_plan"]
        self.assertEqual(app.session_state["planned_days"], 10)
        self.assertEqual(app.session_state["study_units"], units)
        self.assertEqual(ten_days, five_days)
        open_day(app, 10)
        self.assertIn("Day 10", [item.value for item in app.subheader])
        self.assertRegex(visible_text(app), r"(?i)\breview\b")
        self.assertFalse(any((item.key or "").startswith("plan_citation_") for item in app.button))
        create_plan(app, 2)
        self.assertEqual(app.segmented_control(key="day_picker").value, 1)
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
        finish_quiz(app)
        self.assertEqual(app.number_input(key="study_target_days").value, 7)
        create_plan(app, 20)
        self.assertEqual(app.session_state["unit_plan"], sort_plan)
        self.assertEqual([unit.title for unit in app.session_state["study_units"]], ["Order a list"])
        self.assertEqual(len(app.session_state["study_plan"]), 2)
        open_day(app, 20)
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

        # The units are built when the initial quiz starts; each failure can be retried there.
        finish_quiz(app)
        self.assertIn("Could not plan units.", [item.value for item in app.error])
        self.assertNotIn("unit_plan", app.session_state)
        self.assertNotIn("quiz", app.session_state)

        finish_quiz(app)
        self.assertIn("Could not prepare tasks.", [item.value for item in app.error])
        self.assertEqual(app.session_state["unit_plan"], self.plan)
        self.assertNotIn("study_units", app.session_state)
        self.assertNotIn("quiz", app.session_state)
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
