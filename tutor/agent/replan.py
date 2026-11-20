"""Turn a check's conclusion into plan changes, each with the reason the learner sees.

The agent proposes a conclusion; this code decides what changes in the plan, so every change can
be traced to the answers behind it. No Streamlit code belongs here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tutor.planning import StudyDay, insert_review

from .state import LearnerState
from .tools import Diagnosis


# A check adds a review day only when at least this many of its own answers are wrong, and they
# outnumber the right ones: the same standard as a likely gap (2 of 2, 2 of 3, 3 of 3).
REVIEW_MIN_WRONG = 2


@dataclass(frozen=True)
class PlanChange:
    trigger: str
    message: str
    evidence: tuple[str, ...] = ()
    # False when the message explains why the plan was left as it was.
    changed: bool = True


def _answers_text(state: LearnerState, unit_id: str) -> str:
    answers = state.units[unit_id].answers
    right = sum(answer.correct for answer in answers)
    return f"{right} of {len(answers)} answers correct" if answers else "no answers yet"


def after_daily_check(
    state: LearnerState, diagnosis: Diagnosis, days: Sequence[StudyDay], day: int, asked: Sequence[str] = (),
) -> tuple[tuple[StudyDay, ...], PlanChange | None]:
    """Add a review day at the end of the plan when the check calls for one.

    `asked` are the questions of this check. Unless at least REVIEW_MIN_WRONG of them are wrong and
    the wrong ones outnumber the right ones, no review is added, whatever the tutor concluded.
    """
    days = tuple(days)
    if diagnosis.primary_gap:
        state.flag(diagnosis.primary_gap)
    if diagnosis.next_step == "continue":
        return days, None

    today = [a.unit for a in days[day - 1].assignments]
    if diagnosis.primary_gap:
        unit = state.units[diagnosis.primary_gap].unit
    else:
        # No unit named: review the weakest unit studied today.
        rank = {"gap": 0, "uncertain": 1, "suspected": 2, "untested": 3, "mastered": 4}
        unit = min(today, key=lambda u: rank[state.status(u.unit_id)])
    trigger = f"Day {day} check"
    answers = [state.answer(question_id) for question_id in asked]
    wrong = sum(answer is not None and not answer.correct for answer in answers)
    right = sum(answer is not None and answer.correct for answer in answers)
    if wrong < REVIEW_MIN_WRONG or wrong <= right:
        return days, PlanChange(
            trigger, f"No review was added: {wrong} of {len(asked)} answers in this check were wrong. A "
                     f"review is added when at least {REVIEW_MIN_WRONG} answers are wrong and they outnumber "
                     "the right ones.",
            diagnosis.evidence, changed=False,
        )
    planned = [d.number for d in days[day:]
               if any(a.unit.unit_id == unit.unit_id and a.kind == "review" for a in d.assignments)]
    if planned:
        return days, PlanChange(trigger, f"A review of {unit.title} is already planned for day {planned[0]}, "
                                         "so no day was added.", diagnosis.evidence, changed=False)

    updated = insert_review(days, len(days), unit)
    if diagnosis.next_step == "revisit_earlier":
        why = "your answers suggest today's difficulty comes from this earlier unit"
    else:
        why = "today's answers show it needs another session"
    message = (f"Added a review of {unit.title} as day {len(updated)}, at the end of the plan: {why} "
               f"({_answers_text(state, unit.unit_id)}).")
    return updated, PlanChange(trigger, message, diagnosis.evidence)
