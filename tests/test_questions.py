import json
import unittest
from unittest.mock import patch

from tutor.assessment.questions import Evidence, PracticeError, QuestionBatch, QuestionDraft, generate_questions
from tutor.assessment.retrieval import Passage
from tutor.planning import StudyAssignment, StudyUnit


class PracticeQuestionTests(unittest.TestCase):
    def setUp(self):
        unit = StudyUnit("unit-1", "Assignment", "Track the new value.", ("p1", "p2"), "Write a trace.")
        self.assignment = StudyAssignment(unit, "read", ("p1",))
        self.fact = "Assigning x = 2 sets the value of x to 2."
        self.exercise = "Question 7. What value does x = 2 assign? A. 1 B. 2 C. 3"
        self.passages = (
            Passage("p1-c1", "p1", self.fact),
            Passage("p8-c2", "p8", self.exercise + "\nAnswer: B."),
            Passage("p9-c1", "p9", "Q7 Answer: B. Q8 Answer: A."),
        )
        self.original = QuestionDraft(
            kind="multiple_choice", prompt="What value does x = 2 assign?",
            options=["1", "2", "3"], correct_index=1, explanation="The assignment stores 2.",
            origin="pdf", grounding=Evidence(passage_id="p1-c1", quote=self.fact),
            exercise=[Evidence(passage_id="p8-c2", quote=self.exercise)],
            answer_key=Evidence(passage_id="p8-c2", quote="Answer: B."),
        )
        self.generated = QuestionDraft(
            kind="true_false", prompt="Assigning x = 2 stores the value 2.", options=["True", "False"],
            correct_index=0, explanation="The assignment sets x to 2.", origin="generated",
            grounding=self.original.grounding, exercise=[], answer_key=None,
        )
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_structured"))

    def batch(self, *drafts):
        self.generate.return_value = QuestionBatch(questions=list(drafts))
        return generate_questions(self.assignment, self.passages)

    def test_original_and_generated_questions_have_verified_provenance(self):
        original, generated = self.batch(self.generated, self.original)
        self.assertEqual(original.origin, "pdf")
        self.assertEqual(original.options, ("1", "2", "3"))
        self.assertEqual(original.source_ids, ("p8", "p1"))
        self.assertEqual(original.answer_origin, "pdf")
        self.assertEqual((generated.kind, generated.answer_origin), ("true_false", "reference"))
        self.assertEqual(generated.source_ids, ("p1",))
        self.generate.assert_called_once()
        payload = json.loads(self.generate.call_args.kwargs["content"])
        self.assertEqual(payload["study_activity"], "")
        self.assertEqual([p["assigned"] for p in payload["passages"]], [True, False, False])

    def test_reference_answer_for_unlinked_key_and_adapted_exercise(self):
        unrelated = self.original.model_copy(update={
            "answer_key": Evidence(passage_id="p9-c1", quote="Q8 Answer: A."),
        })
        adapted = self.generated.model_copy(update={"origin":"adapted", "exercise":self.original.exercise})
        original, converted = self.batch(adapted, unrelated)
        self.assertEqual(original.answer_origin, "reference")
        self.assertNotIn("p9", original.source_ids)
        self.assertEqual((converted.origin, converted.answer_origin), ("adapted", "reference"))

    def test_cross_page_explicit_key_and_conflicting_answer(self):
        key = Evidence(passage_id="p9-c1", quote="Q7 Answer: B.")
        linked = self.original.model_copy(update={"answer_key":key})
        result, = self.batch(linked)
        self.assertEqual(result.answer_origin, "pdf")
        self.assertIn("p9", result.source_ids)
        with self.assertRaisesRegex(PracticeError, "conflicts"):
            self.batch(linked.model_copy(update={"correct_index":0}))

    def test_repair_on_bad_question_then_success(self):
        self.generate.side_effect = [QuestionBatch(questions=[]), QuestionBatch(questions=[self.generated])]
        questions = generate_questions(self.assignment, self.passages)
        self.assertEqual(len(questions), 1)
        self.assertEqual(self.generate.call_count, 2)
        self.assertIn("correction", json.loads(self.generate.call_args.kwargs["content"]))

    def test_original_claim_requires_full_printed_question(self):
        for change in (
            {"prompt":"Which value is stored?"}, {"options":["1", "2"]},
            {"options":["1", "2", "13"]}, {"exercise":[]},
            {"options":["1", "2"], "exercise":[
                Evidence(passage_id="p8-c2", quote=self.exercise.rsplit(" C.", 1)[0]),
            ]},
        ):
            with self.subTest(change=change), self.assertRaises(PracticeError):
                self.batch(self.original.model_copy(update=change))

    def test_bounded_validation_for_counts_choices_and_quotes(self):
        invalid = (
            [], [self.generated] * 6, [self.generated] * 2,
            [self.generated.model_copy(update={"options":["yes", "almost"]})],
            [self.generated.model_copy(update={"correct_index":2})],
            [self.original.model_copy(update={"options":["x", "X"]})],
            [self.generated.model_copy(update={"explanation":" "})],
            [self.generated.model_copy(update={"grounding":Evidence(passage_id="absent", quote=self.fact)})],
            [self.generated.model_copy(update={"grounding":Evidence(passage_id="p1-c1", quote="invented")})],
            [self.generated.model_copy(update={"grounding":self.original.exercise[0]})],
        )
        for drafts in invalid:
            with self.subTest(drafts=drafts):
                self.generate.reset_mock()
                with self.assertRaises(PracticeError):
                    self.batch(*drafts)
                self.assertEqual(self.generate.call_count, 2)

    def test_no_assigned_evidence_returns_without_a_request(self):
        with self.assertRaises(PracticeError):
            generate_questions(self.assignment, self.passages[1:])
        self.generate.assert_not_called()

    def test_chinese_true_false_original(self):
        text = "判断题：两次更新后，计数器为 2。"
        evidence = Evidence(passage_id="p1-c1", quote=text)
        self.generate.return_value = QuestionBatch(questions=[QuestionDraft(
            kind="true_false", prompt="两次更新后，计数器为 2。", options=["正确", "错误"],
            correct_index=0, explanation="计数器从零开始，每次加一。", origin="pdf",
            grounding=evidence, exercise=[evidence], answer_key=None,
        )])
        result, = generate_questions(self.assignment, [Passage("p1-c1", "p1", text)])
        self.assertEqual((result.origin, result.options, result.answer_origin), ("pdf", ("正确", "错误"), "reference"))
