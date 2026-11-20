"""Feedback on one answered question: right or wrong, the correct answer, and where the material says so."""

import streamlit as st

from tutor.assessment.questions import Question
from tutor.ui.citations import render_sources


def render_feedback(number: int, title: str, question: Question, choice: int, key: str) -> None:
    correct = choice == question.correct_index
    (st.success if correct else st.warning)(f"Question {number} · {title}: {'Correct' if correct else 'Not quite'}.")
    st.text(question.prompt)
    if correct:
        st.text(f"Your answer: {question.options[choice]}")
    else:
        st.text(f"Your answer: {question.options[choice]}\nCorrect answer: {question.options[question.correct_index]}")
    if question.explanation and question.explanation != question.evidence:
        st.text(question.explanation)
    page = question.evidence_source_id
    evidence = " ".join(question.evidence.split())
    if evidence and page:
        st.caption(f"In your material, page {page[1:]}: “{evidence}”")
    elif page:
        st.caption(f"The answer is printed on page {page[1:]} of your material.")
    if question.answer_origin == "pdf" and evidence:
        st.caption("The correct answer is the one printed with this exercise in your material.")
    render_sources(list(dict.fromkeys([page] if page else question.source_ids)), key)
