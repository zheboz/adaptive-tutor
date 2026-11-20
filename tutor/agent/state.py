"""Record which units the learner marked weak and how they answered, and derive each unit's status.

Statuses come only from scored answers and the learner's own report, never from the model:

- untested:  no answers and no report
- suspected: the learner marked the unit weak, but no answer has checked it
- uncertain: one answer, mixed answers, or correct answers that could be guesses
- mastered:  no wrong answers and at least two correct multiple-choice answers
- gap:       at least two wrong answers, outnumbering the correct ones
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from tutor.planning import StudyUnit


Status = Literal["untested", "suspected", "uncertain", "mastered", "gap"]
AnswerSource = Literal["quiz", "diagnosis"]


@dataclass(frozen=True)
class Answer:
    question_id: str
    unit_id: str
    kind: str
    correct: bool
    source: AnswerSource
    prompt: str = ""


@dataclass
class UnitEvidence:
    unit: StudyUnit
    self_reported: bool = False
    answers: list[Answer] = field(default_factory=list)

    @property
    def status(self) -> Status:
        if not self.answers:
            return "suspected" if self.self_reported else "untested"
        if len(self.answers) == 1:
            # A single answer can be a slip or a lucky guess.
            return "uncertain"
        wrong = sum(not answer.correct for answer in self.answers)
        right = len(self.answers) - wrong
        if wrong == 0:
            # True/false answers are right half the time by chance.
            strong = sum(answer.kind != "true_false" for answer in self.answers)
            return "mastered" if strong >= 2 else "uncertain"
        if wrong >= 2 and wrong > right:
            return "gap"
        return "uncertain"


class LearnerState:
    def __init__(self, units: Sequence[StudyUnit]):
        self.units = {unit.unit_id: UnitEvidence(unit) for unit in units}
        self.flagged: set[str] = set()

    @property
    def unit_ids(self) -> tuple[str, ...]:
        return tuple(self.units)

    def matches(self, units: Sequence[StudyUnit]) -> bool:
        return self.unit_ids == tuple(unit.unit_id for unit in units)

    def apply_report(self, unit_ids: Iterable[str]) -> None:
        """Replace the previous report of weak units."""
        reported = set(unit_ids)
        for unit_id, evidence in self.units.items():
            evidence.self_reported = unit_id in reported

    def flag(self, unit_id: str) -> None:
        """Remember a unit a check named as the likeliest difficulty, even when it was not confirmed."""
        if unit_id in self.units:
            self.flagged.add(unit_id)

    def focus_units(self) -> tuple[str, ...]:
        """Units that should get extra time: likely gaps, plus reported or flagged units not yet mastered."""
        return tuple(
            unit_id for unit_id, evidence in self.units.items()
            if evidence.status == "gap"
            or (evidence.status != "mastered" and (evidence.self_reported or unit_id in self.flagged))
        )

    def answered(self, question_id: str) -> bool:
        return any(answer.question_id == question_id for answer in self.answers())

    def record(self, question_id: str, unit_id: str, kind: str, correct: bool, source: AnswerSource,
               prompt: str = "") -> Answer:
        if unit_id not in self.units:
            raise ValueError(f"Unknown study unit: {unit_id}")
        for answer in self.units[unit_id].answers:
            if answer.question_id == question_id:
                return answer
        answer = Answer(question_id, unit_id, kind, correct, source, prompt)
        self.units[unit_id].answers.append(answer)
        return answer

    def answers(self) -> list[Answer]:
        return [answer for evidence in self.units.values() for answer in evidence.answers]

    def answer(self, question_id: str) -> Answer | None:
        return next((answer for answer in self.answers() if answer.question_id == question_id), None)

    def status(self, unit_id: str) -> Status:
        return self.units[unit_id].status

    def summary(self) -> dict[str, Any]:
        """The evidence the diagnosis agent sees, in study order."""
        return {
            "units": [
                {
                    "unit_id": unit_id,
                    "title": evidence.unit.title,
                    "status": evidence.status,
                    "marked_weak_by_learner": evidence.self_reported,
                    "answers": [
                        {"question_id": a.question_id, "correct": a.correct, "kind": a.kind, "source": a.source}
                        for a in evidence.answers
                    ],
                }
                for unit_id, evidence in self.units.items()
            ],
        }
