import json
import unittest
from unittest.mock import patch

from tests.test_agent_loop import ScriptedModel, turn
from tests.test_pdf_preview import previewed_pdf
from tests.ui_helpers import UITestCase, begin, create_plan, show_panel
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

    def test_first_model_call_can_answer_from_initial_passages_with_a_checked_quote(self):
        model = self.script(
            turn("answer", 1, text="It takes the old value of x and adds one.",
                 citations=[{"page": "p2", "quote": QUOTE.upper()}]),
        )
        reply = ask(self.session, "  Explain the   updating statement. ", {"study_day": 2, "weak_topics": ["Updating"]})
        self.assertEqual(reply.kind, "answer")
        self.assertEqual(reply.citations, (Citation("p2", QUOTE.upper()),))
        first = json.loads(model.seen[0][0]["content"])
        self.assertEqual(first, {"question": "Explain the updating statement.",
                                 "context": {"study_day": 2, "weak_topics": ["Updating"]},
                                 "initial_passages": [{"page": "p2", "text": PAGES[1].text}]})
        self.assertEqual(len(model.seen), 1)
        self.assertEqual(self.session.log, [("Explain the updating statement.", reply)])
        spans = [span.name for span in self.session.trace.spans]
        self.assertEqual(spans, ["retrieval:initial_search", "tool:answer"])

    def test_accepts_a_sentence_from_one_column_of_an_interleaved_slide(self):
        # Extracted text reads a two-column slide line by line across both columns.
        self.session = start_qa([PdfPage(1, "Klarna Air Canada\nIts assistant handled two-thirds of "
                                            "Its chatbot described a refund\nsupport chats in its first month. "
                                            "policy that did not exist.")])
        self.script(
            turn("read_page", 1, page="p1"),
            turn("answer", 2, text="Two-thirds.", citations=[
                {"page": "p1", "quote": "Its assistant handled two-thirds of support chats in its first month"}]),
        )
        self.assertEqual(ask(self.session, "How many chats did Klarna's assistant handle?").kind, "answer")

    def test_citations_must_be_retrieved_and_verbatim(self):
        model = self.script(
            turn("answer", 1, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
            turn("read_page", 2, page="p4"),
            turn("answer", 3, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body three times"}]),
            turn("answer", 4, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs"}]),
            turn("answer", 5, text="Loops repeat.", citations=[]),
            turn("answer", 6, text="Loops repeat.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
        )
        reply = ask(self.session, "Explain repetition.")
        errors = [o.get("error", "") for o in model.outputs() if "error" in o]
        self.assertIn("was not retrieved", errors[0])
        self.assertIn("not on p4", errors[1])
        self.assertIn("not a single word", errors[2])
        self.assertIn("at least one", errors[3])
        self.assertEqual((reply.kind, reply.citations), ("answer", (Citation("p4", "runs its body 3 times"),)))

    def test_the_reply_lists_the_steps_the_tutor_took(self):
        self.script(
            turn("search_material", 1, query="What does the loop do?"),   # rejected: the question itself
            turn("search_material", 2, query="range(3) loop"),
            turn("read_page", 3, page="p4"),
            turn("answer", 4, text="It runs 3 times.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
        )
        reply = ask(self.session, "What does the loop do?")
        self.assertEqual(reply.kind, "answer")
        self.assertEqual(len(reply.steps), 3)
        self.assertTrue(reply.steps[0].startswith("Searched “What does the loop do?” → "))
        self.assertTrue(reply.steps[1].startswith("Searched “range(3) loop” → p4"))
        self.assertEqual(reply.steps[2], "Read page 4")
        self.assertEqual(reply.model_calls, 4)

    def test_declines_only_after_searching(self):
        model = self.script(
            turn("cannot_answer", 1, reason="Not covered.", missing_topic="recursion"),
            turn("search_material", 2, query="What is recursion?"),
            turn("cannot_answer", 3, reason="Not covered.", missing_topic="recursion"),
            turn("search_material", 4, query="recursion function calls itself"),
            turn("cannot_answer", 5, reason="The notes never mention recursion.", missing_topic="recursion"),
        )
        reply = ask(self.session, "What is recursion?")
        outputs = model.outputs()
        self.assertIn("Search the material with different words", outputs[0]["error"])
        self.assertIn("already been searched", outputs[1]["error"])
        self.assertEqual(outputs[2], outputs[0])
        self.assertEqual(outputs[3]["results"], [])
        self.assertEqual((reply.kind, reply.text, reply.missing_topic),
                         ("declined", "The notes never mention recursion.", "recursion"))

    def test_follow_up_questions_see_earlier_turns(self):
        model = self.script(
            turn("answer", 1, text="x holds 2.", citations=[{"page": "p1", "quote": "the variable x holds the value 2"}]),
            turn("answer", 2, text="x holds 2.", citations=[{"page": "p1", "quote": "the variable x holds the value 2"}]),
            turn("search_material", 3, query="updating"),
            turn("answer", 4, text="Then it becomes 3.", citations=[{"page": "p2", "quote": QUOTE}]),
        )
        ask(self.session, "What does the assignment do?")
        ask(self.session, "And with x = x + 1?")
        history = model.seen[1][:2]
        self.assertEqual(history, [{"role": "user", "content": "What does the assignment do?"},
                                   {"role": "assistant", "content": "x holds 2."}])
        self.assertIn("was not retrieved", model.outputs()[0]["error"])
        self.assertEqual(self.session.log[-1][1].citations, (Citation("p2", QUOTE),))
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


class TutorChatUITests(UITestCase):
    def setUp(self):
        super().setUp()
        topics = [Topic(title="Updating", summary="Change a value.", source_ids=["p2"]),
                  Topic(title="Loops", summary="Repeat.", source_ids=["p4"])]
        self.enterContext(patch("tutor.materials.outline.generate_outline")).return_value = Outline(topics=topics)
        planner = self.enterContext(patch("tutor.planning.units.generate_structured"))
        planner.side_effect = [
            UnitPlan(steps=[UnitStep(title=t.title, topic_ids=[n]) for n, t in enumerate(topics, 1)]),
            Solution(tasks=[UnitTask(unit_number=n, objective=t.summary, activity="Explain.") for n, t in enumerate(topics, 1)]),
        ]
        self.app = self.new_app()
        self.document = begin(self.app, *[page.text for page in PAGES])

    def test_the_tutor_is_available_while_reviewing_the_topics(self):
        # Asking needs only the PDF, so the chat is offered under the topics, before any plan.
        self.assertIn("Ask the tutor about this material", [e.label for e in self.app.main.expander])
        model = ScriptedModel(
            turn("search_material", 1, query="range(3)"),
            turn("answer", 2, text="It runs 3 times.", citations=[{"page": "p4", "quote": "runs its body 3 times"}]),
        )
        with patch("tutor.agent.qa.call_with_tools", side_effect=model):
            self.app.chat_input(key="tutor_question").set_value("How often does range(3) loop?").run()
        self.assertFalse(self.app.exception)
        self.assertEqual(json.loads(model.seen[0][-1]["content"])["context"], {"weak_topics": []})
        panel = self.app.main.container("tutor_chat_panel")
        self.assertIn("It runs 3 times.", [m.value for m in panel.markdown])
        # There is no reader during setup, so the cited page opens in a window.
        panel.button(key="qa_0_p4").click().run()
        self.assertEqual(previewed_pdf(self.app), (self.document, [4]))
        # The conversation is kept once studying starts.
        create_plan(self.app, 2)
        show_panel(self.app, "Ask the tutor")
        self.assertIn("It runs 3 times.", [m.value for m in self.app.main.container("tutor_chat_panel").markdown])

    def test_beside_the_pdf_chat_answers_with_page_links_and_knows_the_plan(self):
        self.app.checkbox(key="weak_topic_0").check()
        create_plan(self.app, 2)
        show_panel(self.app, "Ask the tutor")
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
            # What the tutor did is shown under its answer: its searches with the pages found, and its calls.
            self.assertIn("How the tutor found this · 2 model calls", [e.label for e in panel.expander])
            steps = [c.value for c in panel.caption]
            self.assertTrue(any(step.startswith("Searched “x = x + 1” → p2") for step in steps), steps)
            panel.button(key="qa_0_p2").click().run()
            # The cited page opens in the reader beside the chat; the chat stays open.
            self.assertEqual(previewed_pdf(self.app), (self.document, [2]))
            self.assertEqual(self.app.segmented_control(key="today_tab").value, "Ask the tutor")

            self.app.chat_input(key="tutor_question").set_value("What is recursion?").run()
            panel = self.app.main.container("tutor_chat_panel")
            self.assertIn("Your material doesn't cover this. Recursion is not in your notes.",
                          [m.value for m in panel.markdown])
            self.assertIn("Missing: recursion", "\n".join(c.value for c in panel.caption))

    def test_an_outage_is_shown_and_the_question_can_be_asked_again(self):
        with patch("tutor.agent.qa.call_with_tools", side_effect=LLMError("Could not reach OpenAI.")):
            self.app.chat_input(key="tutor_question").set_value("Explain loops").run()
        self.assertIn("Could not reach OpenAI.", self.app.main.container("tutor_chat_panel").error[0].value)
        self.assertEqual(self.app.session_state["qa_session"].log, [])
