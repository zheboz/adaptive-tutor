"""The initial quiz between the outline and the plan.

The learner checks the topics they don't understand, takes one question per checked topic (or up to
three across the material), sees every answer with its source, and only then creates the plan.
"""

from collections.abc import Callable, Sequence
from typing import Any

import streamlit as st

from tutor.agent.quiz import Quiz, build_quiz, choose_topics, grade_quiz
from tutor.assessment import retrieval
from tutor.llm import LLMError
from tutor.materials.ingest import PdfPage
from tutor.materials.outline import Outline
from tutor.planning import StudyUnit
from tutor.ui.feedback import render_feedback
from tutor.ui.learner import learner_state, weak_topics_in_order, weak_unit_ids


QUIZ_KEYS = ("quiz", "quiz_summary")


def _data() -> dict[str, Any] | None:
    return st.session_state.get("quiz")


def started() -> bool:
    return _data() is not None


def done() -> bool:
    data = _data()
    return data is not None and data.get("results") is not None


def _build(result: Outline, units: Sequence[StudyUnit], pages: Sequence[PdfPage], topics: list[int]) -> None:
    if "practice_index" not in st.session_state:
        st.session_state.practice_index = retrieval.build_index(pages)
    count = len(topics)
    try:
        with st.spinner(f"Preparing {count} question{'s' if count != 1 else ''} from your material…"):
            quiz = build_quiz(result, units, st.session_state.practice_index, topics)
    except LLMError as error:
        st.session_state.quiz = {"topics": topics, "quiz": None, "results": None, "error": str(error)}
        return
    # With no question to answer, the quiz is finished at once and the plan controls appear.
    results = [] if not quiz.items else None
    st.session_state.quiz = {"topics": topics, "quiz": quiz, "results": results, "error": None}
    if results is not None:
        st.session_state.quiz_summary = _summary(quiz, results)


def render_start(result: Outline, pages: Sequence[PdfPage],
                 ensure_units: Callable[[Outline], Sequence[StudyUnit] | None]) -> None:
    """Sidebar step after the outline: start the quiz from the checked topics."""
    if st.session_state.get("planned_days") is not None:
        return
    st.subheader("Initial quiz")
    if done():
        st.caption(f"Done: {st.session_state.get('quiz_summary', '')}")
        return
    checked = weak_topics_in_order()
    if checked:
        st.caption(f"One question for each topic you checked ({len(checked)}), in the order you checked them.")
    else:
        st.caption("Check the topics you don't understand in the outline first. With none checked, the "
                   "quiz asks up to 3 questions from across the material.")
    if st.button("Start initial quiz", key="start_initial_quiz", type="primary", disabled=started()):
        units = ensure_units(result)
        if units is not None:
            learner_state(units).apply_report(weak_unit_ids(units))
            _build(result, units, pages, choose_topics(len(result.topics), checked))
            st.rerun()


def _summary(quiz: Quiz, results) -> str:
    if not quiz.items:
        return "no question could be prepared from the material."
    right = sum(result.correct for result in results)
    wrong = [result.item.topic_title for result in results if not result.correct]
    text = f"{right} of {len(results)} correct."
    if wrong:
        text += " More time for: " + "; ".join(wrong) + "."
    return text


def _render_skipped(quiz: Quiz) -> None:
    for _, title, reason in quiz.skipped:
        st.caption(f"No question for {title}: {reason}")


def render_quiz(result: Outline, units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    """The quiz panel beside the PDF: questions first, then every answer with its source."""
    data = _data()
    if data["error"]:
        st.error(data["error"])
        if st.button("Try again", key="quiz_retry"):
            _build(result, units, pages, data["topics"])
            st.rerun()
        return

    quiz: Quiz = data["quiz"]
    if data["results"] is None:
        st.caption(f"{len(quiz.items)} question{'s' if len(quiz.items) != 1 else ''}. Answer every question, "
                   "then submit to see the answers.")
        with st.form("initial_quiz"):
            for number, item in enumerate(quiz.items, start=1):
                st.markdown(f"**Question {number} · {item.topic_title}**")
                st.text(item.question.prompt)
                st.radio(f"Answer for question {number}", item.question.options, index=None,
                         key=f"quiz_choice_{item.id}", label_visibility="collapsed")
            submitted = st.form_submit_button("Submit answers", type="primary")
        _render_skipped(quiz)
        if submitted:
            picked = [st.session_state.get(f"quiz_choice_{item.id}") for item in quiz.items]
            if any(choice is None for choice in picked):
                st.warning("Answer every question before submitting.")
                return
            choices = [item.question.options.index(choice) for item, choice in zip(quiz.items, picked)]
            data["results"] = grade_quiz(learner_state(units), quiz, choices)
            st.session_state.quiz_summary = _summary(quiz, data["results"])
            st.rerun()
        return

    results = data["results"]
    if results:
        st.markdown(f"**{sum(r.correct for r in results)} of {len(results)} correct.**")
    else:
        st.info("No question could be prepared from the material for these topics.")
    checked = set(weak_topics_in_order())
    for number, item_result in enumerate(results, start=1):
        item = item_result.item
        with st.container(border=True, key=f"quiz_result_{item.id}"):
            render_feedback(number, item.topic_title, item.question, item_result.choice, f"quiz_feedback_{item.id}")
            if item_result.correct and item.topic_number in checked:
                st.caption("You marked this topic as not understood but answered correctly. "
                           "Uncheck it in the outline if you are confident.")
    _render_skipped(quiz)
    st.info("Next: set the number of days in the sidebar and select Create study plan. Topics you "
            "checked, and topics you answered wrong, get more of the time.")
