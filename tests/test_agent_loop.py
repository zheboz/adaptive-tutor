import json
import unittest
from unittest.mock import patch

from tutor.agent.bank import DiagnosticQuestion, QuestionBank
from tutor.agent.loop import Ask, Done, advance, max_model_calls, start_session
from tutor.agent.state import LearnerState
from tutor.agent.tools import MAX_QUESTIONS, tool_schemas, validate_finish
from tutor.assessment.questions import PracticeError, Question
from tutor.llm import LLMError, ToolCall, ToolTurn
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyUnit


UNITS = (
    StudyUnit("unit-1", "Assignment", "Store a value in a variable.", ("p1",), "Trace x."),
    StudyUnit("unit-2", "Variable updates", "Explain x = x + 1.", ("p2",), "Update a counter."),
    StudyUnit("unit-3", "Loop counts", "Count loop iterations.", ("p3",), "Trace a loop."),
)


def question(prompt, kind="multiple_choice"):
    options = ("True", "False") if kind == "true_false" else ("2", "3", "4")
    return Question(kind, prompt, options, 0, "From the reading.", "generated", ("p1",), "reference")


class FakeBank:
    def __init__(self, per_unit=3, broken=()):
        self.problems = {}
        self.questions = {
            unit.unit_id: [DiagnosticQuestion(f"{unit.unit_id}:q{n}", unit.unit_id, question(f"{unit.title} {n}?"))
                           for n in range(1, per_unit + 1)]
            for unit in UNITS
        }
        self.broken = set(broken)

    def pick(self, unit_id, exclude):
        if unit_id in self.broken:
            raise LLMError("Could not reach OpenAI.")
        return next((q for q in self.questions[unit_id] if q.id not in exclude), None)

    def remaining(self, unit_id, exclude):
        return sum(q.id not in exclude for q in self.questions[unit_id])


