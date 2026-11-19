import threading
import unittest
from unittest.mock import patch

from tests.test_agent_loop import FakeBank, ScriptedModel, UNITS, question, turn
from tutor.agent.bank import QuestionBank
from tutor.agent.loop import Ask, Done, advance, instructions, start_session
from tutor.agent.replan import after_daily_check
from tutor.agent.state import LearnerState
from tutor.agent.tools import DAILY_QUESTIONS, Diagnosis, daily_config, initial_config, validate_finish
from tutor.llm import LLMError, Trace, tracing
from tutor.materials.ingest import PdfPage
from tutor.planning import insert_review, schedule_units


def diagnosis(gap=None, status="uncertain", next_step="continue", evidence=()):
    return Diagnosis(gap, status, tuple(evidence), next_step, "Summary.")


class CheckConfigTests(unittest.TestCase):
    def setUp(self):
        self.state = LearnerState(UNITS)

    def finish(self, config, **changes):
        arguments = {"primary_gap": "none", "status": "uncertain", "evidence": [],
                     "next_step": config.next_steps[0], "summary": "Summary."}
        return validate_finish({**arguments, **changes}, self.state, config)

    def test_daily_questions_are_about_today_and_conclusions_may_name_earlier_units(self):
        config = daily_config(UNITS, ["unit-2"], day=2)
        self.assertEqual((config.scope, config.today, config.max_questions), (("unit-1", "unit-2"), ("unit-2",), 3))
        self.assertEqual(config.askable, ("unit-2",))
        two_today = daily_config(UNITS, ["unit-2", "unit-3"], day=2, askable=["unit-3", "unit-1"])
        self.assertEqual(two_today.askable, ("unit-3",))
        self.assertIn("Unknown unit", self.finish(config, primary_gap="unit-3"))
        self.assertEqual(initial_config(UNITS).scope, ("unit-1", "unit-2", "unit-3"))

    def test_next_step_must_match_where_the_gap_is(self):
        daily = daily_config(UNITS, ["unit-2"], day=2)
        self.assertIsNone(self.finish(daily, primary_gap="unit-2", next_step="review_today"))
        self.assertIn("use revisit_earlier", self.finish(daily, primary_gap="unit-1", next_step="review_today"))
        self.assertIsNone(self.finish(daily, primary_gap="unit-1", next_step="revisit_earlier"))
        self.assertIn("earlier unit", self.finish(daily, primary_gap="unit-2", next_step="revisit_earlier"))
        self.assertIn("one of", self.finish(daily, next_step="review_gap"))
        initial = initial_config(UNITS)
        self.assertIn("needs a unit", self.finish(initial, next_step="review_gap"))
        for n in (1, 2):
            self.state.record(f"q{n}", "unit-2", "multiple_choice", False, "diagnosis")
        self.assertIn("needs review", self.finish(daily, primary_gap="unit-2", status="confirmed",
                                                  evidence=["q1"], next_step="continue"))

    def test_daily_session_is_limited_to_its_scope_and_budget(self):
        config = daily_config(UNITS, ["unit-2"], day=2)
        self.state.record("quiz-1", "unit-1", "multiple_choice", False, "quiz")
        session = start_session(UNITS, self.state, FakeBank(), config)
        self.assertIn("after study day 2", instructions(config))
        self.assertIn("summary_language", instructions(config))
        self.assertIn(f"at most {DAILY_QUESTIONS} questions", instructions(config))
        model = ScriptedModel(
            turn("get_learner_state", 1),
            turn("ask_question", 2, unit_id="unit-1", reason="Earlier unit."),
            turn("ask_question", 3, unit_id="unit-2", reason="Studied today."),
        )
        with patch("tutor.agent.loop.call_with_tools", side_effect=model):
            step = advance(session)
        opening = model.seen[0][0]["content"]
        self.assertIn('"studied_today": ["unit-2"]', opening)
        self.assertIn('"summary_language": "English"', opening)
        self.assertIn('"units_you_can_ask_about": ["unit-2"]', opening)
        self.assertNotIn("unit-3", opening)
        state_output = model.outputs()[0]
        self.assertEqual([u["unit_id"] for u in state_output["units"]], ["unit-1", "unit-2"])
        self.assertEqual(state_output["units"][0]["answers"][0]["source"], "quiz")
        self.assertIn("Unknown unit", model.outputs()[1]["error"])
        self.assertEqual((step.question.unit_id, session.config.max_questions), ("unit-2", 3))


