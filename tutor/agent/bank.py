"""Diagnostic questions per study unit, generated from the unit's reading and cached.

Questions are built on first use, or earlier in background threads with ``prefetch`` so a check
does not wait for each unit in turn.
"""

from collections.abc import Collection, Iterable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
import contextvars
from dataclasses import dataclass
import re
import threading
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
        self._pending: dict[str, Future] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self.problems: dict[str, str] = {}

    @property
    def unit_ids(self) -> tuple[str, ...]:
        return tuple(self._units)

    def _passage_index(self) -> retrieval.PassageIndex:
        with self._lock:
            if self._index is None:
                self._index = retrieval.build_index(self._pages)
            return self._index

    def _build(self, unit_id: str) -> tuple[DiagnosticQuestion, ...]:
        index = self._passage_index()
        unit = self._units[unit_id]
        assignment = StudyAssignment(unit, "study", unit.source_ids)
        passages = retrieval.retrieve(index, assignment)
        scope = set(unit.source_ids)
        reading = [passage for passage in index.passages if passage.source_id in scope]
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

    def prefetch(self, unit_ids: Iterable[str]) -> None:
        """Start building questions for these units in the background.

        Model calls made there are recorded in the trace that is active when this is called.
        """
        self._passage_index()
        for unit_id in unit_ids:
            if unit_id not in self._units or unit_id in self._questions or unit_id in self._pending:
                continue
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="question-bank")
            context = contextvars.copy_context()
            self._pending[unit_id] = self._executor.submit(context.run, self._build, unit_id)

    def _ensure(self, unit_id: str) -> None:
        if unit_id in self._questions:
            return
        future = self._pending.pop(unit_id, None)
        # A failed request is not cached, so the next pick retries it.
        self._questions[unit_id] = future.result() if future is not None else self._build(unit_id)

    def pick(self, unit_id: str, exclude: Collection[str]) -> DiagnosticQuestion | None:
        """Return an unused question for the unit; model errors propagate to the caller."""
        if unit_id not in self._units:
            return None
        self._ensure(unit_id)
        return next((q for q in self._questions[unit_id] if q.id not in exclude), None)

    def remaining(self, unit_id: str, exclude: Collection[str]) -> int | None:
        """Unused questions for a unit, or None before its questions have been prepared."""
        if unit_id not in self._questions:
            return None
        return sum(q.id not in exclude for q in self._questions[unit_id])