def turn(name, n, **arguments):
    call_id = f"call-{n}"
    return ToolTurn(
        (ToolCall(call_id, name, arguments),),
        ({"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)},),
    )


class ScriptedModel:
    """Replays tool calls and keeps a copy of the conversation the model saw each time."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen = []

    def __call__(self, *, instructions, items, tools, **_):
        self.seen.append(json.loads(json.dumps(items)))
        if not self.turns:
            raise AssertionError("The model was called more often than scripted.")
        step = self.turns.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def outputs(self):
        return [json.loads(item["output"]) for item in self.seen[-1] if item.get("type") == "function_call_output"]


def paired(items):
    calls = [item["call_id"] for item in items if item.get("type") == "function_call"]
    outputs = [item["call_id"] for item in items if item.get("type") == "function_call_output"]
    return sorted(calls) == sorted(outputs)


class DiagnosisLoopTests(unittest.TestCase):
    def setUp(self):
        self.state = LearnerState(UNITS)
        self.bank = FakeBank()
        self.session = start_session(UNITS, self.state, self.bank)

    def script(self, *turns):
        model = ScriptedModel(*turns)
        self.enterContext(patch("tutor.agent.loop.call_with_tools", side_effect=model))
        return model

    def test_first_question_can_use_current_evidence_without_a_lookup(self):
        self.state.apply_report(["unit-3"])
        self.state.record("unit-1:q1", "unit-1", "multiple_choice", True, "quiz")
        model = self.script(turn("ask_question", 1, unit_id="unit-3", reason="The learner reported loops."))

        self.assertIsInstance(advance(self.session), Ask)
        self.assertEqual(len(model.seen), 1)
        state = json.loads(model.seen[0][0]["content"])["learner_state"]
        self.assertEqual((state["questions_asked"], state["questions_left"]), (0, MAX_QUESTIONS))
        self.assertEqual(state["units"][0]["answers"][0]["question_id"], "unit-1:q1")
        self.assertEqual(state["units"][0]["unused_questions"], 2)
        self.assertEqual(state["units"][2]["status"], "suspected")

    def test_follows_a_reported_difficulty_back_to_an_earlier_unit(self):
        self.state.apply_report(["unit-3"])
        model = self.script(
            turn("get_learner_state", 1),
            turn("ask_question", 2, unit_id="unit-3", reason="The learner reported loops."),
            turn("ask_question", 3, unit_id="unit-2", reason="Loop counting builds on updates."),
            turn("ask_question", 4, unit_id="unit-1", reason="Is assignment itself the problem?"),
            turn("finish", 5, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1"],
                 next_step="review_gap", summary="Updates are the problem."),
            turn("ask_question", 6, unit_id="unit-2", reason="Confirm with a second update question."),
            turn("finish", 7, primary_gap="unit-2", status="confirmed", evidence=["unit-2:q1", "unit-2:q2"],
                 next_step="review_gap", summary="Two answers on x = x + 1 were wrong."),
        )
        step = advance(self.session)
        self.assertEqual((step.question.unit_id, step.reason, step.number), ("unit-3", "The learner reported loops.", 1))
        opening = json.loads(model.seen[0][0]["content"])
        self.assertEqual([u["unit_id"] for u in opening["units_in_study_order"]], ["unit-1", "unit-2", "unit-3"])
        self.assertEqual(opening["learner_state"], model.outputs()[0])
        self.assertEqual(model.outputs()[0]["units"][2]["status"], "suspected")
        self.assertEqual(model.outputs()[0]["units"][2]["unused_questions"], 3)

        step = advance(self.session, 1)              # wrong
        self.assertEqual(step.question.unit_id, "unit-2")
        self.assertEqual(model.outputs()[-1]["correct"], False)
        self.assertEqual(model.outputs()[-1]["unused_questions_on_this_unit"], 2)
        self.assertEqual(model.outputs()[-1]["questions_left"], MAX_QUESTIONS - 1)
        step = advance(self.session, 2)              # wrong
        self.assertEqual(step.question.unit_id, "unit-1")
        step = advance(self.session, 0)              # right
        # The first finish is rejected: one wrong answer is not a confirmed gap.
        self.assertEqual(step.question.id, "unit-2:q2")
        self.assertIn("A confirmed gap needs at least two wrong answers", model.outputs()[-1]["error"])
        done = advance(self.session, 1)              # wrong again

        self.assertIsInstance(done, Done)
        self.assertEqual((done.diagnosis.primary_gap, done.diagnosis.status), ("unit-2", "confirmed"))
        self.assertEqual(done.diagnosis.evidence, ("unit-2:q1", "unit-2:q2"))
        self.assertEqual([self.state.status(u.unit_id) for u in UNITS], ["uncertain", "gap", "uncertain"])
        self.assertEqual(self.session.asked, ["unit-3:q1", "unit-2:q1", "unit-1:q1", "unit-2:q2"])
        self.assertTrue(paired(self.session.items))
        self.assertEqual(self.session.trace.model_calls, 0)  # the fake model records no spans
        tool_spans = [span.name for span in self.session.trace.spans]
        self.assertEqual(tool_spans.count("tool:ask_question"), 4)
        self.assertIn("unit-2: Loop counting builds on updates.", [s.detail for s in self.session.trace.spans])
        self.assertEqual(advance(self.session), done)

    def test_waiting_for_an_answer_does_not_call_the_model(self):
        model = self.script(turn("ask_question", 1, unit_id="unit-1", reason="Start."))
        first = advance(self.session)
        self.assertEqual(advance(self.session), first)
        self.assertEqual(len(model.seen), 1)
        with self.assertRaises(ValueError):
            advance(self.session, 7)

    def test_question_budget_is_enforced_in_code(self):
        asks = [turn("ask_question", n, unit_id="unit-1" if n % 2 else "unit-3", reason="More evidence.")
                for n in range(1, MAX_QUESTIONS + 2)]
        model = self.script(*asks, turn("finish", 99, primary_gap="none", status="uncertain", evidence=[],
                                        next_step="continue", summary="Mixed answers."))
        self.bank.questions["unit-1"] += [DiagnosticQuestion(f"unit-1:x{n}", "unit-1", question("x?")) for n in range(3)]
        step = advance(self.session)
        for _ in range(MAX_QUESTIONS):
            step = advance(self.session, 0)
        self.assertIsInstance(step, Done)
        self.assertEqual(len(self.session.asked), MAX_QUESTIONS)
        self.assertIn(f"All {MAX_QUESTIONS} questions are used", model.outputs()[-1]["error"])

    def test_call_limit_ends_with_an_uncertain_diagnosis(self):
        self.state.apply_report(["unit-2"])
        limit = max_model_calls(self.session.config)
        self.assertEqual(limit, 12)  # 5 questions in the initial check, plus 7
        self.script(*[turn("get_learner_state", n) for n in range(limit)])
        done = advance(self.session)
        self.assertTrue(done.diagnosis.forced)
        self.assertEqual((done.diagnosis.primary_gap, done.diagnosis.status), ("unit-2", "uncertain"))
        self.assertEqual(self.session.model_calls, limit)

    def test_unavailable_questions_are_reported_to_the_model(self):
        self.bank.questions["unit-1"] = []
        self.bank.problems["unit-1"] = "The assigned pages have no teaching point."
        model = self.script(
            turn("ask_question", 1, unit_id="unit-1", reason="Start at the beginning."),
            turn("ask_question", 2, unit_id="unit-2", reason="Try the next unit."),
        )
        step = advance(self.session)
        self.assertEqual(step.question.unit_id, "unit-2")
        self.assertIn("no teaching point", model.outputs()[0]["error"])

    def test_an_outage_while_preparing_a_question_can_be_resumed(self):
        self.bank.broken = {"unit-1"}
        model = self.script(
            turn("ask_question", 1, unit_id="unit-1", reason="Start."),
            turn("ask_question", 2, unit_id="unit-2", reason="Retry elsewhere."),
        )
        with self.assertRaises(LLMError):
            advance(self.session)
        self.assertTrue(paired(self.session.items))
        self.assertIsNone(self.session.pending)
        step = advance(self.session)
        self.assertEqual(step.question.unit_id, "unit-2")
        self.assertIn("could not be prepared", model.outputs()[0]["error"])

    def test_extra_parallel_calls_get_an_output(self):
        both = ToolTurn(
            (ToolCall("a", "ask_question", {"unit_id": "unit-1", "reason": "One."}),
             ToolCall("b", "get_learner_state", {})),
            ({"type": "function_call", "call_id": "a", "name": "ask_question", "arguments": "{}"},
             {"type": "function_call", "call_id": "b", "name": "get_learner_state", "arguments": "{}"}),
        )
        self.script(both)
        self.assertIsInstance(advance(self.session), Ask)
        outputs = [item for item in self.session.items if item.get("type") == "function_call_output"]
        self.assertEqual([item["call_id"] for item in outputs], ["b"])


class FinishValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = LearnerState(UNITS)

    def finish(self, **changes):
        arguments = {"primary_gap": "unit-2", "status": "confirmed", "evidence": [],
                     "next_step": "review_gap", "summary": "Summary."}
        return validate_finish({**arguments, **changes}, self.state)

    def test_evidence_must_be_real_answers(self):
        self.assertIn("not answers the learner gave", self.finish(status="uncertain", evidence=["made-up"]))

    def test_self_report_alone_cannot_confirm_a_gap(self):
        self.state.apply_report(["unit-2"])
        self.assertIn("no answers yet", self.finish())
        self.assertIsNone(self.finish(status="uncertain"))

    def test_confirmed_gap_must_cite_its_wrong_answers(self):
        for n in (1, 2):
            self.state.record(f"q{n}", "unit-2", "multiple_choice", False, "diagnosis")
        self.state.record("q3", "unit-1", "multiple_choice", True, "practice")
        self.assertIn("Cite the wrong answers", self.finish(evidence=["q3"]))
        self.assertIsNone(self.finish(evidence=["q1", "q2"]))
        self.assertIn("cannot be 'none'", self.finish(primary_gap="none", next_step="continue"))

    def test_no_gap_needs_more_than_one_answer(self):
        self.state.record("q1", "unit-1", "multiple_choice", True, "diagnosis")
        self.assertIn("One answer cannot rule out", self.finish(primary_gap="none", next_step="continue"))
        self.state.record("q2", "unit-3", "multiple_choice", True, "diagnosis")
        self.assertIsNone(self.finish(primary_gap="none", next_step="continue"))

    def test_schemas_limit_units_to_this_material(self):
        ask, finish = tool_schemas(UNITS)[1:]
        self.assertEqual(ask["parameters"]["properties"]["unit_id"]["enum"], ["unit-1", "unit-2", "unit-3"])
        self.assertEqual(finish["parameters"]["properties"]["primary_gap"]["enum"][-1], "none")
        for schema in tool_schemas(UNITS):
            parameters = schema["parameters"]
            self.assertTrue(schema["strict"])
            self.assertEqual(sorted(parameters["required"]), sorted(parameters["properties"]))
            self.assertFalse(parameters["additionalProperties"])


class QuestionBankTests(unittest.TestCase):
    def setUp(self):
        self.pages = [PdfPage(1, "Assignment\nAssigning x = 2 sets x to 2."), PdfPage(2, "Updates\nx = x + 1 adds one.")]
        self.generate = self.enterContext(patch("tutor.assessment.questions.generate_questions"))

    def test_questions_are_built_once_per_unit_from_its_pages(self):
        self.generate.return_value = (question("T/F?", "true_false"), question("MC?"))
        bank = QuestionBank(UNITS[:2], self.pages)
        first = bank.pick("unit-1", exclude=())
        self.assertEqual((first.id, first.question.kind), ("unit-1:q1", "multiple_choice"))
        self.assertEqual(bank.pick("unit-1", exclude={"unit-1:q1"}).question.kind, "true_false")
        self.assertIsNone(bank.pick("unit-1", exclude={"unit-1:q1", "unit-1:q2"}))
        self.generate.assert_called_once()
        self.assertEqual(self.generate.call_args.kwargs["questions_wanted"], 3)
        self.assertEqual(bank.remaining("unit-1", exclude={"unit-1:q1"}), 1)
        self.assertIsNone(bank.remaining("unit-2", exclude=()))
        assignment, _ = self.generate.call_args.args
        self.assertEqual(assignment.source_ids, ("p1",))
        self.assertEqual([p.source_id for p in self.generate.call_args.kwargs["assigned_reading"]], ["p1"])
        self.assertIsNone(bank.pick("unit-9", exclude=()))

    def test_a_printed_exercise_and_its_copy_count_once(self):
        printed = question("Exercise 3. How many times does for i in range(4) run?")
        copy = Question("multiple_choice", "How many times does for i in range(4) run", ("4", "2", "3"), 0,
                        "range(4) yields four values.", "generated", ("p1",), "reference")
        other = question("What does range(3) produce?")
        self.generate.return_value = (printed, copy, other)
        bank = QuestionBank(UNITS[:2], self.pages)
        first = bank.pick("unit-1", exclude=())
        self.assertIs(first.question, printed)
        self.assertIs(bank.pick("unit-1", exclude={first.id}).question, other)
        self.assertEqual(bank.remaining("unit-1", exclude=()), 2)

    def test_unbuildable_units_record_why(self):
        self.generate.side_effect = PracticeError("No teaching point.")
        bank = QuestionBank(UNITS[:2], self.pages)
        self.assertIsNone(bank.pick("unit-2", exclude=()))
        self.assertEqual(bank.problems["unit-2"], "No teaching point.")

    def test_model_outages_are_not_cached(self):
        self.generate.side_effect = [LLMError("Could not reach OpenAI."), (question("MC?"),)]
        bank = QuestionBank(UNITS[:2], self.pages)
        with self.assertRaises(LLMError):
            bank.pick("unit-1", exclude=())
        self.assertEqual(bank.pick("unit-1", exclude=()).id, "unit-1:q1")
