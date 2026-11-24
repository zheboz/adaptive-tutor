import unittest

from eval.run_eval import report


def row(system, run, task_id, passed, document="week_2.pdf", category="direct"):
    return {"system": system, "run": run, "id": task_id, "category": category, "passed": passed, "reason": "r",
            "turns": 1, "latency": 1.0, "tokens": 100, "questions": 0, "document": document}


class RunEvalReportTests(unittest.TestCase):
    def test_both_systems_get_pass_k_and_each_document_its_accuracy(self):
        tasks = [{"id": "t01", "category": "direct"}, {"id": "t51", "category": "direct"}]
        rows = [
            # t01 on Week 2: the baseline flips, the agent always passes.
            *(row("baseline", n, "t01", passed) for n, passed in ((1, True), (2, False), (3, True))),
            *(row("agent", n, "t01", True) for n in (1, 2, 3)),
            # t51 on Week 3: the baseline always fails, the agent passes twice.
            *(row("baseline", n, "t51", False, "week_3.pdf") for n in (1, 2, 3)),
            *(row("agent", n, "t51", passed, "week_3.pdf") for n, passed in ((1, True), (2, True), (3, False))),
        ]
        text = report(rows, tasks, 3, "gpt-test", 3)
        self.assertIn("agent runs: 3 · baseline runs: 3", text)
        self.assertIn("| Baseline (one-shot RAG), run 2 | 0% |", text)
        self.assertIn("| Baseline (one-shot RAG), all 3 runs | 33% |", text)
        self.assertIn("| Baseline | 50% | 0% | t01 (✓✗✓) |", text)
        self.assertIn("| Agent | 100% | 50% | t51 (✓✓✗) |", text)
        self.assertIn("| week_2.pdf | 1 | 67% | 100% |", text)
        self.assertIn("| week_3.pdf | 1 | 0% | 67% |", text)

    def test_a_single_baseline_run_has_no_pass_k_row(self):
        tasks = [{"id": "t01", "category": "direct"}]
        rows = [row("baseline", 1, "t01", True), *(row("agent", n, "t01", True) for n in (1, 2, 3))]
        text = report(rows, tasks, 3, "gpt-test", 1)
        self.assertIn("| Baseline (one-shot RAG) | 100% |", text)
        self.assertNotIn("| Baseline | 100%", text)
        self.assertIn("k = 3 for the agent; the baseline ran once.", text)
        # One document only: no per-document table.
        self.assertNotIn("| Document |", text)
