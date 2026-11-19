"""The "Ask the tutor" chat: questions answered from the learner's material, with checked quotes."""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from tutor.agent.qa import QASession, ask, start_qa
from tutor.assessment import retrieval
from tutor.llm import LLMError
from tutor.materials.ingest import PdfPage
from tutor.ui.citations import render_sources


def qa_session(pages: Sequence[PdfPage]) -> QASession:
    session = st.session_state.get("qa_session")
    if session is None:
        # Share the passage index with the initial quiz.
        if "passage_index" not in st.session_state:
            st.session_state.passage_index = retrieval.build_index(pages)
        session = start_qa(pages, st.session_state.passage_index)
        st.session_state.qa_session = session
    return session


def render_tutor_chat(pages: Sequence[PdfPage], context: dict[str, Any], height: int) -> None:
    st.header("Ask the tutor")
    session = qa_session(pages)
    chat = st.container(key="tutor_chat")
    messages = chat.container(height=height, border=True, key="tutor_chat_panel")
    question = chat.chat_input("Ask about your material", key="tutor_question")
    error = None
    if question:
        try:
            with st.spinner("Searching your material…"):
                ask(session, question, context)
        except LLMError as failure:
            error = str(failure)
        except ValueError:
            pass

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
        if error:
            st.error(error)
    if session.log:
        trace = session.trace
        st.caption(f"This conversation: {trace.model_calls} model calls · {trace.total_tokens} tokens")
