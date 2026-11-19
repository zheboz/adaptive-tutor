"""Generate and answer exercises for a day's assigned material in the current session."""

from hashlib import sha256

import streamlit as st

from tutor.assessment import questions, retrieval
from tutor.llm import LLMError
from tutor.materials.citations import render_sources
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyAssignment


def practice_key(document_id: str, assignment: StudyAssignment) -> str:
    # Dates can change. The document, unit and assigned reading identify the material.
    parts = [document_id, assignment.unit.unit_id, *sorted(set(assignment.source_ids))]
    return sha256("|".join(parts).encode()).hexdigest()


def prepare_daily_practice(scopes: list[tuple[str, StudyAssignment]], pages: list[PdfPage]) -> None:
    saved = st.session_state.setdefault("practice_sets", {})
    # A tuple is a completed result (empty when the reading has no supported
    # concept). A string records a failed attempt and leaves that item retryable.
    missing = [(key, assignment) for key, assignment in scopes if not isinstance(saved.get(key), tuple)]
    if not missing:
        return
    action = st.empty()
    if not action.button(
        "Generate daily practice",
        help="Prepare 1–5 questions for each learning item with evidence in the assigned reading.",
    ):
        return
    if "practice_index" not in st.session_state:
        st.session_state.practice_index = retrieval.build_index(pages)
    for key, assignment in missing:
        try:
            with st.spinner(f"Preparing practice for {assignment.unit.title}…"):
                index = st.session_state.practice_index
                passages = retrieval.retrieve(index, assignment)
                pages_in_scope = set(assignment.source_ids)
                assigned_reading = [passage for passage in index.passages if passage.source_id in pages_in_scope]
                saved[key] = questions.generate_questions(assignment, passages, assigned_reading=assigned_reading)
        except questions.InsufficientEvidence as reason:
            saved[key] = ()
            st.session_state.setdefault("practice_skips", {})[key] = str(reason)
        except questions.PracticeError:
            saved[key] = (
                f"The tutor couldn't verify a question for {assignment.unit.title} against the PDF. "
                "Select Generate daily practice to try again."
            )
        except LLMError as error:
            saved[key] = f"The practice request for {assignment.unit.title} failed. {error}"
    if all(isinstance(saved.get(key), tuple) for key, _ in missing):
        action.empty()


def _record_answer(answer_key: str, widget_key: str, options: tuple[str, ...]) -> None:
    selected = st.session_state.get(widget_key)
    if selected in options:
        st.session_state.practice_answers[answer_key] = options.index(selected)


def render_questions(scope: str) -> None:
    exercises = st.session_state.practice_sets.get(scope)
    if exercises is None:
        return
    if isinstance(exercises, str):
        st.error(exercises)
        return
    if not exercises:
        reason = st.session_state.get("practice_skips", {}).get(
            scope, "The tutor couldn't find enough evidence for a practice question on the assigned pages."
        )
        st.info(f"No practice for this item. {reason}")
        return
    answers = st.session_state.setdefault("practice_answers", {})
    origins = {"pdf": "From PDF", "adapted": "Adapted from PDF", "generated": "Generated from PDF"}
    st.subheader("Practice")
    for number, question in enumerate(exercises, start=1):
        answer_key = f"practice_{scope}_{number}"
        widget_key = f"{answer_key}_choice"
        submitted = answers.get(answer_key)
        kind = "True / False" if question.kind == "true_false" else "Multiple choice"
        st.caption(f"{kind} · {origins[question.origin]}")
        st.text(f"{number}. {question.prompt}")
        selected = st.radio(
            f"Answer for question {number}", question.options, key=widget_key,
            index=submitted, disabled=submitted is not None, label_visibility="collapsed",
        )
        if submitted is None:
            st.button(
                "Check answer", key=f"{answer_key}_submit", disabled=selected is None,
                on_click=_record_answer, args=(answer_key, widget_key, question.options),
            )
        else:
            if submitted == question.correct_index:
                st.success("Correct.")
            else:
                st.warning("Incorrect.")
                st.text(f"Correct answer: {question.options[question.correct_index]}")
            answer_sources = {"pdf": "PDF answer key", "reference": "Model reference answer",
                              "reading": "Answer from the assigned reading"}
            st.caption(answer_sources[question.answer_origin])
            st.text(question.explanation)
        render_sources(question.source_ids, answer_key)
