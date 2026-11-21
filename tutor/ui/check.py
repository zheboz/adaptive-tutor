"""The daily check: after studying a day, the learner asks to be checked. The check takes the whole
width of the Today page and hides the PDF; the pages behind each answer open in a window.

Questions are prepared from that day's pages only, in the background as soon as the day is opened.
When none can be made, the panel says why; otherwise the ReAct agent asks up to eight of them, at most
three per unit, until each unit is settled, and the rest of the plan is adjusted. Each answer
is submitted in the main script run so a spinner can show while the tutor chooses the next step,
and feedback on it appears before the next question.
"""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from tutor.agent.bank import QuestionBank
from tutor.agent.loop import Ask, Done, advance, start_session
from tutor.agent.replan import PlanChange, after_daily_check
from tutor.agent.tools import UnitTally, daily_config, tally
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


def prefetch_questions(units: Sequence[StudyUnit], pages: Sequence[PdfPage], day: int) -> None:
    """Start making the day's check questions in the background, so the check need not wait."""
    plan = st.session_state.study_plan
    bank = day_bank(units, pages, plan[day - 1])
    bank.prefetch(dict.fromkeys(assignment.unit.unit_id for assignment in plan[day - 1].assignments))


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
            if unit_id in bank.retryable:
                return f"No question passed verification this time ({bank.problems[unit_id]})"
            return bank.problems.get(unit_id) or "The pages have no point the tutor could ask about."

        check["empty"] = [(titles[unit_id], reason(unit_id)) for unit_id in today]
        check["retry"] = [unit_id for unit_id in today if unit_id in bank.retryable]
        return
    session = start_session(units, state, bank, daily_config(units, today, check["day"], askable))
    session.trace.spans.extend(trace.spans)
    check["session"] = session


def active() -> bool:
    return bool(st.session_state.get("check"))


def end_check() -> None:
    st.session_state.pop("check", None)


def _finish_without_questions(day: int) -> None:
    """Nothing could be asked: the day still counts as checked."""
    completed_days().add(day)
    end_check()


def _retry_preparing(units: Sequence[StudyUnit], pages: Sequence[PdfPage], unit_ids: list[str]) -> None:
    check = st.session_state.check
    days = st.session_state.study_plan
    day_bank(units, pages, days[check["day"] - 1]).forget(unit_ids)
    check["empty"] = None
    check["retry"] = []


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
    st.caption("When you have studied today's material, the tutor asks up to 8 questions from today's "
               "pages, at most 3 per unit, until it is clear whether you understood each unit. It shows "
               "the answers with their sources and adds a review at the end of the plan for any unit "
               "you have not understood yet.")


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
    """Show the active check. Returns True while a check is open."""
    check = st.session_state.get("check")
    if not check:
        return False
    titles = {unit.unit_id: unit.title for unit in units}
    st.subheader(f"Day {check['day']} check", anchor=False)
    st.caption("Answer from what you learned: the PDF is hidden until the check ends.")

    if check["session"] is None and check["empty"] is None and not check["error"]:
        _prepare(check, units, pages)
    if check["empty"] is not None:
        retry = check.get("retry") or []
        if retry:
            st.warning("No question could be prepared from today's material this time. You can try again, "
                       "or continue: the day is marked as checked and the plan is unchanged.")
        else:
            st.info("There is nothing to check from today's material. When you continue, the day is marked "
                    "as checked and the plan is unchanged.")
        for title, reason in check["empty"]:
            st.caption(f"{title}: {reason}")
        with st.container(horizontal=True):
            st.button("Continue", key="check_close", type="primary", on_click=_finish_without_questions,
                      args=(check["day"],))
            if retry:
                st.button("Try again", key="check_prepare_again", on_click=_retry_preparing,
                          args=(units, pages, retry))
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
    tallies = tally(session.state, session.asked)
    verdicts = {"understood": "understood", "gap": "needs review", "mixed": "mixed answers",
                "open": "not settled"}
    for unit_id in session.config.today:
        unit_tally = tallies.get(unit_id, UnitTally())
        if unit_tally.answered:
            st.caption(f"{titles[unit_id]}: {verdicts[unit_tally.verdict(session.config.per_unit)]} "
                       f"({unit_tally.right} of {unit_tally.answered} correct)")
        else:
            st.caption(f"{titles[unit_id]}: not asked in this check")
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
