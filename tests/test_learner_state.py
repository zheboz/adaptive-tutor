import json
import unittest
from unittest.mock import patch

from tutor.agent.intake import NoteMapping, read_self_report
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
        self.state.apply_report(["unit-1"], "x = x + 1 confuses me", ["unit-2"], "while loops")
        summary = self.state.summary()
        self.assertEqual([u["self_reported_unclear"] for u in summary["units"]], [True, True, False])
        self.assertEqual(summary["units"][1]["learner_note"], "x = x + 1 confuses me")
        self.assertIsNone(summary["units"][0]["learner_note"])
        self.assertEqual(summary["topics_missing_from_material"], ["while loops"])
        self.state.apply_report([])
        self.assertFalse(any(u["self_reported_unclear"] for u in self.state.summary()["units"]))
        self.assertEqual(self.state.missing_topics, [])


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.model = self.enterContext(patch("tutor.agent.intake.generate_structured"))

    def test_checked_units_alone_need_no_model_call(self):
        intake = read_self_report(UNITS, ["unit-3", "unit-9", "unit-1"], "   ")
        self.assertEqual(intake.unit_ids, ("unit-1", "unit-3"))
        self.assertIsNone(intake.missing_topic)
        self.model.assert_not_called()

    def test_note_is_matched_to_real_units_only(self):
        self.model.return_value = NoteMapping(unit_ids=["unit-2", "unit-7"], not_in_material=False, missing_topic=None)
        intake = read_self_report(UNITS, ["unit-3"], "I don't get  x = x + 1")
        self.assertEqual((intake.noted_ids, intake.unit_ids), (("unit-2",), ("unit-3", "unit-2")))
        self.assertEqual(intake.note, "I don't get x = x + 1")
        self.assertIsNone(intake.missing_topic)
        payload = json.loads(self.model.call_args.kwargs["content"])
        self.assertEqual([u["unit_id"] for u in payload["units"]], ["unit-1", "unit-2", "unit-3"])
        self.assertEqual(payload["learner_note"], "I don't get x = x + 1")

    def test_topics_outside_the_material_are_reported(self):
        self.model.return_value = NoteMapping(unit_ids=[], not_in_material=True, missing_topic="recursion")
        intake = read_self_report(UNITS, [], "What is recursion?")
        self.assertEqual((intake.noted_ids, intake.missing_topic), ((), "recursion"))
        # Nothing matched and no topic named: the note itself is what is missing.
        self.model.return_value = NoteMapping(unit_ids=["bogus"], not_in_material=False, missing_topic=None)
        self.assertEqual(read_self_report(UNITS, [], "decorators").missing_topic, "decorators")
        # Partly covered: keep the match and the missing part.
        self.model.return_value = NoteMapping(unit_ids=["unit-3"], not_in_material=True, missing_topic="while loops")
        intake = read_self_report(UNITS, [], "for and while loops")
        self.assertEqual((intake.noted_ids, intake.missing_topic), (("unit-3",), "while loops"))
