"""The tutor's checks: an initial check after the outline and before the plan, and a check after each day.

Both run the same ReAct agent with a different configuration. Each answer is submitted in the main
script run so a spinner can show while the tutor chooses the next step.
"""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from tutor.agent.bank import DiagnosticQuestion, QuestionBank
from tutor.agent.loop import Ask, Done, advance, start_session
from tutor.agent.replan import PlanChange, after_daily_check, after_initial_check
from tutor.agent.tools import daily_config, initial_config
from tutor.llm import LLMError, tracing
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyDay, StudyUnit
from tutor.ui.citations import render_sources
from tutor.ui.learner import learner_state


CHECK_KEYS = ("check", "initial_check", "initial_check_summary", "plan_changes", "completed_days",
              "diagnostic_bank")
# The first units a check is likely to ask about are prepared in the background.
PREFETCH_UNITS = 3


def reset_progress() -> None:
    """Forget checks and plan changes when the plan is created again."""
    for key in ("check", "plan_changes", "completed_days"):
        st.session_state.pop(key, None)


def question_bank(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> QuestionBank:
    bank = st.session_state.get("diagnostic_bank")
    if bank is None or bank.unit_ids != tuple(unit.unit_id for unit in units):
        bank = QuestionBank(units, pages)
        st.session_state.diagnostic_bank = bank
    return bank


def completed_days() -> set[int]:
    return st.session_state.setdefault("completed_days", set())


def plan_changes() -> list[PlanChange]:
    return st.session_state.setdefault("plan_changes", [])


def _start(mode: str, units: Sequence[StudyUnit], pages: Sequence[PdfPage], first: Sequence[str],
           day: int | None = None, today: Sequence[str] = ()) -> None:
    state = learner_state(units)
    config = initial_config(units) if mode == "initial" else daily_config(units, today, day)
    bank = question_bank(units, pages)
    session = start_session(units, state, bank, config)
    with tracing(session.trace):
        bank.prefetch(list(first)[:PREFETCH_UNITS])
    st.session_state.check = {"mode": mode, "day": day, "session": session, "step": None,
                              "error": None, "applied": False, "change": None}


def active() -> bool:
    return st.session_state.get("check") is not None


def initial_running() -> bool:
    check = st.session_state.get("check")
    return check is not None and check["mode"] == "initial"


def start_initial_check(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    """Start from the weak topics checked on the outline; call after recording them."""
    state = learner_state(units)
    first = state.focus_units() or tuple(unit.unit_id for unit in units)
    _start("initial", units, pages, first)
    st.session_state.initial_check = "running"


def start_daily_check(units: Sequence[StudyUnit], pages: Sequence[PdfPage], days: Sequence[StudyDay], day: int) -> None:
    today = [assignment.unit.unit_id for assignment in days[day - 1].assignments]
    _start("daily", units, pages, today, day, today)


def end_check() -> None:
    check = st.session_state.pop("check", None)
    if check and check["mode"] == "initial" and st.session_state.get("initial_check") == "running":
        st.session_state.initial_check = "skipped"


def _advance(check: dict[str, Any], answer: int | None) -> None:
    try:
        with st.spinner("The tutor is choosing the next step…"):
            check["step"] = advance(check["session"], answer)
    except LLMError as error:
        check["error"] = str(error)


def _apply(check: dict[str, Any]) -> None:
    """Record the conclusion once: the initial check informs the plan to come; a daily check changes it."""
    if check["applied"]:
        return
    state = check["session"].state
    diagnosis = check["step"].diagnosis
    if check["mode"] == "initial":
        # No plan exists yet. The answers stay in the learner state, so the plan created next
        # gives the units they show to be weak more time.
        _, change = after_initial_check(state, diagnosis)
        st.session_state.initial_check = "done"
        st.session_state.initial_check_summary = change.message
    else:
        day = check["day"]
        before = st.session_state.study_plan
        days, change = after_daily_check(state, diagnosis, before, day)
        st.session_state.study_plan = days
        done = completed_days()
        if len(days) > len(before):
            # Days after the inserted review move back by one.
            shifted = {number + 1 if number > day else number for number in done}
            done.clear()
            done.update(shifted)
        done.add(day)
        if change is not None:
            plan_changes().append(change)
    check["change"] = change
    check["applied"] = True


def render_daily_check_button(units: Sequence[StudyUnit], pages: Sequence[PdfPage],
                              days: Sequence[StudyDay], day: int) -> None:
    st.divider()
    checked = day in completed_days()
    st.button("Check my understanding" if not checked else "Check again", key=f"daily_check_{day}",
              on_click=start_daily_check, args=(units, pages, days, day))
    st.caption("The tutor looks at today's practice answers and may ask up to 3 more questions, "
               "then adjusts the rest of the plan.")


def _evidence_line(check: dict[str, Any]) -> str:
    state = check["session"].state
    parts = []
    for question_id in check["step"].diagnosis.evidence:
        answer = state.answer(question_id)
        if answer is not None:
            title = state.units[answer.unit_id].unit.title
            parts.append(f"{title}: {'correct' if answer.correct else 'wrong'}")
    return "; ".join(parts)


def _render_feedback(number: int, item: DiagnosticQuestion, choice: int, title: str) -> None:
    """Right or wrong, the correct answer, and where the material says so."""
    question = item.question
    correct = choice == question.correct_index
    verdict = "Correct" if correct else "Not quite"
    (st.success if correct else st.warning)(f"Question {number} · {title}: {verdict}.")
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
    pages = list(dict.fromkeys([page] if page else question.source_ids))
    render_sources(pages, f"check_feedback_{item.id}")


def render_check(units: Sequence[StudyUnit]) -> bool:
    """Show the active check. Returns True while a check occupies the panel."""
    check = st.session_state.get("check")
    if not check:
        return False
    session = check["session"]
    titles = {unit.unit_id: unit.title for unit in units}
    st.subheader("Initial check" if check["mode"] == "initial" else f"Day {check['day']} check")

    if check["step"] is None and not check["error"]:
        _advance(check, None)
    if check["error"]:
        st.error(check["error"])
        with st.container(horizontal=True):
            if st.button("Try again", key="check_retry"):
                check["error"] = None
                check["step"] = None
                st.rerun()
            st.button("Stop check", key="check_stop", on_click=end_check)
        return True

    step = check["step"]
    answered = check.setdefault("answered", [])
    if isinstance(step, Ask):
        if answered:
            # Feedback on the previous answer, before the next question.
            item, choice = answered[-1]
            with st.container(border=True, key=f"check_last_feedback_{item.id}"):
                _render_feedback(len(answered), item, choice, titles[item.unit_id])
        question = step.question.question
        st.caption(f"Question {step.number} of up to {session.config.max_questions} · "
                   f"{titles[step.question.unit_id]}")
        st.caption(f"Why this question: {step.reason}")
        st.text(question.prompt)
        with st.form(f"check_form_{step.question.id}"):
            choice = st.radio("Your answer", question.options, index=None,
                              key=f"check_choice_{step.question.id}", label_visibility="collapsed")
            submitted = st.form_submit_button("Submit answer")
        if submitted and choice is not None:
            answered.append((step.question, question.options.index(choice)))
            _advance(check, question.options.index(choice))
            st.rerun()
        st.button("Stop check", key="check_stop", on_click=end_check)
        return True

    assert isinstance(step, Done)
    _apply(check)
    diagnosis = step.diagnosis
    if diagnosis.primary_gap is None:
        headline = "No gap found." if diagnosis.status == "confirmed" else "No clear gap yet."
    elif diagnosis.status == "confirmed":
        headline = f"Likely gap: {titles[diagnosis.primary_gap]}."
    else:
        headline = f"Possible gap: {titles[diagnosis.primary_gap]} (needs more evidence)."
    st.markdown(f"**{headline}**")
    st.write(diagnosis.summary)
    evidence = _evidence_line(check)
    if evidence:
        st.caption(f"Based on: {evidence}")
    if check["mode"] == "initial":
        st.info(f"For your plan · {check['change'].message}")
        st.caption("Set the number of days and select Create study plan to use these results.")
    elif check["change"] is not None:
        st.info(f"Plan change · {check['change'].message}")
    elif check["mode"] == "daily":
        st.caption("The plan is unchanged.")
    if answered:
        with st.expander(f"Your answers in this check ({len(answered)})", expanded=True):
            for number, (item, choice) in enumerate(answered, start=1):
                _render_feedback(number, item, choice, titles[item.unit_id])
    trace = session.trace
    st.caption(f"This check: {trace.model_calls} model calls · {trace.total_tokens} tokens")
    st.button("Continue", key="check_close", type="primary", on_click=end_check)
    return True


def render_plan_changes() -> None:
    changes = plan_changes()
    if not changes:
        return
    with st.expander(f"Plan changes ({len(changes)})"):
        for change in reversed(changes):
            st.caption(f"{change.trigger} · {change.message}")
