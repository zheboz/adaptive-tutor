"""Turn a check's conclusion into plan changes, each with the reason the learner sees.

The agent proposes a conclusion; this code decides what changes in the plan, so every change can
be traced to the answers behind it. No Streamlit code belongs here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tutor.planning import StudyDay, insert_review

from .state import LearnerState
from .tools import SETTLING_ANSWERS, Diagnosis, UnitTally, tally


@dataclass(frozen=True)
class PlanChange:
    trigger: str
    message: str
    evidence: tuple[str, ...] = ()
    # False when the message explains why the plan was left as it was.
    changed: bool = True


def _answers_text(state: LearnerState, unit_id: str, asked: Sequence[str]) -> str:
    unit_tally = tally(state, asked).get(unit_id)
    if unit_tally is not None:
        return f"{unit_tally.right} of {unit_tally.answered} correct in this check"
    answers = state.units[unit_id].answers
    right = sum(answer.correct for answer in answers)
    return f"{right} of {len(answers)} answers correct" if answers else "no answers yet"


def after_daily_check(
    state: LearnerState, diagnosis: Diagnosis, days: Sequence[StudyDay], day: int, asked: Sequence[str] = (),
) -> tuple[tuple[StudyDay, ...], PlanChange | None]:
    """Add review days at the end of the plan when the check calls for them.

    `asked` are the questions of this check. A review is added for each unit studied today that
    ended this check as a gap (at least 2 wrong answers that outnumber the right ones), and for the
    earlier unit the tutor named with revisit_earlier. Without a gap today, nothing is added,
    whatever the tutor concluded.
    """
    days = tuple(days)
    if diagnosis.primary_gap:
        state.flag(diagnosis.primary_gap)
    trigger = f"Day {day} check"
    today = tuple(dict.fromkeys(a.unit.unit_id for a in days[day - 1].assignments))
    tallies = tally(state, asked)
    gaps = [unit_id for unit_id in today if tallies.get(unit_id, UnitTally()).verdict() == "gap"]
    if not gaps:
        if diagnosis.next_step == "continue":
            return days, None
        return days, PlanChange(
            trigger, "No review was added: no unit studied today ended this check as a gap. A review is "
                     f"added when a unit has at least {SETTLING_ANSWERS} wrong answers in a check and they "
                     "outnumber the right ones.",
            diagnosis.evidence, changed=False,
        )

    earlier = diagnosis.primary_gap if (diagnosis.next_step == "revisit_earlier"
                                        and diagnosis.primary_gap not in (None, *today)) else None
    added, skipped = [], []
    updated = days
    for unit_id in ([earlier] if earlier else []) + gaps:
        unit = state.units[unit_id].unit
        planned = [d.number for d in updated[day:]
                   if any(a.unit.unit_id == unit_id and a.kind == "review" for a in d.assignments)]
        if planned:
            skipped.append(f"a review of {unit.title} is already planned for day {planned[0]}")
            continue
        updated = insert_review(updated, len(updated), unit)
        why = ("your answers suggest today's difficulty comes from this earlier unit" if unit_id == earlier
               else "today's answers show it needs another session")
        added.append(f"{unit.title} as day {len(updated)} ({why}; {_answers_text(state, unit_id, asked)})")
    if not added:
        return days, PlanChange(trigger, "No day was added: " + "; ".join(skipped) + ".",
                                diagnosis.evidence, changed=False)
    message = "Added a review of " + "; and of ".join(added) + ", at the end of the plan."
    if skipped:
        message += " Not added again: " + "; ".join(skipped) + "."
    return updated, PlanChange(trigger, message, diagnosis.evidence)
