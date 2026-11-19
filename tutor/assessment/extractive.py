"""Build a fill-in-the-blank reading check directly from a verified concept on the assigned pages."""

import re
from collections.abc import Sequence

from tutor.planning import StudyAssignment

from .concepts import Concept, find_concepts
from .questions import Question
from .retrieval import Passage


_NUMBER = re.compile(r"(?<![A-Za-z_0-9.+-])\d{1,8}(?:\.\d{1,6})?(?!\d|\.\d|[A-Za-z_])")


def build_reading_check(
    assignment: StudyAssignment, passages: Sequence[Passage], concepts: Sequence[Concept] | None = None,
) -> Question | None:
    """Build one question from the selected evidence without making another model request.

    Only a numeric cloze is built: it has real distractors from the same passage. Restating a
    sentence as a true/false item would always be "True" and would not show understanding,
    so a reading without a usable number gets no check.
    """
    if concepts is None:
        concepts = find_concepts(assignment, passages)
    assigned = {p.id: p for p in passages if p.source_id in assignment.source_ids}
    for concept in concepts:
        passage = assigned.get(concept.passage_id)
        if not passage or passage.source_id != concept.source_id or not concept.text.strip():
            continue
        quote = concept.text
        if quote not in passage.text:
            continue
        # Keep examples and equations intact; blank a value in explanatory prose.
        if "=" in quote:
            continue
        target = _NUMBER.search(quote)
        if not target:
            continue
        # Distractors come from the same passage; 1 and 1.0 are one possible answer.
        values = {float(word): word for word in _NUMBER.findall(passage.text)}
        if len(values) < 2:
            continue
        answer = target[0]
        number = float(answer)
        values[number] = answer
        nearby = sorted(values, key=lambda n: abs(n - number))[:4]
        options = tuple(values[n] for n in sorted(nearby))
        prompt = quote[:target.start()] + "____" + quote[target.end():]
        return Question("multiple_choice", prompt, options, options.index(answer), quote,
                        "generated", (passage.source_id,), "reading", concept.id)
    return None
