"""The tutor's checks in the plan panel: an initial check before studying, and a check after each day.

Both run the same ReAct agent with a different configuration. Each answer is submitted in the main
script run so a spinner can show while the tutor chooses the next step.
"""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from tutor.agent.bank import QuestionBank
from tutor.agent.loop import Ask, Done, advance, start_session
from tutor.agent.replan import PlanChange, after_daily_check, after_initial_check
from tutor.agent.tools import daily_config, initial_config
from tutor.llm import LLMError, tracing
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyDay, StudyUnit
from tutor.ui.learner import learner_state


CHECK_KEYS = ("check", "initial_check", "plan_changes", "completed_days", "diagnostic_bank")
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


def start_initial_check(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    state = learner_state(units)
    first = state.focus_units() or tuple(unit.unit_id for unit in units)
    _start("initial", units, pages, first)
    st.session_state.initial_check = "running"


def skip_initial_check() -> None:
    st.session_state.initial_check = "skipped"


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
    """Change the plan once, when the check concludes."""
    if check["applied"]:
        return
    state = check["session"].state
    diagnosis = check["step"].diagnosis
    if check["mode"] == "initial":
        weak, days, change = after_initial_check(
            state, diagnosis, st.session_state.get("planned_weak", ()), st.session_state.planned_days,
        )
        st.session_state.planned_weak = weak
        st.session_state.study_plan = days
        st.session_state.initial_check = "done"
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


def render_initial_offer(units: Sequence[StudyUnit], pages: Sequence[PdfPage]) -> None:
    if st.session_state.get("initial_check") or st.session_state.get("check"):
        return
    with st.container(border=True, key="initial_check_offer"):
        st.markdown("**Initial check**")
        st.caption("Before you start, answer up to 5 questions so the tutor can confirm which topics "
                   "need more time. The plan is adjusted to your answers.")
        with st.container(horizontal=True):
            st.button("Start initial check", key="start_initial_check", type="primary",
                      on_click=start_initial_check, args=(units, pages))
            st.button("Skip", key="skip_initial_check", on_click=skip_initial_check)


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


def render_check(units: Sequence[StudyUnit]) -> bool:
    """Show the active check. Returns True while a check occupies the plan panel."""
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
    if isinstance(step, Ask):
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
    if check["change"] is not None:
        st.info(f"Plan change · {check['change'].message}")
    elif check["mode"] == "daily":
        st.caption("The plan is unchanged.")
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
