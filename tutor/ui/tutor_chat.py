"""The "Ask the tutor" chat: questions answered from the learner's material, with checked quotes.

It needs only the PDF, so it is offered while the learner reviews the topics and beside the PDF
while they study."""

from collections.abc import Sequence
import streamlit as st

from tutor.agent.qa import QASession, ask, start_qa
from tutor.assessment import retrieval
from tutor.llm import LLMError
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.ui import learner, navigation
from tutor.ui.citations import render_sources


def tutor_context(result: Outline | None) -> dict:
    """What the tutor should know about the learner when answering a question."""
    topics = result.topics if result is not None else []
    context: dict = {"weak_topics": [
        topics[number - 1].title for number in sorted(learner.weak_topic_numbers()) if number <= len(topics)
    ]}
    days = st.session_state.get("study_plan")
    number = navigation.current_day()
    if days and st.session_state.get("planned_days") is not None and number <= len(days):
        context["study_day"] = number
        context["todays_units"] = [
            {"title": a.unit.title, "objective": a.unit.objective, "pages": list(a.source_ids)}
            for a in days[number - 1].assignments
        ]
    return context


def qa_session(pages: Sequence[PdfPage]) -> QASession:
    session = st.session_state.get("qa_session")
    if session is None:
        # Share the passage index with the quick check.
        if "passage_index" not in st.session_state:
            st.session_state.passage_index = retrieval.build_index(pages)
        session = start_qa(pages, st.session_state.passage_index)
        st.session_state.qa_session = session
    return session


def render_tutor_chat(pages: Sequence[PdfPage], result: Outline | None, height: int) -> None:
    session = qa_session(pages)
    context = tutor_context(result)
    chat = st.container(key="tutor_chat")
    messages = chat.container(height=height, border=True, key="tutor_chat_panel")
    question = chat.chat_input("Ask about your material", key="tutor_question")
    error = None
    if question:
        # While the tutor works, show the question and each step it takes; the steps stay under the
        # answer afterwards, in "How the tutor found this".
        working = messages.empty()
        with working.container():
            with st.chat_message("user"):
                st.text(question)
            status = st.status("The tutor is searching your material…", expanded=True)
        try:
            ask(session, question, context, on_step=status.write)
        except LLMError as failure:
            error = str(failure)
        except ValueError:
            pass
        working.empty()

    with messages:
        if not session.log:
            st.caption("Ask anything about this material. Answers quote the pages they rely on; "
                       "questions the material doesn't cover are declined rather than guessed.")
        for number, (asked, reply) in enumerate(session.log):
            with st.chat_message("user"):
                st.text(asked)
            with st.chat_message("assistant"):
                if reply.kind == "declined":
                    st.markdown(f"Your material doesn't cover this. {reply.text}")
                    if reply.missing_topic:
                        st.caption(f"Missing: {reply.missing_topic}. Upload material on it to study it here.")
                else:
                    st.markdown(reply.text)
                if reply.citations:
                    render_sources(list(dict.fromkeys(c.source_id for c in reply.citations)), f"qa_{number}")
                    with st.expander("Quoted from your material"):
                        for citation in reply.citations:
                            st.caption(f"Page {citation.source_id[1:]}: “{citation.quote}”")
                if reply.steps:
                    calls = f" · {reply.model_calls} model call{'s' if reply.model_calls != 1 else ''}"
                    with st.expander(f"How the tutor found this{calls if reply.model_calls else ''}"):
                        for step in reply.steps:
                            st.caption(step)
        if error:
            st.error(error)
    if session.log:
        trace = session.trace
        st.caption(f"This conversation: {trace.model_calls} model calls · {trace.total_tokens} tokens")
