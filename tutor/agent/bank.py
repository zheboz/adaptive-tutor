"""Diagnostic questions per study unit, generated from the unit's reading on first use and cached."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
import re
import unicodedata

from tutor.assessment import questions, retrieval
from tutor.assessment.questions import PracticeError, Question
from tutor.materials.ingest import PdfPage
from tutor.planning import StudyAssignment, StudyUnit


# Confirming a gap takes two wrong answers on the unit, so one question per unit is not enough.
QUESTIONS_PER_UNIT = 3
_NUMBERING = re.compile(r"^(?:(?:exercise|question|q)\s*\d+\s*[.:：)）]?|第\s*\d+\s*[题題][.:：、]?|\d+\s*[.)）、])\s*", re.I)


def _identity(question: Question) -> tuple[str, frozenset[str]]:
    """The same question with or without its printed number, punctuation or option order."""
    def normal(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip("?？.。!！")

    return normal(_NUMBERING.sub("", question.prompt.strip())), frozenset(map(normal, question.options))

@dataclass(frozen=True)
class DiagnosticQuestion:
    id: str
    unit_id: str
    question: Question


class QuestionBank:
    """Questions come from the existing verified practice pipeline, so each cites the learner's material."""

    def __init__(self, units: Sequence[StudyUnit], pages: Sequence[PdfPage]):
        self._units = {unit.unit_id: unit for unit in units}
        self._pages = pages
        self._index: retrieval.PassageIndex | None = None
        self._questions: dict[str, tuple[DiagnosticQuestion, ...]] = {}
        self.problems: dict[str, str] = {}

    def _build(self, unit_id: str) -> tuple[DiagnosticQuestion, ...]:
        if self._index is None:
            self._index = retrieval.build_index(self._pages)
        unit = self._units[unit_id]
        assignment = StudyAssignment(unit, "study", unit.source_ids)
        passages = retrieval.retrieve(self._index, assignment)
        scope = set(unit.source_ids)
        reading = [passage for passage in self._index.passages if passage.source_id in scope]
        try:
            built = questions.generate_questions(
                assignment, passages, assigned_reading=reading, questions_wanted=QUESTIONS_PER_UNIT,
            )
        except PracticeError as error:
            self.problems[unit_id] = str(error)
            return ()
        # Multiple choice first: a true/false answer is right half the time by chance.
        ranked = sorted(built, key=lambda question: question.kind == "true_false")
        # A printed exercise and its adapted copy are one piece of evidence, not two.
        seen = set()
        distinct = []
        for question in ranked:
            if _identity(question) not in seen:
                seen.add(_identity(question))
                distinct.append(question)
        return tuple(DiagnosticQuestion(f"{unit_id}:q{n}", unit_id, q) for n, q in enumerate(distinct, 1))

    def pick(self, unit_id: str, exclude: Collection[str]) -> DiagnosticQuestion | None:
        """Return an unused question for the unit; model errors propagate to the caller."""
        if unit_id not in self._units:
            return None
        if unit_id not in self._questions:
            self._questions[unit_id] = self._build(unit_id)
        return next((q for q in self._questions[unit_id] if q.id not in exclude), None)

    def remaining(self, unit_id: str, exclude: Collection[str]) -> int | None:
        """Unused questions for a unit, or None before its questions have been prepared."""
        if unit_id not in self._questions:
            return None
        return sum(q.id not in exclude for q in self._questions[unit_id])
