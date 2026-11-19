import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_outline_ui import upload
from tests.test_pdf_preview import APP, button, previewed_pdf
from tests.test_planning_ui import create_plan
from tutor.agent.qa import MAX_MODEL_CALLS, Citation, ask, start_qa
from tutor.assessment.retrieval import build_index, search
from tutor.llm import LLMError
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline, Topic
from tutor.planning.units import Solution, UnitPlan, UnitStep, UnitTask


PAGES = [
    PdfPage(1, "Assignment\nAfter x = 2, the variable x holds the value 2."),
    PdfPage(2, "Updating\nThe statement x = x + 1 reads x, adds 1, and stores the result back in x."),
    PdfPage(3, ""),
    PdfPage(4, "Loops\nThe loop for i in range(3) runs its body 3 times."),
]
QUOTE = "reads x, adds 1, and stores the result back in x"


class SearchTests(unittest.TestCase):
    def test_free_text_search_ranks_matching_pages(self):
        index = build_index(PAGES)
        self.assertEqual([p.source_id for p in search(index, "updating statement")][0], "p2")
        # Matching is by word, so the agent must retry with the material's own wording.
        self.assertEqual(search(index, "update"), ())
        # Code fragments have no indexable words but still match verbatim.
        self.assertEqual([p.source_id for p in search(index, "x = x + 1")], ["p2"])
        self.assertEqual([p.source_id for p in search(index, "range(3)")], ["p4"])
        self.assertEqual(search(index, "x"), ())
        self.assertEqual([p.source_id for p in search(index, "range loop body")], ["p4"])
        self.assertEqual(search(index, "the of and"), ())
        self.assertEqual(search(index, "recursion"), ())


