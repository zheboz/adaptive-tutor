"""Feedback on one answered question: right or wrong, the correct answer, and where the material says so."""

from html import escape

import streamlit as st

from tutor.assessment.questions import Question
from tutor.ui.citations import render_sources


def render_feedback(number: int, title: str, question: Question, choice: int, key: str) -> None:
    correct = choice == question.correct_index
    (st.success if correct else st.warning)(f"Question {number} · {title}: {'Correct' if correct else 'Not quite'}.")
    st.text(question.prompt)
    rows = [("right" if correct else "wrong", "Your answer", question.options[choice])]
    if not correct:
        rows.append(("right", "Correct answer", question.options[question.correct_index]))
    st.html(_answers(rows))
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


def _answers(rows: list[tuple[str, str, str]]) -> str:
    """The learner's answer and, when it was wrong, the correct one, each marked so it stands out."""
    marks = {"right": "✓", "wrong": "✗"}
    return '<div class="answer-rows">' + "".join(
        f'<div class="answer-row {kind}"><span class="answer-mark" aria-hidden="true">{marks[kind]}</span>'
        f'<span class="answer-label">{label}</span><span class="answer-value">{escape(option)}</span></div>'
        for kind, label, option in rows
    ) + "</div>"
