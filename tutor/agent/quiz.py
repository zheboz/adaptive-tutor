"""The quick check before the plan exists: one question per outline topic.

Topics the learner checked are quizzed in the order they were checked. With none checked, up to
three topics spread across the whole outline are quizzed. Each question is built from the topic's
own pages, so it checks that topic rather than its unit as a whole. No Streamlit code belongs here.
"""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
import contextvars
from dataclasses import dataclass

from tutor.assessment import questions, retrieval
from tutor.assessment.questions import PracticeError, Question
from tutor.llm import LLMError
from tutor.materials.outline import Outline
from tutor.planning import StudyAssignment, StudyUnit

from .state import LearnerState


UNCHECKED_QUESTIONS = 3
WORKERS = 6


@dataclass(frozen=True)
class QuizItem:
    id: str
    topic_number: int
    topic_title: str
    unit_id: str
    question: Question


@dataclass(frozen=True)
class Quiz:
    items: tuple[QuizItem, ...]
    # Topics that got no question, with the reason, in quiz order.
    skipped: tuple[tuple[int, str, str], ...] = ()


@dataclass(frozen=True)
class QuizResult:
    item: QuizItem
    choice: int

    @property
    def correct(self) -> bool:
        return self.choice == self.item.question.correct_index


def choose_topics(topic_count: int, checked_in_order: Sequence[int]) -> list[int]:
    """Checked topics in the order checked, or up to three topics spread across the outline."""
    checked = [n for n in dict.fromkeys(checked_in_order) if 1 <= n <= topic_count]
    if checked:
        return checked
    if topic_count <= UNCHECKED_QUESTIONS:
        return list(range(1, topic_count + 1))
    step = (topic_count - 1) / (UNCHECKED_QUESTIONS - 1)
    return [round(i * step) + 1 for i in range(UNCHECKED_QUESTIONS)]


def _unit_for(topic_number: int, units: Sequence[StudyUnit]) -> StudyUnit:
    return next(unit for unit in units if topic_number in unit.topic_ids)


def _question_for(outline: Outline, units: Sequence[StudyUnit], index: retrieval.PassageIndex,
                  topic_number: int) -> Question | None:
    topic = outline.topics[topic_number - 1]
    unit = _unit_for(topic_number, units)
    # Focus the question on this topic: its title, summary and pages stand in for the unit's.
    focus = StudyUnit(unit.unit_id, topic.title, topic.summary, tuple(topic.source_ids), unit.activity,
                      unit.topic_ids)
    assignment = StudyAssignment(focus, "study", focus.source_ids)
    passages = retrieval.retrieve(index, assignment)
    reading = [passage for passage in index.passages if passage.source_id in set(focus.source_ids)]
    built = questions.generate_questions(assignment, passages, assigned_reading=reading, questions_wanted=1)
    # Multiple choice first: a true/false answer is right half the time by chance.
    return min(built, key=lambda question: question.kind == "true_false", default=None)


def build_quiz(outline: Outline, units: Sequence[StudyUnit], index: retrieval.PassageIndex,
               topic_numbers: Sequence[int]) -> Quiz:
    """Build the questions in parallel. Raises LLMError only when no question could be built for an outage."""
    def build(number: int) -> Question | None | Exception:
        try:
            return _question_for(outline, units, index, number)
        except (PracticeError, LLMError) as error:
            return error

    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="quiz") as pool:
        futures = [pool.submit(contextvars.copy_context().run, build, number) for number in topic_numbers]
        outcomes = [future.result() for future in futures]

    items, skipped, outages = [], [], []
    for number, outcome in zip(topic_numbers, outcomes, strict=True):
        title = outline.topics[number - 1].title
        if isinstance(outcome, Question):
            unit = _unit_for(number, units)
            items.append(QuizItem(f"quiz-{len(items) + 1}", number, title, unit.unit_id, outcome))
        elif isinstance(outcome, LLMError):
            outages.append(outcome)
            skipped.append((number, title, str(outcome)))
        else:
            reason = str(outcome) if outcome is not None else "The reading had no question to ask."
            skipped.append((number, title, reason))
    if outages and not items:
        raise outages[0]
    return Quiz(tuple(items), tuple(skipped))


def grade_quiz(state: LearnerState, quiz: Quiz, choices: Sequence[int]) -> list[QuizResult]:
    """Record every answer as evidence; a wrong answer marks its unit for extra time in the plan."""
    results = []
    for item, choice in zip(quiz.items, choices, strict=True):
        result = QuizResult(item, choice)
        state.record(item.id, item.unit_id, item.question.kind, result.correct, "quiz", item.question.prompt)
        if not result.correct:
            state.flag(item.unit_id)
        results.append(result)
    return results
