"""Turn a check's conclusion into plan changes, each with the reason the learner sees.

The agent proposes a conclusion; this code decides what changes in the plan, so every change can
be traced to the answers behind it. No Streamlit code belongs here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from tutor.planning import StudyDay, insert_review

from .state import LearnerState
from .tools import Diagnosis


@dataclass(frozen=True)
class PlanChange:
    trigger: str
    message: str
    evidence: tuple[str, ...] = ()


def _answers_text(state: LearnerState, unit_id: str) -> str:
    answers = state.units[unit_id].answers
    right = sum(answer.correct for answer in answers)
    return f"{right} of {len(answers)} answers correct" if answers else "no answers yet"


def after_initial_check(state: LearnerState, diagnosis: Diagnosis) -> tuple[tuple[str, ...], PlanChange]:
    """Record the check's conclusion before planning; return the units the plan should give more time.

    The check runs before the plan exists, so nothing is scheduled here: the units it finds weak
    get more time when the learner creates the plan.
    """
    if diagnosis.primary_gap:
        state.flag(diagnosis.primary_gap)
    weak = state.focus_units()
    reported = [unit_id for unit_id, evidence in state.units.items() if evidence.self_reported]

    def title(unit_id: str) -> str:
        return state.units[unit_id].unit.title

    parts = [f"{title(u)} will get more time ({_answers_text(state, u)})." for u in weak if u not in reported]
    parts += [f"{title(u)} won't get extra time ({_answers_text(state, u)})." for u in reported if u not in weak]
    if not parts:
        parts = (["Your answers support the topics you marked, so they will get more time."] if weak
                 else ["No weak unit was found, so the plan will spread the time evenly."])
    return weak, PlanChange("Initial check", " ".join(parts), diagnosis.evidence)


def after_daily_check(
    state: LearnerState, diagnosis: Diagnosis, days: Sequence[StudyDay], day: int,
) -> tuple[tuple[StudyDay, ...], PlanChange | None]:
    """Add a review day when the check calls for one, after the unit's remaining study days."""
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
    later = [d.number for d in days[day:] if any(a.unit.unit_id == unit.unit_id for a in d.assignments)]
    planned = [d.number for d in days[day:]
               if any(a.unit.unit_id == unit.unit_id and a.kind == "review" for a in d.assignments)]
    if planned:
        return days, PlanChange(trigger, f"A review of {unit.title} is already planned for day {planned[0]}, "
                                         "so no day was added.", diagnosis.evidence)

    # Review after the unit's remaining study days, so its reading and task come first.
    after = later[-1] if later else day
    updated = insert_review(days, after, unit)
    if diagnosis.next_step == "revisit_earlier":
        why = "your answers suggest today's difficulty comes from this earlier unit"
    else:
        why = "today's answers show it needs another session"
    message = (f"Added a review of {unit.title} as day {after + 1}: {why} "
               f"({_answers_text(state, unit.unit_id)}). Later days move back by one.")
    return updated, PlanChange(trigger, message, diagnosis.evidence)
