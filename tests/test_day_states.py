from types import SimpleNamespace as Day
import unittest

from tutor.ui.views import day_states, day_strip_html, plan_html


def day(number, *kinds):
    return Day(number=number, assignments=tuple(
        Day(kind=kind, unit=Day(title=f"Unit {number}"), source_ids=("p1",)) for kind in kinds))


class DayStateTests(unittest.TestCase):
    def setUp(self):
        self.days = [day(1, "study"), day(2, "study"), day(3, "study"), day(4, "review")]

    def test_each_day_is_checked_next_still_to_come_a_review_or_optional(self):
        self.assertEqual(day_states(self.days, {1}, 5), ["checked", "next", "todo", "review", "optional"])
        # A checked review is checked; the first day not checked is next even after a gap.
        self.assertEqual(day_states(self.days, {1, 3, 4}, 4), ["checked", "next", "checked", "checked"])

    def test_the_tabs_are_colored_by_position_and_the_colors_explained(self):
        html = day_strip_html(day_states(self.days, {1}, 4))
        self.assertIn("button:nth-child(1) { background: #EAF6EF", html)
        self.assertIn("button:nth-child(4) { background: #FFF1E3", html)
        self.assertNotIn("nth-child(3)", html)
        self.assertIn("Checked", html)
        self.assertIn("Review", html)

    def test_the_plan_timeline_marks_reviews_still_to_do(self):
        html = plan_html(self.days, 4, {1}, 2)
        self.assertIn('<li class="plan-day review" data-day="4">', html)
        self.assertIn('<li class="plan-day next" data-day="2">', html)


if __name__ == "__main__":
    unittest.main()
