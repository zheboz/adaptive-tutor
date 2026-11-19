import threading
import unittest
from unittest.mock import patch

from tests.test_agent_loop import FakeBank, ScriptedModel, UNITS, question, turn
from tutor.agent.bank import QuestionBank
from tutor.agent.loop import Ask, Done, advance, instructions, start_session
from tutor.agent.replan import after_daily_check, after_initial_check
from tutor.agent.state import LearnerState
from tutor.agent.tools import DAILY_QUESTIONS, Diagnosis, daily_config, initial_config, validate_finish
from tutor.ui.practice import practice_key
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

    def test_daily_scope_is_today_and_earlier_units(self):
        config = daily_config(UNITS, ["unit-2"], day=2)
        self.assertEqual((config.scope, config.today, config.max_questions), (("unit-1", "unit-2"), ("unit-2",), 3))
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
        self.state.record("practice-1", "unit-2", "multiple_choice", False, "practice")
        session = start_session(UNITS, self.state, FakeBank(), config)
        self.assertIn("after study day 2", instructions(config))
        self.assertIn("summary_language", instructions(config))
        self.assertIn(f"at most {DAILY_QUESTIONS} questions", instructions(config))
        model = ScriptedModel(
            turn("get_learner_state", 1),
            turn("ask_question", 2, unit_id="unit-3", reason="Later unit."),
            turn("ask_question", 3, unit_id="unit-2", reason="Practice was wrong."),
        )
        with patch("tutor.agent.loop.call_with_tools", side_effect=model):
            step = advance(session)
        opening = model.seen[0][0]["content"]
        self.assertIn('"studied_today": ["unit-2"]', opening)
        self.assertIn('"summary_language": "English"', opening)
        self.assertNotIn("unit-3", opening)
        state_output = model.outputs()[0]
        self.assertEqual([u["unit_id"] for u in state_output["units"]], ["unit-1", "unit-2"])
        self.assertEqual(state_output["units"][1]["answers"][0]["source"], "practice")
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

    def test_initial_check_reports_which_units_get_more_time(self):
        self.state.apply_report(["unit-1"])
        self.answer("unit-1", True, True)
        self.answer("unit-2", False, False)
        weak, change = after_initial_check(self.state, diagnosis("unit-2", "confirmed", "review_gap", ["q3", "q4"]))
        self.assertEqual(weak, ("unit-2",))
        self.assertEqual(change.trigger, "Initial check")
        self.assertIn("Variable updates will get more time (0 of 2 answers correct).", change.message)
        self.assertIn("Assignment won't get extra time (2 of 2 answers correct).", change.message)
        self.assertEqual(change.evidence, ("q3", "q4"))
        # The plan created afterwards gives the weak unit more time.
        self.assertEqual(self.state.focus_units(), weak)

    def test_initial_check_without_changes_says_so(self):
        _, change = after_initial_check(self.state, diagnosis())
        self.assertIn("spread the time evenly", change.message)
        self.state.apply_report(["unit-3"])
        _, change = after_initial_check(self.state, diagnosis())
        self.assertIn("Your answers support the topics you marked", change.message)

    def test_daily_check_inserts_a_review_after_the_day(self):
        days = schedule_units(UNITS, 3)
        same, change = after_daily_check(self.state, diagnosis(), days, 2)
        self.assertEqual((same, change), (days, None))

        self.answer("unit-2", False, False)
        updated, change = after_daily_check(
            self.state, diagnosis("unit-2", "confirmed", "review_today", ["q1", "q2"]), days, 2)
        self.assertEqual([d.assignments[0].kind for d in updated], ["study", "study", "review", "study"])
        self.assertEqual([d.number for d in updated], [1, 2, 3, 4])
        self.assertEqual((updated[2].assignments[0].unit.unit_id, updated[2].assignments[0].round), ("unit-2", 1))
        self.assertIn("Added a review of Variable updates as day 3", change.message)
        self.assertIn("needs another session", change.message)
        self.assertIn("unit-2", self.state.flagged)
        # A review already planned later is not added again.
        again, note = after_daily_check(self.state, diagnosis("unit-2", "confirmed", "review_today"), updated, 2)
        self.assertEqual(again, updated)
        self.assertIn("already planned for day 3, so no day was added", note.message)

    def test_a_review_comes_after_the_units_remaining_study_days(self):
        days = schedule_units(UNITS, 5)
        plan = [(d.assignments[0].unit.unit_id, d.assignments[0].kind) for d in days]
        self.assertEqual(plan[2:4], [("unit-2", "read"), ("unit-2", "apply")])
        updated, change = after_daily_check(self.state, diagnosis("unit-2", next_step="review_today"), days, 3)
        plan = [(d.assignments[0].unit.unit_id, d.assignments[0].kind) for d in updated]
        self.assertEqual(plan[2:6], [("unit-2", "read"), ("unit-2", "apply"), ("unit-2", "review"), ("unit-3", "study")])
        self.assertIn("as day 5", change.message)

    def test_revisit_names_the_earlier_unit_and_no_gap_reviews_the_weakest_today(self):
        days = schedule_units(UNITS, 3)
        updated, change = after_daily_check(self.state, diagnosis("unit-1", next_step="revisit_earlier"), days, 3)
        self.assertEqual(updated[3].assignments[0].unit.unit_id, "unit-1")
        self.assertIn("comes from this earlier unit", change.message)
        self.answer("unit-3", False)
        updated, _ = after_daily_check(self.state, diagnosis(next_step="review_today"), days, 3)
        self.assertEqual(updated[3].assignments[0].unit.unit_id, "unit-3")

    def test_each_review_round_gets_its_own_practice(self):
        days = schedule_units(UNITS, 3)
        once = insert_review(days, 1, UNITS[0])
        twice = insert_review(once, 3, UNITS[0])
        reviews = [a for d in twice for a in d.assignments if a.kind == "review"]
        self.assertEqual([r.round for r in reviews], [1, 2])
        keys = {practice_key("doc", a) for d in twice for a in d.assignments}
        self.assertEqual(len(keys), 5)
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