class AskTests(unittest.TestCase):
    def setUp(self):
        self.session = start_qa(PAGES)

    def script(self, *turns):
        model = ScriptedModel(*turns)
        self.enterContext(patch("tutor.agent.qa.call_with_tools", side_effect=model))
        return model

    def test_searches_then_answers_with_a_checked_quote(self):
        model = self.script(
            turn("search_material", 1, query="x = x + 1"),
            turn("answer", 2, text="It takes the old value of x and adds one.",
                 citations=[{"page": "p2", "quote": QUOTE.upper()}]),
        )
        reply = ask(self.session, "  What does x = x + 1   do? ", {"study_day": 2, "weak_topics": ["Updating"]})
        self.assertEqual(reply.kind, "answer")
        self.assertEqual(reply.citations, (Citation("p2", QUOTE.upper()),))
        first = json.loads(model.seen[0][0]["content"])
        self.assertEqual(first, {"question": "What does x = x + 1 do?",
                                 "context": {"study_day": 2, "weak_topics": ["Updating"]}})
        self.assertEqual(model.outputs()[0]["results"][0]["page"], "p2")
        self.assertEqual(self.session.log, [("What does x = x + 1 do?", reply)])
        spans = [span.name for span in self.session.trace.spans]
        self.assertEqual(spans, ["tool:search_material", "tool:answer"])

    def test_citations_must_be_retrieved_and_verbatim(self):
        model = self.script(
            turn("answer", 1, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
            turn("read_page", 2, page="p4"),
            turn("answer", 3, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body three times"}]),
            turn("answer", 4, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs"}]),
            turn("answer", 5, text="Loops repeat.", citations=[]),
            turn("answer", 6, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
        )
        reply = ask(self.session, "How many times does the loop run?")
        errors = [o.get("error", "") for o in model.outputs() if "error" in o]
        self.assertIn("was not retrieved", errors[0])
        self.assertIn("not on p4", errors[1])
        self.assertIn("not a single word", errors[2])
        self.assertIn("at least one", errors[3])
        self.assertEqual((reply.kind, reply.citations), ("answer", (Citation("p4", "runs its body 3 times"),)))

    def test_declines_only_after_searching(self):
        model = self.script(
            turn("cannot_answer", 1, reason="Not covered.", missing_topic="recursion"),
            turn("search_material", 2, query="recursion function calls itself"),
            turn("cannot_answer", 3, reason="The notes never mention recursion.", missing_topic="recursion"),
        )
        reply = ask(self.session, "What is recursion?")
        self.assertIn("Search the material before", model.outputs()[0]["error"])
        self.assertEqual(model.outputs()[1]["results"], [])
        self.assertEqual((reply.kind, reply.text, reply.missing_topic),
                         ("declined", "The notes never mention recursion.", "recursion"))

    def test_follow_up_questions_see_earlier_turns(self):
        model = self.script(
            turn("search_material", 1, query="assignment"),
            turn("answer", 2, text="x holds 2.", citations=[{"page": "p1", "quote": "the variable x holds the value 2"}]),
            turn("search_material", 3, query="updating"),
            turn("answer", 4, text="Then it becomes 3.", citations=[{"page": "p2", "quote": QUOTE}]),
        )
        ask(self.session, "What does x hold after x = 2?")
        ask(self.session, "And after x = x + 1?")
        history = model.seen[2][:2]
        self.assertEqual(history, [{"role": "user", "content": "What does x hold after x = 2?"},
                                   {"role": "assistant", "content": "x holds 2."}])
        # Pages retrieved for an earlier question cannot be cited without retrieving them again.
        self.assertEqual(len(self.session.log), 2)

    def test_gives_up_at_the_call_limit_and_surfaces_outages(self):
        self.script(*[turn("search_material", n, query="loops") for n in range(MAX_MODEL_CALLS)])
        reply = ask(self.session, "Explain loops")
        self.assertEqual(reply.kind, "failed")
        self.script(LLMError("Could not reach OpenAI."))
        with self.assertRaises(LLMError):
            ask(self.session, "Explain loops again")
        self.assertEqual(len(self.session.log), 1)
        with self.assertRaises(ValueError):
            ask(self.session, "   ")

    def test_search_limit_and_final_call_force_a_decision(self):
        model = ScriptedModel(
            *[turn("search_material", n, query=f"recursion {n}") for n in range(5)],
            turn("cannot_answer", 9, reason="Your notes cover loops, not recursion.", missing_topic="recursion"),
        )
        with patch("tutor.agent.qa.call_with_tools", side_effect=model) as fake:
            reply = ask(self.session, "What is recursion?")
        self.assertEqual(model.outputs()[2]["searches_left"], 0)
        self.assertIn("searches are used", model.outputs()[3]["error"])
        offered = [[tool["name"] for tool in call.kwargs["tools"]] for call in fake.call_args_list]
        self.assertEqual(len(offered), MAX_MODEL_CALLS)
        self.assertEqual(len(offered[0]), 4)
        self.assertEqual(offered[-1], ["answer", "cannot_answer"])
        self.assertEqual((reply.kind, reply.missing_topic), ("declined", "recursion"))

    def test_tools_offer_only_readable_pages(self):
        model = ScriptedModel(turn("search_material", 1, query="x"), turn("cannot_answer", 2, reason="r", missing_topic="t"))
        with patch("tutor.agent.qa.call_with_tools", side_effect=model) as fake:
            ask(self.session, "What is x?")
        self.assertEqual(fake.call_args.kwargs["name"], "model:tutor")
        tools = {tool["name"]: tool for tool in fake.call_args.kwargs["tools"]}
        self.assertEqual(tools["read_page"]["parameters"]["properties"]["page"]["enum"], ["p1", "p2", "p4"])
        self.assertTrue(all(tool["strict"] for tool in tools.values()))


class TutorChatUITests(unittest.TestCase):
    def setUp(self):
        topics = [Topic(title="Updating", summary="Change a value.", source_ids=["p2"]),
                  Topic(title="Loops", summary="Repeat.", source_ids=["p4"])]
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain.") for n, t in enumerate(topics, 1)]),
        ]
        self.app = AppTest.from_file(APP).run()
        self.document = upload(self.app, *[page.text for page in PAGES])

    def test_chat_appears_with_the_outline_and_answers_with_page_links(self):
        self.assertFalse(self.app.chat_input)
        button(self.app.sidebar, "Generate outline").click().run()
        self.app.checkbox(key="weak_topic_0").check()
        create_plan(self.app, 2)
        model = ScriptedModel(
            turn("search_material", 1, query="x = x + 1"),
            turn("answer", 2, text="It **adds one** to x.", citations=[{"page": "p2", "quote": QUOTE}]),
            turn("search_material", 3, query="recursion"),
            turn("cannot_answer", 4, reason="Recursion is not in your notes.", missing_topic="recursion"),
        )
        with patch("tutor.agent.qa.call_with_tools", side_effect=model):
            self.app.chat_input(key="tutor_question").set_value("What does x = x + 1 do?").run()
            self.assertFalse(self.app.exception)
            context = json.loads(model.seen[0][-1]["content"])["context"]
            self.assertEqual(context["weak_topics"], ["Updating"])
            self.assertEqual(context["study_day"], 1)
            self.assertEqual(context["todays_units"][0]["title"], "Updating")
            panel = self.app.main.container("tutor_chat_panel")
            self.assertIn("It **adds one** to x.", [m.value for m in panel.markdown])
            panel.button(key="qa_0_p2").click().run()
            # The cited page opens in the PDF; the chat below and the view beside the PDF stay as they were.
            self.assertEqual(previewed_pdf(self.app), (self.document, [2]))
            self.assertEqual(self.app.segmented_control(key="right_view").value, "Today")

            self.app.chat_input(key="tutor_question").set_value("What is recursion?").run()
            panel = self.app.main.container("tutor_chat_panel")
            self.assertIn("Your material doesn't cover this. Recursion is not in your notes.",
                          [m.value for m in panel.markdown])
            self.assertIn("Missing: recursion", "\n".join(c.value for c in panel.caption))

    def test_an_outage_is_shown_and_the_question_can_be_asked_again(self):
        button(self.app.sidebar, "Generate outline").click().run()
        with patch("tutor.agent.qa.call_with_tools", side_effect=LLMError("Could not reach OpenAI.")):
            self.app.chat_input(key="tutor_question").set_value("Explain loops").run()
        self.assertIn("Could not reach OpenAI.", self.app.main.container("tutor_chat_panel").error[0].value)
        self.assertEqual(self.app.session_state["qa_session"].log, [])
