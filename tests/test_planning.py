from itertools import groupby
import json
import unittest
from unittest.mock import patch

from tutor.materials.outline import Outline, Topic
from tutor.planning import PlanningError, StudyUnit, build_study_units, plan_units, schedule_units
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


class PlanAndSolveTests(unittest.TestCase):
    def setUp(self):
        self.outline = Outline(topics=[
            Topic(title="赋值", summary="跟踪变量的初始值。", source_ids=["p2"]),
            Topic(title="计数", summary="观察每次迭代后的计数。", source_ids=["p2", "p3"]),
            Topic(title="终止条件", summary="判断循环何时结束。", source_ids=["p5"]),
        ])
        self.plan = UnitPlan(steps=[
            UnitStep(title="初始状态与更新", topic_ids=[1, 2]),
            UnitStep(title="末次迭代", topic_ids=[2, 3]),
        ])
        # The model writes its results in reverse order. Match them to the plan by ID.
        self.solution = Solution(tasks=[
            UnitTask(unit_number=2, objective="判断最终值。", activity="找出最后一次更新。"),
            UnitTask(unit_number=1, objective="解释首次更新。", activity="记录变量更新前后的值。"),
        ])

    @patch("tutor.planning.units.generate_structured")
    def test_solve_executes_the_planned_units_and_retains_their_sources(self, generate):
        generate.side_effect = [self.plan, self.solution]
        units = build_study_units(self.outline)

        plan_call, solve_call = generate.call_args_list
        self.assertIs(plan_call.kwargs["schema"], UnitPlan)
        self.assertIs(solve_call.kwargs["schema"], Solution)
        topic_rows = [
            {"topic_id": number, **topic.model_dump()}
            for number, topic in enumerate(self.outline.topics, start=1)
        ]
        steps = [
            {"unit_number": number, **step.model_dump()}
            for number, step in enumerate(self.plan.steps, start=1)
        ]
        self.assertEqual(json.loads(plan_call.kwargs["content"]), {"topics": topic_rows})
        self.assertEqual(json.loads(solve_call.kwargs["content"]), {"topics": topic_rows, "steps": steps})
        self.assertEqual([unit.title for unit in units], [step.title for step in self.plan.steps])
        self.assertEqual(len({unit.unit_id for unit in units}), len(units))
        self.assertEqual(units[0].objective, self.solution.tasks[1].objective)
        self.assertEqual(units[0].activity, self.solution.tasks[1].activity)
        self.assertEqual(units[1].objective, self.solution.tasks[0].objective)
        self.assertEqual(units[1].activity, self.solution.tasks[0].activity)
        self.assertCountEqual(units[0].source_ids, ("p2", "p3"))
        self.assertCountEqual(units[1].source_ids, ("p2", "p3", "p5"))

    @patch("tutor.planning.units.generate_structured")
    def test_cached_plan_can_retry_solve_without_another_decomposition(self, generate):
        generate.side_effect = [self.plan, Solution(tasks=[]), self.solution]
        plan = plan_units(self.outline)
        with self.assertRaises(PlanningError):
            build_study_units(self.outline, plan=plan)
        units = build_study_units(self.outline, plan=plan)
        self.assertEqual(len(schedule_units(units, 5)), 5)
        self.assertEqual(len(schedule_units(units, 10)), 7)
        schemas = [call.kwargs["schema"] for call in generate.call_args_list]
        self.assertEqual(schemas, [UnitPlan, Solution, Solution])

    @patch("tutor.planning.units.generate_structured")
    def test_rejects_missing_invented_or_ambiguous_plan_steps_before_solving(self, generate):
        for steps in (
            [],
            [UnitStep(title="Missing topic", topic_ids=[1, 2])],
            [UnitStep(title="Unknown topic", topic_ids=[1, 2, 3, 4])],
            [UnitStep(title="Duplicate topic", topic_ids=[1, 1, 2, 3])],
            [UnitStep(title="  ", topic_ids=[1, 2, 3])],
            [UnitStep(title="No topic", topic_ids=[]), UnitStep(title="All", topic_ids=[1, 2, 3])],
            [UnitStep(title="Same", topic_ids=[1]), UnitStep(title="Same", topic_ids=[2, 3])],
        ):
            with self.subTest(steps=steps):
                generate.reset_mock()
                generate.return_value = UnitPlan(steps=steps)
                with self.assertRaises(PlanningError):
                    build_study_units(self.outline)
                generate.assert_called_once()

    @patch("tutor.planning.units.generate_structured")
    def test_rejects_missing_duplicate_unknown_and_empty_tasks(self, generate):
        last, first = self.solution.tasks
        for tasks in (
            [first], [first, first], [first, last, last.model_copy(update={"unit_number": 3})],
            [first.model_copy(update={"objective": "  "}), last],
            [first, last.model_copy(update={"activity": ""})],
        ):
            with self.subTest(tasks=tasks):
                generate.return_value = Solution(tasks=tasks)
                with self.assertRaises(PlanningError):
                    build_study_units(self.outline, plan=self.plan)

    @patch("tutor.planning.units.generate_structured")
    def test_empty_outline_has_no_study_days_or_model_calls(self, generate):
        self.assertEqual(schedule_units(build_study_units(Outline(topics=[])), 5), ())
        generate.assert_not_called()


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.units = (
            StudyUnit("unit-1", "Variables", "Trace an assignment.", ("p1", "p2", "p2", "p3"),
                      "Record the values before and after an update."),
            StudyUnit("unit-2", "Loops", "Count iterations.", ("p3", "p4", "p5", "p6", "p7"),
                      "Trace the loop in the reading."),
        )

    def test_shorter_plans_group_whole_units_in_order(self):
        units = tuple(
            StudyUnit(f"unit-{number}", f"Lesson {number}", f"Learn concept {number}.",
                      (f"p{number}",), f"Explain concept {number}.")
            for number in range(1, 6)
        )
        for duration in (1, 2, 5):
            with self.subTest(duration=duration):
                days = schedule_units(units, duration)
                counts = [len(day.assignments) for day in days]
                self.assertEqual(len(days), duration)
                self.assertLessEqual(max(counts) - min(counts), 1)
                assignments = [part for day in days for part in day.assignments]
                self.assertEqual([part.unit for part in assignments], list(units))
                for part in assignments:
                    self.assertEqual(part.kind, "study")
                    self.assertEqual(part.source_ids, part.unit.source_ids)

    def test_longer_plans_split_readings_then_assign_each_units_activity_once(self):
        for duration in (5, 10):
            with self.subTest(duration=duration):
                days = schedule_units(self.units, duration)
                self.assertEqual([day.number for day in days], list(range(1, duration + 1)))
                self.assertTrue(all(len(day.assignments) == 1 for day in days))
                groups = [
                    (unit, list(parts))
                    for unit, parts in groupby((day.assignments[0] for day in days), key=lambda part: part.unit)
                ]
                self.assertEqual([unit for unit, _ in groups], list(self.units))
                for unit, parts in groups:
                    pages = list(dict.fromkeys(unit.source_ids))
                    self.assertEqual(parts[-1].kind, "apply")
                    self.assertEqual(list(parts[-1].source_ids), pages)
                    readings = parts[:-1]
                    self.assertTrue(all(part.kind == "read" and part.source_ids for part in readings))
                    self.assertEqual([page for part in readings for page in part.source_ids], pages)
                    page_counts = [len(part.source_ids) for part in readings]
                    self.assertLessEqual(max(page_counts) - min(page_counts), 1)

    def test_extra_days_add_no_new_assignments_to_the_complete_material(self):
        full = schedule_units(self.units, 10)
        self.assertEqual(schedule_units(self.units, 10_000), full)

    def test_invalid_duration_is_rejected(self):
        for duration in (0, -1, 2.5, True):
            with self.subTest(duration=duration), self.assertRaises((ValueError, TypeError)):
                schedule_units(self.units, duration)