class FocusAndReplanTests(unittest.TestCase):
    def setUp(self):
        self.state = LearnerState(UNITS)

    def answer(self, unit_id, *results):
        for correct in results:
            self.state.record(f"q{len(self.state.answers()) + 1}", unit_id, "multiple_choice", correct, "diagnosis")

    def test_focus_combines_reports_evidence_and_flags(self):
        self.state.apply_report(["unit-1", "unit-3"])
        self.answer("unit-1", True, True)        # reported, but mastered
        self.answer("unit-2", False, False)      # not reported, but a gap
        self.state.flag("unit-3")
        self.assertEqual(self.state.focus_units(), ("unit-2", "unit-3"))
        self.state.flag("unknown")
        self.assertNotIn("unknown", self.state.flagged)

    def wrong_answers(self, unit_id, count, right=0):
        asked = []
        for correct in [False] * count + [True] * right:
            question_id = f"q{len(self.state.answers()) + 1}"
            self.state.record(question_id, unit_id, "multiple_choice", correct, "diagnosis")
            asked.append(question_id)
        return asked

    def test_mostly_wrong_answers_add_a_review_at_the_end(self):
        days = schedule_units(UNITS, 3)
        same, change = after_daily_check(self.state, diagnosis(), days, 2)
        self.assertEqual((same, change), (days, None))

        asked = self.wrong_answers("unit-2", 2, right=1)
        updated, change = after_daily_check(
            self.state, diagnosis("unit-2", "confirmed", "review_today", asked), days, 2, asked)
        self.assertEqual(updated[:3], days)
        self.assertEqual(len(updated), 4)
        review = updated[3].assignments[0]
        self.assertEqual((review.unit.unit_id, review.kind, review.round), ("unit-2", "review", 1))
        self.assertTrue(change.changed)
        self.assertIn("Added a review of Variable updates as day 4, at the end of the plan", change.message)
        self.assertIn("unit-2", self.state.flagged)
        # A review already planned later is not added again.
        again, note = after_daily_check(self.state, diagnosis("unit-2", "confirmed", "review_today"), updated, 2,
                                        asked)
        self.assertEqual(again, updated)
        self.assertFalse(note.changed)
        self.assertIn("already planned for day 4, so no day was added", note.message)

    def test_which_checks_add_a_review(self):
        days = schedule_units(UNITS, 3)
        for wrong, right, added in ((2, 0, True), (2, 1, True), (3, 0, True),
                                    (1, 0, False), (1, 2, False), (2, 2, False), (0, 3, False)):
            with self.subTest(wrong=wrong, right=right):
                self.state = LearnerState(UNITS)
                asked = self.wrong_answers("unit-2", wrong, right)
                updated, change = after_daily_check(
                    self.state, diagnosis("unit-2", "confirmed", "review_today"), days, 2, asked)
                self.assertEqual(len(updated) == 4, added)
                self.assertEqual(change.changed, added)
                if not added:
                    self.assertIn(f"{wrong} of {wrong + right} answers in this check were wrong", change.message)
                    self.assertIn("at least 2 answers are wrong and they outnumber the right ones", change.message)

    def test_revisit_names_the_earlier_unit_and_no_gap_reviews_the_weakest_today(self):
        days = schedule_units(UNITS, 3)
        asked = self.wrong_answers("unit-3", 2)
        updated, change = after_daily_check(self.state, diagnosis("unit-1", next_step="revisit_earlier"), days, 3,
                                            asked)
        self.assertEqual(updated[3].assignments[0].unit.unit_id, "unit-1")
        self.assertIn("comes from this earlier unit", change.message)
        updated, _ = after_daily_check(self.state, diagnosis(next_step="review_today"), days, 3, asked)
        self.assertEqual(updated[3].assignments[0].unit.unit_id, "unit-3")

    def test_each_review_round_is_numbered(self):
        days = schedule_units(UNITS, 3)
        once = insert_review(days, 1, UNITS[0])
        twice = insert_review(once, 3, UNITS[0])
        reviews = [a for d in twice for a in d.assignments if a.kind == "review"]
        self.assertEqual([r.round for r in reviews], [1, 2])
        with self.assertRaises(ValueError):
            insert_review(days, 9, UNITS[0])


