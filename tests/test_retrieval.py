import unittest

from tutor.assessment.retrieval import build_index, retrieve
from tutor.materials.ingest import PdfPage
from tutor.planning.scheduler import StudyAssignment
from tutor.planning.units import StudyUnit


def reading(source_ids=("p1",), title="Accumulation", objective="Trace a running total."):
    unit = StudyUnit("unit-1", title, objective, source_ids, "Solve the final recurrence.")
    return StudyAssignment(unit, "read", source_ids)


class RetrievalTests(unittest.TestCase):
    def test_finds_original_exercise_and_its_options_on_the_next_page(self):
        index = build_index([
            PdfPage(1, "For accumulation, a counter records the running total."),
            PdfPage(2, "Exercise: Which planets have rings?"),
            PdfPage(3, "Photosynthesis uses sunlight."),
            PdfPage(4, "Review questions\nWhat does the counter record?"),
            PdfPage(5, "A) The running total\nB) The array length"),
        ])
        result = retrieve(index, reading())
        self.assertEqual([p.source_id for p in result], ["p1", "p4", "p5"])
        self.assertEqual(result[1].text, index.passages[3].text)
        self.assertEqual(len({p.id for p in result}), len(result))

    def test_finds_chinese_exercise_with_terms_from_the_assigned_reading(self):
        index = build_index([
            PdfPage(1, "Python变量可以保存数值，赋值语句更新变量。"),
            PdfPage(2, "章节练习：以下哪条赋值语句会更新变量？"),
            PdfPage(3, "章节练习：下列哪个城市盛产苹果？"),
        ])
        result = retrieve(index, reading(title="阅读", objective="指出本节要点。"))
        self.assertEqual([p.source_id for p in result], ["p1", "p2"])

    def test_reading_day_excludes_later_unit_material_and_unreadable_pages(self):
        index = build_index([
            PdfPage(1, "Initialize the counter to zero."),
            PdfPage(2, "Exercise: Find the recurrence after the last iteration."),
            PdfPage(3, "Which counter starts at zero?"),
            PdfPage(4, ""), PdfPage(5, "Counter question?", "Unreadable page"),
        ])
        unit = StudyUnit("unit", "Counters and recurrence", "Trace later iterations.",
                         ("p1", "p2"), "Find the last recurrence.")
        result = retrieve(index, StudyAssignment(unit, "read", ("p1",)))
        self.assertEqual([p.source_id for p in result], ["p1", "p3"])
        self.assertEqual(retrieve(index, StudyAssignment(unit, "read", ("p4", "p5"))), ())
        self.assertEqual(retrieve(build_index([]), reading()), ())

    def test_bounds_evidence_and_retrieves_an_exercise_late_in_a_long_page(self):
        background = "Set a counter to zero and add the current value.\n" * 80
        original = "Question: Is the running total equal to the counter after each addition?"
        pages = [PdfPage(1, background * 8 + original)]
        pages.extend(PdfPage(i, f"Exercise {i}: What is the running total?") for i in range(2, 30))
        index = build_index(pages)
        result = retrieve(index, reading())
        self.assertTrue(any(original in p.text and p.source_id == "p1" for p in result))
        self.assertTrue(any(p.source_id != "p1" for p in result))
        self.assertLessEqual(len(result), 10)
        self.assertLessEqual(sum(len(p.text) for p in result), 16000)
        for passage in index.passages:
            self.assertLessEqual(len(passage.text), 1600)
            self.assertIn(passage.text, pages[int(passage.source_id[1:]) - 1].text)

    def test_repeating_queries_reuse_index_and_preserve_order(self):
        pages = [PdfPage(1, "Increment a counter."), PdfPage(2, "Add to a running total.")]
        index = build_index(pages)
        assignment = reading(source_ids=("p1", "p2"))
        first = retrieve(index, assignment)
        self.assertEqual(first, retrieve(index, assignment))
        self.assertEqual({p.id for p in first}, {"p1-c1", "p2-c1"})
