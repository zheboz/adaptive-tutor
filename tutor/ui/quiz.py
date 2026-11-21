"""The quick check, the third setup step: one question at a time, each answered at once.

There is one question per topic the learner checked, in the order they checked them, or up to three
across the material when nothing is checked. Each answer shows whether it was right, the correct
answer and its source before the next question. The answers are recorded when the last one is in,
and the plan then gives more time to the topics answered wrong. The check can be skipped.
"""

from collections.abc import Sequence
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
from tutor.ui.units import ensure_units


QUIZ_KEYS = ("quiz", "quiz_summary")


def _data() -> dict[str, Any] | None:
    return st.session_state.get("quiz")


def started() -> bool:
    return _data() is not None


def done() -> bool:
    data = _data()
    return data is not None and data.get("results") is not None


def skipped() -> bool:
    data = _data()
    return data is not None and bool(data.get("skipped"))


def _build(result: Outline, units: Sequence[StudyUnit], pages: Sequence[PdfPage], topics: list[int]) -> None:
    if "passage_index" not in st.session_state:
        st.session_state.passage_index = retrieval.build_index(pages)
    data = {"topics": topics, "quiz": None, "answers": [], "revealed": False, "results": None, "error": None}
    count = len(topics)
    try:
        with st.spinner(f"Preparing {count} question{'s' if count != 1 else ''} from your material…"):
            data["quiz"] = build_quiz(result, units, st.session_state.passage_index, topics)
    except LLMError as error:
        data["error"] = str(error)
    else:
        # With no question to answer, the check is finished at once.
        if not data["quiz"].items:
            data["results"] = []
            st.session_state.quiz_summary = _summary(data["quiz"], [])
    st.session_state.quiz = data


def _ready_units(result: Outline) -> Sequence[StudyUnit] | None:
    """The units, with the checked topics recorded as the learner's report; None after an error."""
    units = ensure_units(result)
    if units is not None:
        learner_state(units).apply_report(weak_unit_ids(units))
    return units


def start(result: Outline, pages: Sequence[PdfPage]) -> bool:
    """Prepare the questions for the checked topics. False when the units could not be planned."""
    units = _ready_units(result)
    if units is None:
        return False
    _build(result, units, pages, choose_topics(len(result.topics), weak_topics_in_order()))
    return True


def skip(result: Outline) -> bool:
    """Go straight to the plan. Checked topics still get more time; nothing is graded."""
    if _ready_units(result) is None:
        return False
    st.session_state.quiz = {"topics": [], "quiz": Quiz(items=()), "answers": [], "revealed": False,
                             "results": [], "error": None, "skipped": True}
    st.session_state.quiz_summary = "skipped."
    return True


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


def _answer(data: dict[str, Any], choice: int) -> None:
    data["answers"].append(choice)
    data["revealed"] = True


def _next(data: dict[str, Any], units: Sequence[StudyUnit]) -> None:
    data["revealed"] = False
    quiz: Quiz = data["quiz"]
    if len(data["answers"]) == len(quiz.items):
        data["results"] = grade_quiz(learner_state(units), quiz, data["answers"])
        st.session_state.quiz_summary = _summary(quiz, data["results"])


def render_quiz(result: Outline, units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    """The current question, the feedback on the last answer, or every answer once the check is done."""
    data = _data()
    if data["error"]:
        st.error(data["error"])
        if st.button("Try again", key="quiz_retry", type="primary"):
            _build(result, units, pages, data["topics"])
            st.rerun()
        return
    if data["results"] is not None:
        _render_results(data)
        return

    quiz: Quiz = data["quiz"]
    total = len(quiz.items)
    answered = len(data["answers"])
    number = answered if data["revealed"] else answered + 1
    item = quiz.items[number - 1]
    st.progress(answered / total, text=f"Question {number} of {total}")
    if data["revealed"]:
        with st.container(border=True, key=f"quiz_feedback_{item.id}"):
            render_feedback(number, item.topic_title, item.question, data["answers"][-1], f"quiz_feedback_{item.id}")
            if item.question.correct_index == data["answers"][-1] and item.topic_number in weak_topics_in_order():
                st.caption("You marked this topic as not understood but answered correctly. Uncheck it in "
                           "Topics if you are confident.")
        last = answered == total
        st.button("See my results" if last else "Next question", key="quiz_next", type="primary",
                  on_click=_next, args=(data, units))
        return

    with st.container(border=True, key=f"quiz_question_{item.id}"):
        st.markdown(f"**{item.topic_title}**")
        st.text(item.question.prompt)
        choice = st.radio(f"Answer for question {number}", item.question.options, index=None,
                          key=f"quiz_choice_{item.id}", label_visibility="collapsed")
    if st.button("Check answer", key="quiz_submit", type="primary", disabled=choice is None):
        _answer(data, item.question.options.index(choice))
        st.rerun()
    if answered == 0:
        _render_skipped(quiz)


def _render_results(data: dict[str, Any]) -> None:
    results = data["results"]
    if data.get("skipped"):
        st.info("You skipped the quick check. The plan gives more time to the topics you checked.")
        return
    if not results:
        st.info("No question could be prepared from the material for these topics.")
        _render_skipped(data["quiz"])
        return
    right = sum(r.correct for r in results)
    st.markdown(f"**{right} of {len(results)} correct.**")
    wrong = [r.item.topic_title for r in results if not r.correct]
    if wrong:
        st.caption("The plan gives more time to: " + "; ".join(wrong) + ".")
    with st.expander(f"Your answers ({len(results)})"):
        for number, item_result in enumerate(results, start=1):
            item = item_result.item
            render_feedback(number, item.topic_title, item.question, item_result.choice, f"quiz_result_{item.id}")
    _render_skipped(data["quiz"])


def render_quiz_review() -> None:
    """The quick check's answers again, for the Progress page."""
    data = _data()
    if not done() or not data["results"]:
        return
    results = data["results"]
    with st.expander(f"Quick check: {sum(r.correct for r in results)} of {len(results)} correct"):
        for number, item_result in enumerate(results, start=1):
            item = item_result.item
            render_feedback(number, item.topic_title, item.question, item_result.choice, f"quiz_review_{item.id}")