class PrefetchTests(unittest.TestCase):
    def setUp(self):
        self.pages = [PdfPage(1, "Assignment\nx = 2 stores 2."), PdfPage(2, "Updates\nx = x + 1 adds one.")]

    def test_questions_are_built_in_the_background_once(self):
        threads = []

        def build(assignment, passages, **kwargs):
            threads.append(threading.current_thread().name)
            return (question(f"{assignment.unit.title}?"),)

        with patch("tutor.assessment.questions.generate_questions", side_effect=build) as generate:
            bank = QuestionBank(UNITS[:2], self.pages)
            bank.prefetch(["unit-1", "unit-2", "unit-1", "unit-9"])
            self.assertEqual(bank.pick("unit-2", ()).question.prompt, "Variable updates?")
            self.assertEqual(bank.pick("unit-1", ()).question.prompt, "Assignment?")
            bank.prefetch(["unit-1"])
        self.assertEqual(generate.call_count, 2)
        self.assertTrue(all(name.startswith("question-bank") for name in threads))

    def test_background_failures_are_not_cached(self):
        trace = Trace()
        with patch("tutor.assessment.questions.generate_questions",
                   side_effect=[LLMError("Could not reach OpenAI."), (question("Q?"),)]):
            bank = QuestionBank(UNITS[:1], self.pages)
            with tracing(trace):
                bank.prefetch(["unit-1"])
            with self.assertRaises(LLMError):
                bank.pick("unit-1", ())
            self.assertEqual(bank.pick("unit-1", ()).id, "unit-1:q1")


class SummaryLanguageTests(unittest.TestCase):
    def test_language_is_decided_from_the_unit_text(self):
        from tutor.agent.loop import summary_language
        from tutor.planning import StudyUnit

        def unit(title):
            return StudyUnit("u", title, "", (), "")

        self.assertEqual(summary_language([unit("Loops and counters")]), "English")
        self.assertEqual(summary_language([unit("循环 for loops")]), "Chinese")
        self.assertEqual(summary_language([unit("Bucles y contadores según el índice")]),
                         "the language of the unit titles")
        self.assertEqual(summary_language([unit("Циклы и счётчики")]), "the language of the unit titles")


class DayBankTests(unittest.TestCase):
    def test_a_days_questions_come_from_its_own_pages(self):
        from tutor.planning import StudyAssignment
        pages = [PdfPage(n, f"Page {n}: x = {n} stores {n}.") for n in (1, 2, 3)]
        unit = UNITS[0].__class__("unit-1", "Assignment", "Store a value.", ("p1", "p2", "p3"), "Trace x.")
        reading = StudyAssignment(unit, "read", ("p2",))
        with patch("tutor.assessment.questions.generate_questions", return_value=(question("Q?"),)) as generate:
            bank = QuestionBank([unit], pages, [reading], prefix="read0-p2:")
            self.assertEqual(bank.prepare(["unit-1"]), {"unit-1": 1})
        assignment = generate.call_args.args[0]
        self.assertEqual((assignment.kind, assignment.source_ids), ("read", ("p2",)))
        self.assertEqual([p.source_id for p in generate.call_args.kwargs["assigned_reading"]], ["p2"])
        self.assertEqual(bank.pick("unit-1", ()).id, "read0-p2:unit-1:q1")
