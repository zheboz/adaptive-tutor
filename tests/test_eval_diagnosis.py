import json
from pathlib import Path
import unittest
from unittest.mock import patch

from eval import diagnosis
from eval.diagnosis import Conclusion, grade, run_baseline


TASKS = [json.loads(line) for line in (Path(__file__).parent.parent / "tasks.jsonl").read_text().splitlines()
         if '"diagnosis"' in line]


class DiagnosisTaskTests(unittest.TestCase):
    def test_every_task_answers_every_question_it_can_be_asked(self):
        self.assertEqual(len(TASKS), 10)
        for task in TASKS:
            for unit_id in task["today"]:
                wanted = task.get("available", {}).get(unit_id, len(diagnosis.QUESTIONS[unit_id]))
                self.assertEqual(len(task["answers"][unit_id]), wanted, task["id"])

    def test_baseline_asks_two_fixed_questions_per_unit_then_concludes_once(self):
        task = next(t for t in TASKS if t["id"] == "d02")
        conclusion = Conclusion(primary_gap="unit-3", status="confirmed", evidence=["unit-3:q1", "unit-3:q2"],
                                next_step="review_today", summary="Unit 3 needs review.")
        with patch("eval.diagnosis.generate_structured", return_value=conclusion) as model:
            result, _, questions = run_baseline(task)
        model.assert_called_once()
        self.assertEqual(questions, 4)
        self.assertEqual(grade(task, result), (True, "primary_gap=unit-3, status=confirmed, next_step=review_today"))

    def test_a_rejected_baseline_conclusion_fails(self):
        # d05 needs a third question on unit-3; after two answers (one right) a confirmed gap is rejected.
        task = next(t for t in TASKS if t["id"] == "d05")
        conclusion = Conclusion(primary_gap="unit-3", status="confirmed", evidence=["unit-3:q2"],
                                next_step="review_today", summary="Unit 3 needs review.")
        with patch("eval.diagnosis.generate_structured", return_value=conclusion):
            result, _, _ = run_baseline(task)
        self.assertTrue(result.forced)
        self.assertFalse(grade(task, result)[0])


if __name__ == "__main__":
    unittest.main()
