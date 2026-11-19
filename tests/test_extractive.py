import unittest

from tutor.assessment.concepts import Concept
from tutor.assessment.extractive import build_reading_check
from tutor.assessment.retrieval import Passage
from tutor.planning import StudyAssignment, StudyUnit


def reading(title="Counter increments", objective="Trace counter updates."):
    unit = StudyUnit("u1", title, objective, ("p1", "p2"), "Calculate the following stage.")
    return StudyAssignment(unit, "read", ("p1",))


class ReadingCheckTests(unittest.TestCase):
    def test_numeric_cloze_is_a_verbatim_sentence_with_one_blank_and_same_page_options(self):
        text = "Set counter = 2.\nPerform counter = counter + 1.\nThe new counter value is 3."
        result = build_reading_check(reading(), [Passage("p1-c1", "p1", text)])
        self.assertEqual(result.kind, "multiple_choice")
        self.assertEqual(result.prompt, "The new counter value is ____.")
        self.assertEqual(result.options[result.correct_index], "3")
        self.assertEqual(set(result.options), {"1", "2", "3"})
        self.assertEqual(result.explanation, result.prompt.replace("____", "3"))
        self.assertEqual((result.source_ids, result.origin, result.answer_origin), (("p1",), "generated", "reading"))

    def test_statements_without_a_number_get_no_always_true_check(self):
        # A verbatim true/false restatement would always be "True", so it is not offered.
        for title, objective, text in (
            ("变量", "变量可以保存数值。", "变量可以保存一个数值。"),
            ("Memory", "Explain persistent memory.", "What is memory?\n• Long-term memory stores preferences across sessions"),
            ("Counter increments", "Trace counter updates.", "The counter value is 1.\nThe counter value is 1.0."),
        ):
            with self.subTest(text=text):
                self.assertIsNone(build_reading_check(reading(title, objective), [Passage("p1-c1", "p1", text)]))

    def test_excludes_unassigned_nonteaching_and_unrelated_passages(self):
        for text in ("Counter increments\n2\n4", "x = 2\nx = x + 1", "Counter value is 5.\nAnswer: False",
                     "Question 2. The counter value is 5.", "A) The counter value is 5.",
                     "A planet is made of gas.", "练习：计数器是 3。"):
            with self.subTest(text=text):
                passages = [Passage("p1-c1", "p1", text), Passage("p2-c1", "p2", "The counter value is 5.")]
                self.assertIsNone(build_reading_check(reading(), passages))

    def test_preselected_concepts_must_exist_on_assigned_pages(self):
        text = "Set counter = 4.\nThe counter value is 5."
        fact = "The counter value is 5."
        passages = [Passage("p1-c1", "p1", text), Passage("p2-c1", "p2", text)]
        valid = Concept(id="c1", passage_id="p1-c1", source_id="p1", text=fact)
        self.assertEqual(build_reading_check(reading(), passages, concepts=[valid]).concept_id, "c1")
        for candidates in ([], [Concept(id="c1", passage_id="p2-c1", source_id="p2", text=fact)],
                           [Concept(id="c1", passage_id="p1-c1", source_id="p1", text="An invented value of 7.")]):
            with self.subTest(candidates=candidates):
                self.assertIsNone(build_reading_check(reading(), passages, concepts=candidates))
