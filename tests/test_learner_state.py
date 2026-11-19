import unittest

from tutor.agent.state import LearnerState
from tutor.planning import StudyUnit


UNITS = (
    StudyUnit("unit-1", "Assignment", "Store a value in a variable.", ("p1",), "Trace x."),
    StudyUnit("unit-2", "Variable updates", "Explain x = x + 1.", ("p2",), "Update a counter."),
    StudyUnit("unit-3", "Loop counts", "Count loop iterations.", ("p3",), "Trace a loop."),
)


class StatusRuleTests(unittest.TestCase):
    def setUp(self):
        self.state = LearnerState(UNITS)

    def answer(self, unit_id, *results, kind="multiple_choice"):
        for correct in results:
            n = len(self.state.answers()) + 1
            self.state.record(f"q{n}", unit_id, kind, correct, "diagnosis")

    def test_report_alone_is_only_a_suspicion(self):
        self.assertEqual(self.state.status("unit-2"), "untested")
        self.state.apply_report(["unit-2"])
        self.assertEqual(self.state.status("unit-2"), "suspected")

    def test_one_answer_is_never_conclusive(self):
        self.answer("unit-1", False)
        self.answer("unit-2", True)
        self.assertEqual((self.state.status("unit-1"), self.state.status("unit-2")), ("uncertain", "uncertain"))

    def test_mastery_needs_two_correct_multiple_choice_answers(self):
        self.answer("unit-1", True, True)
        self.assertEqual(self.state.status("unit-1"), "mastered")
        self.answer("unit-2", True, True, kind="true_false")
        self.assertEqual(self.state.status("unit-2"), "uncertain")

    def test_gap_needs_repeated_wrong_answers_that_outnumber_correct_ones(self):
        self.answer("unit-2", False, False)
        self.assertEqual(self.state.status("unit-2"), "gap")
        self.answer("unit-3", False, True)
        self.assertEqual(self.state.status("unit-3"), "uncertain")
        self.answer("unit-3", False)
        self.assertEqual(self.state.status("unit-3"), "gap")
        self.answer("unit-1", False, False, True, True)
        self.assertEqual(self.state.status("unit-1"), "uncertain")

    def test_record_is_idempotent_and_rejects_unknown_units(self):
        first = self.state.record("q1", "unit-1", "multiple_choice", True, "practice")
        again = self.state.record("q1", "unit-1", "multiple_choice", False, "practice")
        self.assertIs(first, again)
        self.assertEqual(len(self.state.answers()), 1)
        with self.assertRaises(ValueError):
            self.state.record("q2", "unit-9", "multiple_choice", True, "practice")

    def test_a_new_report_replaces_the_old_one(self):
        self.state.apply_report(["unit-1", "unit-2"])
        summary = self.state.summary()
        self.assertEqual([u["marked_weak_by_learner"] for u in summary["units"]], [True, True, False])
        self.state.apply_report(["unit-3", "unit-9"])
        self.assertEqual([u["marked_weak_by_learner"] for u in self.state.summary()["units"]], [False, False, True])
        self.state.apply_report([])
        self.assertFalse(any(u["marked_weak_by_learner"] for u in self.state.summary()["units"]))
