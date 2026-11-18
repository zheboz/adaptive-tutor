"""Distribute ordered study units, readings, and activities across days."""

from collections import deque
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from .units import StudyUnit


@dataclass(frozen=True)
class StudyAssignment:
    unit: StudyUnit
    kind: Literal["study", "read", "apply"]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class StudyDay:
    number: int
    assignments: tuple[StudyAssignment, ...]


def _groups[T](items: tuple[T, ...], count: int) -> Iterator[tuple[T, ...]]:
    """Yield contiguous groups whose sizes differ by at most one item."""
    size, extra = divmod(len(items), count)
    start = 0
    for index in range(count):
        end = start + size + (index < extra)
        yield items[start:end]
        start = end


def schedule_units(units: Sequence[StudyUnit], target_days: int) -> tuple[StudyDay, ...]:
    """Return the days with assigned material. Later days are available for review."""
    if type(target_days) is not int or target_days < 1:
        raise ValueError("Target days must be a positive integer.")
    if not units:
        return ()

    whole_units = tuple(
        StudyAssignment(unit, "study", tuple(dict.fromkeys(unit.source_ids))) for unit in units
    )
    if target_days <= len(whole_units):
        return tuple(
            StudyDay(number, group)
            for number, group in enumerate(_groups(whole_units, target_days), start=1)
        )

    # Give each unit a separate reading day in turn, up to one day per cited page.
    reading_days = [0] * len(whole_units)
    remaining = target_days - len(whole_units)
    eligible = deque(index for index, whole in enumerate(whole_units) if whole.source_ids)
    while remaining and eligible:
        index = eligible.popleft()
        reading_days[index] += 1
        remaining -= 1
        if reading_days[index] < len(whole_units[index].source_ids):
            eligible.append(index)

    assignments = []
    for whole, count in zip(whole_units, reading_days, strict=True):
        if count == 0:
            assignments.append(whole)
            continue
        for pages in _groups(whole.source_ids, count):
            assignments.append(StudyAssignment(whole.unit, "read", pages))
        assignments.append(StudyAssignment(whole.unit, "apply", whole.source_ids))
    return tuple(StudyDay(number, (task,)) for number, task in enumerate(assignments, start=1))
