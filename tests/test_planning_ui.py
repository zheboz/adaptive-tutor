from types import SimpleNamespace
from unittest.mock import patch

from tests.test_pdf_preview import button, previewed_pdf
from tests.ui_helpers import (
    UITestCase, begin, create_plan, go_to_step, labels, metrics, open_day, plan_days, show_page, show_panel,
    visible_text,
)
from tutor.llm import LLMError
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


class PlanningUITests(UITestCase):
    def setUp(self):
        super().setUp()
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
        self.generate = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        self.generate.return_value = self.outline
        self.app = self.new_app()

    def test_the_plan_step_previews_the_days_before_studying_starts(self):
        app = self.app
        begin(app, "Variable updates", "Loop tracing")
        # The units are planned in the background as soon as the outline is ready.
        self.assertIn("units_started", app.session_state)
        self.assertFalse(app.number_input)
        app.button(key="skip_initial_quiz").click().run()
        self.assertEqual(app.session_state["setup_step"], 4)
        target = app.number_input(key="study_target_days")
        self.assertEqual(target.value, 7)
        self.assertIn("2 learning units over 7 days.", [c.value for c in app.caption])
        rows = plan_days(app)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[-1]["Study"], "Optional review")
        # The preview follows the number of days at once, with no model call.
        target.set_value(2).run()
        rows = plan_days(app)
        self.assertEqual([r["Study"] for r in rows], ["Study: Read an assignment", "Study: Follow the loop"])
        self.assertEqual(self.model.call_count, 2)
        self.assertNotIn("planned_days", app.session_state)

        # Going back and forth keeps the number of days.
        go_to_step(app, 2)
        go_to_step(app, 4)
        self.assertEqual(app.number_input(key="study_target_days").value, 2)
        app.button(key="start_studying").click().run()
        self.assertEqual(app.session_state["planned_days"], 2)
        self.assertEqual(app.segmented_control(key="workspace_page").value, "Today")
        # Setup is over: the step bar is gone.
        self.assertNotIn("step_1", [b.key for b in app.button])
        self.assertFalse(app.exception)

    def test_today_puts_the_reader_beside_the_day(self):
        app = self.app
        document = begin(app, "Variable updates", "Loop tracing")
        create_plan(app, 2)
        self.assertEqual(app.segmented_control(key="workspace_page").options, ["Today", "Plan", "Progress"])
        self.assertEqual(app.segmented_control(key="today_tab").options, ["Study", "Ask the tutor"])
        self.assertEqual(previewed_pdf(app), (document, [1]))
        reader = app.main.container("pdf_preview_panel")
        panel = app.main.container("today_panel")
        self.assertEqual(reader.proto.height_config.pixel_height, panel.proto.height_config.pixel_height)
        self.assertIn("Read an assignment", visible_text(app.main.container("study_panel")))

        # The reader's own controls, and its Text view of what the tutor reads.
        self.assertTrue(button(reader, "Previous page").disabled)
        button(reader, "Next page").click().run()
        self.assertEqual(previewed_pdf(app), (document, [2]))
        app.segmented_control(key="reader_mode").set_value("Text").run()
        self.assertFalse(app.get("component_instance"))
        self.assertEqual(app.main.container("extracted_text_panel").code[0].value.strip(), "Loop tracing")
        app.segmented_control(key="reader_mode").set_value("Page").run()
        app.selectbox(key="pdf_page_number").select(1).run()
        self.assertEqual(previewed_pdf(app), (document, [1]))

        # Page links beside the reader turn its page; elsewhere they open a window.
        open_day(app, 2)
        units = app.session_state["study_units"]
        app.button(key=f"plan_citation_2_{units[1].unit_id}_p2").click().run()
        self.assertEqual(previewed_pdf(app), (document, [2]))
        self.assertEqual(app.segmented_control(key="day_picker").value, 2)
        show_page(app, "Plan")
        self.assertFalse(app.get("component_instance"))
        app.button(key="citation_0_p1").click().run()
        self.assertEqual(previewed_pdf(app), (document, [1]))
        self.assertEqual(app.segmented_control(key="workspace_page").value, "Plan")
        self.generate.assert_called_once()
        self.assertEqual(self.model.call_count, 2)
        self.assertFalse(app.exception)

    def test_reschedule_and_follow_a_planned_reading(self):
        app = self.app
        begin(app, "Variable updates", "Loop tracing")
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
        # The open day is kept while the chat is beside the PDF.
        show_panel(app, "Ask the tutor")
        show_panel(app, "Study")
        self.assertEqual(app.segmented_control(key="day_picker").value, 4)
        show_page(app, "Plan")
        self.assertEqual(metrics(app)["Goal"], "5 days")
        self.assertEqual(metrics(app)["Plan"], "4 days")
        self.assertEqual([row["Day"] for row in plan_days(app)], [1, 2, 3, 4, 5])

        create_plan(app, 10)
        ten_days = app.session_state["study_plan"]
        self.assertEqual(app.session_state["planned_days"], 10)
        self.assertEqual(app.session_state["study_units"], units)
        self.assertEqual(ten_days, five_days)
        self.assertEqual(app.segmented_control(key="workspace_page").value, "Today")
        open_day(app, 10)
        self.assertIn("Day 10", [item.value for item in app.subheader])
        self.assertRegex(visible_text(app), r"(?i)\breview\b")
        self.assertFalse(any((item.key or "").startswith("plan_citation_") for item in app.button))
        create_plan(app, 2)
        self.assertEqual(app.segmented_control(key="day_picker").value, 1)
        self.assertIn("Find the assigned value.", visible_text(app))
        self.generate.assert_called_once()
        self.assertEqual([call.kwargs["schema"] for call in self.model.call_args_list], [UnitPlan, Solution])
        self.assertFalse(app.exception)

    def test_starting_over_clears_the_material_and_its_plan(self):
        app = self.app
        replacement = Outline(topics=[
            Topic(title="Sort a list", summary="Arrange values in order.", source_ids=["p1"]),
        ])
        sort_plan = UnitPlan(steps=[UnitStep(title="Order a list", topic_ids=[1])])
        sort_solution = Solution(tasks=[
            UnitTask(unit_number=1, objective="Recognize sorted order.", activity="Compare two lists."),
        ])
        self.model.side_effect = [self.plan, self.solution, sort_plan, sort_solution]
        self.generate.side_effect = [self.outline, replacement]
        begin(app, "Variable updates", "Loop tracing")
        create_plan(app, 3)

        app.button(key="start_over").click().run()
        self.assert_plan_cleared()
        self.assertEqual(app.session_state["setup_step"], 1)
        begin(app, "Sorting")
        create_plan(app, 20)
        self.assertEqual(app.session_state["unit_plan"], sort_plan)
        self.assertEqual([unit.title for unit in app.session_state["study_units"]], ["Order a list"])
        self.assertEqual(len(app.session_state["study_plan"]), 2)
        open_day(app, 20)
        self.assertRegex(visible_text(app), r"(?i)\breview\b")
        self.assertFalse(app.exception)

    def test_retry_continues_from_the_last_validated_stage(self):
        app = self.app
        self.model.side_effect = [
            LLMError("Could not plan units."), self.plan, LLMError("Could not prepare tasks."), self.solution,
        ]
        begin(app, "Variable updates", "Loop tracing")

        # The units are needed when the learner moves past Topics; each failure can be retried there.
        app.button(key="skip_initial_quiz").click().run()
        self.assertIn("Could not plan units.", [item.value for item in app.error])
        self.assertNotIn("unit_plan", app.session_state)
        self.assertNotIn("quiz", app.session_state)
        self.assertEqual(app.session_state["setup_step"], 2)

        app.button(key="skip_initial_quiz").click().run()
        self.assertIn("Could not prepare tasks.", [item.value for item in app.error])
        self.assertEqual(app.session_state["unit_plan"], self.plan)
        self.assertNotIn("study_units", app.session_state)
        go_to_step(app, 1)
        go_to_step(app, 2)
        self.assertEqual(self.model.call_count, 3)

        create_plan(app, 10)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["planned_days"], 10)
        self.assertEqual(len(app.session_state["study_plan"]), 4)
        self.assertEqual([call.kwargs["schema"] for call in self.model.call_args_list],
                         [UnitPlan, UnitPlan, Solution, Solution])
        self.generate.assert_called_once()

    def test_existing_session_redistributes_legacy_segments_without_model_calls(self):
        app = self.app
        begin(app, "Variable updates", "Loop tracing")
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
        self.generate.assert_called_once()

    def assert_plan_cleared(self):
        self.assertFalse(self.app.number_input)
        self.assertNotIn("Start studying →", labels(self.app))
        for key in ("pdf_bytes", "unit_plan", "study_units", "study_plan", "planned_days", "draft_days"):
            self.assertNotIn(key, self.app.session_state)
