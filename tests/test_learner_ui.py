import re
import unittest
from unittest.mock import patch

from tests.ui_helpers import UITestCase, begin, create_plan, show_page, visible_text
from tutor.agent.state import LearnerState
from tutor.materials.outline import Outline, Topic
from tutor.planning import StudyUnit
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask
from tutor.ui.learner import chapter_percent, chapter_progress, chapter_progress_html


def answer(state, unit_id, *results):
    for number, correct in enumerate(results, start=1):
        state.record(f"{unit_id}-q{number}", unit_id, "multiple_choice", correct, "diagnosis")


class ChapterProgressTests(unittest.TestCase):
    def test_units_are_counted_by_how_they_stand(self):
        units = [StudyUnit(f"unit-{n}", f"Unit {n}", "Learn.", (f"p{n}",), "Do.", (n,)) for n in range(1, 6)]
        state = LearnerState(units)
        answer(state, "unit-1", True, True)            # understood
        answer(state, "unit-2", True)                  # one answer: needs more evidence
        answer(state, "unit-3", False, False, True)    # likely gap
        state.apply_report(["unit-4"])                 # marked weak, not checked: not checked yet
        counts = chapter_progress(state)
        self.assertEqual(counts, {"understood": 1, "uncertain": 1, "gap": 1, "untested": 2})

        # Understood counts fully, needs more evidence half: (1 + 0.5) of 5 units.
        self.assertEqual(chapter_percent(counts), 30)
        html = chapter_progress_html(counts, 2, 6)
        self.assertIn('<p class="chapter-percent"><span>30%</span> of the chapter learned</p>', html)
        self.assertIn('aria-valuemax="100" aria-valuenow="30"', html)
        self.assertIn('class="chapter-bar-part understood" style="width: 20.0000%"', html)
        self.assertIn('class="chapter-bar-part untested" style="width: 40.0000%"', html)
        self.assertIn("1 of 5 units understood · 2 of 6 days checked", html)

    def test_the_percentage_weighs_each_unit_by_how_it_stands(self):
        def percent(understood=0, uncertain=0, gap=0, untested=0):
            return chapter_percent({"understood": understood, "uncertain": uncertain, "gap": gap,
                                    "untested": untested})
        self.assertEqual(percent(understood=4), 100)
        self.assertEqual(percent(uncertain=4), 50)
        self.assertEqual(percent(gap=3, untested=1), 0)
        self.assertEqual(percent(understood=1, uncertain=1, gap=1), 50)
        self.assertEqual(percent(), 0)

    def test_an_empty_or_untouched_chapter_shows_no_filled_part(self):
        html = chapter_progress_html({"understood": 0, "uncertain": 0, "gap": 0, "untested": 3}, 0, 4)
        self.assertIn("<span>0%</span>", html)
        self.assertNotIn("chapter-bar-part understood", html)
        self.assertIn("0 of 3 units understood · 0 of 4 days checked", html)
        html = chapter_progress_html({"understood": 0, "uncertain": 0, "gap": 0, "untested": 0}, 0, 1)
        self.assertIn("<span>0%</span>", html)
        self.assertNotIn("chapter-bar-part", html)


class LearnerUITests(UITestCase):
    def setUp(self):
        super().setUp()
        topics = [
            Topic(title="Assignment", summary="Store a value.", source_ids=["p1"]),
            Topic(title="Iteration", summary="Repeat a block.", source_ids=["p2"]),
            Topic(title="Loop counts", summary="Count iterations.", source_ids=["p3"]),
        ]
        outline = self.enterContext(patch("tutor.materials.outline.generate_outline"))
        outline.return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain it.")
                            for n, t in enumerate(topics, 1)]),
        ]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions"))
        self.app = self.new_app()
        begin(self.app, "Assignment: x = 2.", "Iteration: loop twice.", "Counting: range(3).")

    def status_text(self):
        show_page(self.app, "Progress")
        html = visible_text(self.app.main.container("learning_status_panel"))
        return re.sub(r"\s*<br>\s*", "\n", re.sub(r"</?(?:p|strong|small)>", "", html))

    def plan(self, days, *weak):
        for index in weak:
            self.app.checkbox(key=f"weak_topic_{index}").check()
        create_plan(self.app, days)
        self.assertFalse(self.app.exception)

    def plan_text(self):
        show_page(self.app, "Plan")
        return visible_text(self.app.main.container("plan_overview_panel"))

    def test_weak_topics_on_the_outline_get_more_time(self):
        self.assertEqual(len(self.app.main.container("outline_panel").checkbox), 3)
        self.plan(2, 1)
        self.assertIn("More time for: Iteration", self.plan_text())
        self.assertIn("Iteration · Marked weak · not checked yet", self.status_text())
        self.assertIn("Assignment · Not checked yet", self.status_text())
        self.assertFalse(self.app.text_area)
        # A long plan gives the weak unit a review day.
        self.plan(6)
        kinds = [(a.unit.title, a.kind) for day in self.app.session_state["study_plan"] for a in day.assignments]
        self.assertIn(("Iteration", "review"), kinds)
        self.assertNotIn(("Assignment", "review"), kinds)

    def test_progress_opens_with_the_chapter_bar(self):
        self.plan(3, 1)
        show_page(self.app, "Progress")
        panel = self.app.main.container("progress_panel")
        chapter = next(h.value for h in panel.html if "chapter-progress" in h.value)
        self.assertIn("<span>0%</span> of the chapter learned", chapter)
        self.assertIn("0 of 3 units understood · 0 of 3 days checked", chapter)
        # The bar comes before each unit's status.
        texts = [h.value for h in panel.html]
        self.assertLess(texts.index(chapter), next(i for i, t in enumerate(texts) if "Iteration" in t))

    def test_checked_topics_take_effect_when_the_plan_is_created(self):
        self.plan(3, 0, 2)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-3"))
        self.assertIn("Loop counts · Marked weak · not checked yet", self.status_text())
        # The outline is under Change the plan now; its checks keep what was checked before.
        show_page(self.app, "Plan")
        self.assertTrue(self.app.checkbox(key="weak_topic_0").value)
        # Unchecking alone changes nothing until the plan is created again.
        self.app.checkbox(key="weak_topic_0").uncheck().run()
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-1", "unit-3"))
        self.plan(3)
        self.assertEqual(self.app.session_state["planned_weak"], ("unit-3",))
        self.assertIn("Assignment · Not checked yet", self.status_text())
        self.assertNotIn("More time for: Assignment", self.plan_text())
