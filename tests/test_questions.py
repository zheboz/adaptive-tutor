import json
import unittest
from unittest.mock import patch

from tutor.assessment.concepts import find_concepts
from tutor.assessment.questions import (
    Evidence, InsufficientEvidence, PracticeError, QuestionBatch, QuestionDraft, _model_questions, generate_questions,
)
from tutor.assessment.retrieval import Passage
from tutor.llm import LLMError
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
        concept, = find_concepts(self.assignment, self.passages[:1])
        self.concept_id = concept.id
        self.original = QuestionDraft(
            kind="multiple_choice", prompt="What value does x = 2 assign?",
            options=["1", "2", "3"], correct_index=1, explanation="The assignment stores 2.",
            origin="pdf", concept_id=self.concept_id,
            exercise=[Evidence(passage_id="p8-c2", quote=self.exercise)],
            answer_key=Evidence(passage_id="p8-c2", quote="Answer: B."),
        )
        self.generated = QuestionDraft(
            kind="true_false", prompt="Assigning x = 2 stores the value 2.", options=["True", "False"],
            correct_index=0, explanation="The assignment sets x to 2.", origin="generated",
            concept_id=self.concept_id, exercise=[], answer_key=None,
        )
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_structured"))

    def batch(self, *drafts, generate=generate_questions):
        self.generate.return_value = QuestionBatch(questions=list(drafts))
        return generate(self.assignment, self.passages)

    def test_original_and_generated_questions_have_verified_provenance(self):
        original, generated = self.batch(self.generated, self.original)
        self.assertEqual(original.origin, "pdf")
        self.assertEqual(original.options, ("1", "2", "3"))
        self.assertEqual(original.source_ids, ("p8", "p1"))
        self.assertEqual(original.answer_origin, "pdf")
        self.assertEqual((generated.kind, generated.answer_origin), ("true_false", "reference"))
        self.assertEqual(generated.source_ids, ("p1",))
        self.assertEqual((original.concept_id, generated.concept_id), (self.concept_id, self.concept_id))
        self.generate.assert_called_once()
        payload = json.loads(self.generate.call_args.kwargs["content"])
        self.assertEqual(payload["study_activity"], "")
        self.assertEqual(payload["learning_points"], [{"id": self.concept_id, "fact": self.fact}])
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
            self.batch(linked.model_copy(update={"correct_index":0}), generate=_model_questions)

    def test_repair_on_bad_question_then_success(self):
        self.generate.side_effect = [QuestionBatch(questions=[]), QuestionBatch(questions=[self.generated])]
        questions = generate_questions(self.assignment, self.passages)
        self.assertEqual(len(questions), 1)
        self.assertEqual(self.generate.call_count, 2)
        self.assertIn("correction", json.loads(self.generate.call_args.kwargs["content"]))

    def test_original_claim_requires_full_printed_question(self):
        for change in (
            {"prompt":"Which value is stored?", "answer_key":None}, {"options":["1", "2"]},
            {"options":["1", "2", "13"]}, {"exercise":[]},
            {"options":["1", "2"], "exercise":[
                Evidence(passage_id="p8-c2", quote=self.exercise.rsplit(" C.", 1)[0]),
            ]},
        ):
            with self.subTest(change=change), self.assertRaises(PracticeError):
                self.batch(self.original.model_copy(update=change), generate=_model_questions)

    def test_bounded_validation_for_counts_choices_and_quotes(self):
        invalid = (
            [], [self.generated] * 6,
            [self.generated.model_copy(update={"options":["yes", "almost"]})],
            [self.generated.model_copy(update={"correct_index":2})],
            [self.original.model_copy(update={"options":["x", "X"]})],
            [self.generated.model_copy(update={"explanation":" "})],
            [self.generated.model_copy(update={"concept_id":"p1-invented"})],
            [self.generated.model_copy(update={"concept_id":None})],
            [self.original.model_copy(update={"concept_id":None})],
        )
        for drafts in invalid:
            with self.subTest(drafts=drafts):
                self.generate.reset_mock()
                with self.assertRaises(PracticeError):
                    self.batch(*drafts, generate=_model_questions)
                self.assertEqual(self.generate.call_count, 2)

    def test_restores_the_printed_stem_for_a_paraphrase_with_verified_key(self):
        paraphrased = self.original.model_copy(update={"prompt": "What number is stored in x after assignment?"})
        result, = self.batch(paraphrased)
        self.assertEqual(result.prompt, self.original.prompt)
        self.assertEqual((result.origin, result.answer_origin, result.correct_index), ("pdf", "pdf", 1))
        self.assertEqual(result.explanation, self.fact)
        self.generate.assert_called_once()

    def test_retains_verified_items_after_repeated_bad_sibling_or_failed_repair(self):
        bad = self.original.model_copy(update={"options": ["1", "2", "13"]})
        for retry in (QuestionBatch(questions=[bad]), LLMError("Request failed.")):
            with self.subTest(retry=retry):
                self.generate.side_effect = [QuestionBatch(questions=[bad, self.generated]), retry]
                result, = generate_questions(self.assignment, self.passages)
                self.assertEqual(result.prompt, self.generated.prompt)

    def test_duplicate_valid_questions_are_shown_once(self):
        result, = self.batch(self.generated, self.generated)
        self.assertEqual(result.prompt, self.generated.prompt)

    def test_repair_separates_assigned_reading_from_supplemental_exercises(self):
        # Without a learning point, an exercise printed on another page cannot ground the question.
        wrong_page = self.original.model_copy(update={"concept_id": None})
        self.generate.side_effect = [QuestionBatch(questions=[wrong_page]), QuestionBatch(questions=[self.original])]
        result, = generate_questions(self.assignment, self.passages)
        repair = json.loads(self.generate.call_args.kwargs["content"])
        self.assertEqual(repair["rejected_items"][0]["prompt"], wrong_page.prompt)
        self.assertEqual([p["id"] for p in repair["assigned_reading_for_grounding"]], ["p1-c1"])
        self.assertEqual([p["id"] for p in repair["supplemental_exercises_and_keys_only"]], ["p8-c2", "p9-c1"])
        self.assertEqual(result.source_ids, ("p8", "p1"))

    def test_failed_drafts_fall_back_to_a_relevant_printed_answer_on_the_assigned_page(self):
        page = Passage("p1-c1", "p1", self.exercise + "\nAnswer: B.\nQ8. True or false: Mars is cold.\nAnswer: True")
        self.generate.return_value = QuestionBatch(questions=[])
        result, = generate_questions(self.assignment, [page])
        self.assertEqual((result.prompt, result.options), (self.original.prompt, ("1", "2", "3")))
        self.assertEqual((result.correct_index, result.source_ids, result.answer_origin), (1, ("p1",), "pdf"))
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
            concept_id=None, exercise=[evidence], answer_key=None,
        )])
        result, = generate_questions(self.assignment, [Passage("p1-c1", "p1", text)])
        self.assertEqual((result.origin, result.options, result.answer_origin), ("pdf", ("正确", "错误"), "reference"))
        self.assertEqual((result.source_ids, result.concept_id), (("p1",), None))
        payload = json.loads(self.generate.call_args.kwargs["content"])
        self.assertEqual(payload["learning_points"], [])

    def test_learning_points_come_from_the_full_assigned_reading(self):
        # Retrieval may return only exercises; the lesson on today's page still grounds the question.
        self.generate.return_value = QuestionBatch(questions=[self.generated])
        result, = generate_questions(self.assignment, self.passages[1:], assigned_reading=self.passages[:1])
        self.assertEqual((result.source_ids, result.concept_id), (("p1",), self.concept_id))
        payload = json.loads(self.generate.call_args.kwargs["content"])
        self.assertEqual([p["id"] for p in payload["passages"]], ["p1-c1", "p8-c2", "p9-c1"])

    def test_reading_without_a_point_or_exercise_is_insufficient_without_a_request(self):
        headings = [Passage("p1-c1", "p1", "Variables\nAssignment")]
        with self.assertRaises(InsufficientEvidence):
            generate_questions(self.assignment, headings)
        self.generate.assert_not_called()

    def test_model_can_decline_practice_for_pages_with_nothing_to_teach(self):
        agenda = Passage("p1-c1", "p1", "Agenda\n1. Recap\n2. Assignment x = 2 sets the value of x to 2.\nQuestions?")
        self.generate.return_value = QuestionBatch(questions=[], no_practice_reason="The page only lists topics.")
        with self.assertRaisesRegex(InsufficientEvidence, "only lists topics"):
            generate_questions(self.assignment, [agenda])
        # No repair request and no fallback question built from the page's text.
        self.generate.assert_called_once()
        payload = json.loads(self.generate.call_args.kwargs["content"])
        self.assertNotIn("correction", payload)

    def test_an_empty_batch_without_a_reason_is_still_repaired(self):
        self.generate.side_effect = [QuestionBatch(questions=[], no_practice_reason=" "),
                                     QuestionBatch(questions=[self.generated])]
        result, = generate_questions(self.assignment, self.passages)
        self.assertEqual(result.prompt, self.generated.prompt)
        self.assertEqual(self.generate.call_count, 2)
