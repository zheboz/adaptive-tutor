"""The daily check in the plan panel: after studying a day, the learner asks to be checked.

Questions are prepared from that day's pages only. When none can be made, the panel says why;
otherwise the ReAct agent asks up to three of them and the rest of the plan is adjusted. Each answer
is submitted in the main script run so a spinner can show while the tutor chooses the next step,
and feedback on it appears before the next question.
"""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from tutor.agent.bank import QuestionBank
from tutor.agent.loop import Ask, Done, advance, start_session
from tutor.agent.replan import PlanChange, after_daily_check
from tutor.agent.tools import daily_config
from tutor.llm import LLMError, Trace, tracing
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyDay, StudyUnit
from tutor.ui.feedback import render_feedback
from tutor.ui.learner import learner_state


CHECK_KEYS = ("check", "plan_changes", "completed_days", "day_banks")


def reset_progress() -> None:
    """Forget checks and plan changes when the plan is created again."""
    for key in ("check", "plan_changes", "completed_days"):
        st.session_state.pop(key, None)


def day_bank(units: Sequence[StudyUnit], pages: Sequence[PdfPage], day: StudyDay) -> QuestionBank:
    """One bank per study day's material, so checking the day again offers questions not yet asked."""
    key = tuple((a.unit.unit_id, a.kind, a.source_ids, a.round) for a in day.assignments)
    banks = st.session_state.setdefault("day_banks", {})
    if key not in banks or banks[key].unit_ids != tuple(unit.unit_id for unit in units):
        prefix = "-".join(f"{a.kind}{a.round}-{'.'.join(a.source_ids)}" for a in day.assignments)
        banks[key] = QuestionBank(units, pages, day.assignments, prefix=f"{prefix}:")
    return banks[key]


def completed_days() -> set[int]:
    return st.session_state.setdefault("completed_days", set())


def plan_changes() -> list[PlanChange]:
    return st.session_state.setdefault("plan_changes", [])


def start_daily_check(day: int) -> None:
    """Questions are prepared when the panel next renders, where a spinner can show."""
    st.session_state.check = {"day": day, "session": None, "step": None, "error": None,
                              "applied": False, "change": None, "answered": [], "empty": None}


def _prepare(check: dict[str, Any], units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    """Build today's questions; start the agent only on units that have some."""
    days = st.session_state.study_plan
    day = days[check["day"] - 1]
    today = list(dict.fromkeys(assignment.unit.unit_id for assignment in day.assignments))
    bank = day_bank(units, pages, day)
    state = learner_state(units)
    used = {answer.question_id for answer in state.answers()}
    trace = Trace()
    try:
        with st.spinner("Preparing questions from today's material…"), tracing(trace):
            bank.prepare(today)
    except LLMError as error:
        check["error"] = str(error)
        return
    askable = [unit_id for unit_id in today if bank.remaining(unit_id, used)]
    if not askable:
        titles = {unit.unit_id: unit.title for unit in units}

        def reason(unit_id: str) -> str:
            if bank.remaining(unit_id, ()):
                return "Every question from today's pages has been asked already."
            return bank.problems.get(unit_id) or "The pages have no point the tutor could ask about."

        check["empty"] = [(titles[unit_id], reason(unit_id)) for unit_id in today]
        return
    session = start_session(units, state, bank, daily_config(units, today, check["day"], askable))
    session.trace.spans.extend(trace.spans)
    check["session"] = session


def end_check() -> None:
    st.session_state.pop("check", None)


def _advance(check: dict[str, Any], answer: int | None) -> None:
    try:
        with st.spinner("The tutor is choosing the next step…"):
            check["step"] = advance(check["session"], answer)
    except LLMError as error:
        check["error"] = str(error)


def _apply(check: dict[str, Any]) -> None:
    """Change the plan once, when the check concludes."""
    if check["applied"]:
        return
    day = check["day"]
    session = check["session"]
    days, change = after_daily_check(session.state, check["step"].diagnosis, st.session_state.study_plan, day,
                                     session.asked)
    # A review is added at the end, so no day moves.
    st.session_state.study_plan = days
    completed_days().add(day)
    if change is not None and change.changed:
        plan_changes().append(change)
    check["change"] = change
    check["applied"] = True


def render_daily_check_button(day: int) -> None:
    st.divider()
    checked = day in completed_days()
    st.button("Check my understanding" if not checked else "Check again", key=f"daily_check_{day}",
              on_click=start_daily_check, args=(day,))
    st.caption("When you have studied today's material, the tutor asks up to 3 questions from today's "
               "pages, shows the answers with their sources, and adjusts the rest of the plan.")


def _evidence_line(check: dict[str, Any]) -> str:
    state = check["session"].state
    parts = []
    for question_id in check["step"].diagnosis.evidence:
        answer = state.answer(question_id)
        if answer is not None:
            title = state.units[answer.unit_id].unit.title
            parts.append(f"{title}: {'correct' if answer.correct else 'wrong'}")
    return "; ".join(parts)


def render_check(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> bool:
    """Show the active check. Returns True while a check occupies the plan panel."""
    check = st.session_state.get("check")
    if not check:
        return False
    titles = {unit.unit_id: unit.title for unit in units}
    st.subheader(f"Day {check['day']} check")

    if check["session"] is None and check["empty"] is None and not check["error"]:
        _prepare(check, units, pages)
    if check["empty"] is not None:
        st.info("There is nothing to check from today's material, so the plan is unchanged.")
        for title, reason in check["empty"]:
            st.caption(f"{title}: {reason}")
        st.button("Continue", key="check_close", type="primary", on_click=end_check)
        return True
    if check["session"] is not None and check["step"] is None and not check["error"]:
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
    session = check["session"]

    step = check["step"]
    answered = check["answered"]
    if isinstance(step, Ask):
        if answered:
            # Feedback on the previous answer, before the next question.
            item, choice = answered[-1]
            with st.container(border=True, key=f"check_last_feedback_{item.id}"):
                render_feedback(len(answered), titles[item.unit_id], item.question, choice,
                                f"check_feedback_{item.id}")
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
    change = check["change"]
    if change is not None and change.changed:
        st.info(f"Plan change · {change.message}")
    elif change is not None:
        st.caption(change.message)
    else:
        st.caption("The plan is unchanged.")
    if answered:
        with st.expander(f"Your answers in this check ({len(answered)})", expanded=True):
            for number, (item, choice) in enumerate(answered, start=1):
                render_feedback(number, titles[item.unit_id], item.question, choice, f"check_feedback_{item.id}")
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
