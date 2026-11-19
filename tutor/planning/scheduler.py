"""Distribute ordered study units, readings, and activities across days.

Units the learner marked as weak get more of the time. In a short plan they count double when
units share days. In a long plan the extra days go first to their reading days, then to a review
day for each, and only then to other units. Without weak units the plan is spread evenly.
"""

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Literal

from .units import StudyUnit


# A weak unit counts as this many ordinary units when days are shared.
WEAK_WEIGHT = 2


@dataclass(frozen=True)
class StudyAssignment:
    unit: StudyUnit
    kind: Literal["study", "read", "apply", "review"]
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


def _weighted_groups[T](items: tuple[T, ...], weights: Sequence[int], count: int) -> list[tuple[T, ...]]:
    """Split items, in order, into `count` non-empty groups whose largest total weight is smallest."""
    prefix = [0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)

    def total(start: int, end: int) -> int:
        return prefix[end] - prefix[start]

    @cache
    def best(start: int, groups: int) -> int:
        if groups == 1:
            return total(start, len(items))
        return min(max(total(start, end), best(end, groups - 1))
                   for end in range(start + 1, len(items) - groups + 2))

    result = []
    start = 0
    for groups in range(count, 1, -1):
        target = best(start, groups)
        share = total(start, len(items)) / groups
        # Among the optimal cuts, keep each day's load closest to an even share.
        end = min(
            (end for end in range(start + 1, len(items) - groups + 2)
             if max(total(start, end), best(end, groups - 1)) == target),
            key=lambda end: abs(total(start, end) - share),
        )
        result.append(items[start:end])
        start = end
    result.append(items[start:])
    return result


def schedule_units(
    units: Sequence[StudyUnit], target_days: int, weak_unit_ids: Collection[str] = (),
) -> tuple[StudyDay, ...]:
    """Return the days with assigned material. Later days are available for review."""
    if type(target_days) is not int or target_days < 1:
        raise ValueError("Target days must be a positive integer.")
    if not units:
        return ()
    weak = {unit.unit_id for unit in units} & set(weak_unit_ids)

    whole_units = tuple(
        StudyAssignment(unit, "study", tuple(dict.fromkeys(unit.source_ids))) for unit in units
    )
    if target_days <= len(whole_units):
        if weak:
            weights = [WEAK_WEIGHT if part.unit.unit_id in weak else 1 for part in whole_units]
            groups = _weighted_groups(whole_units, weights, target_days)
        else:
            groups = list(_groups(whole_units, target_days))
        return tuple(StudyDay(number, group) for number, group in enumerate(groups, start=1))

    # Extra days go, in this order, to: reading days for weak units, one review day per weak
    # unit, then reading days for the other units. Reading days are given in rounds, up to
    # one day per cited page. Days still left are optional review.
    reading_days = [0] * len(whole_units)
    remaining = target_days - len(whole_units)
    weak_indices = [i for i, part in enumerate(whole_units) if part.unit.unit_id in weak]
    other_indices = [i for i, part in enumerate(whole_units) if part.unit.unit_id not in weak]

    def give_reading_days(indices: list[int]) -> None:
        nonlocal remaining
        while remaining:
            progressed = False
            for index in indices:
                if remaining and reading_days[index] < len(whole_units[index].source_ids):
                    reading_days[index] += 1
                    remaining -= 1
                    progressed = True
            if not progressed:
                return

    give_reading_days(weak_indices)
    reviews = set()
    for index in weak_indices:
        if remaining:
            reviews.add(index)
            remaining -= 1
    give_reading_days(other_indices)

    assignments = []
    for index, (whole, count) in enumerate(zip(whole_units, reading_days, strict=True)):
        if count == 0:
            assignments.append(whole)
        else:
            for pages in _groups(whole.source_ids, count):
                assignments.append(StudyAssignment(whole.unit, "read", pages))
            assignments.append(StudyAssignment(whole.unit, "apply", whole.source_ids))
        if index in reviews:
            assignments.append(StudyAssignment(whole.unit, "review", whole.source_ids))
    return tuple(StudyDay(number, (task,)) for number, task in enumerate(assignments, start=1))
