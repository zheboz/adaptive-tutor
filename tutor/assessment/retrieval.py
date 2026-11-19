"""Retrieve cited readings and related PDF exercises with a local BM25 index."""

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import math
import re
import unicodedata

from tutor.materials.ingest import PdfPage
from tutor.planning.scheduler import StudyAssignment


_CHUNK_SIZE = 1600
_OVERLAP = 180
_MAX_PASSAGES = 10
# Added to the BM25 score of a passage that contains the search query word for word.
_PHRASE_BONUS = 10.0
# Split adjacent Latin words and Han sequences even when there are no spaces.
_TOKEN = re.compile(r"[\u3400-\u9fff]+|(?:(?![\u3400-\u9fff])[^\W_])+")
_STOP = set("""
    a an and are as at be been by can chapter choose concept correct describe do each
    example exercise explain following for from how in into is it learning material of
    on or page practice question read reading select statement study task that the their
    then these this to true false use using what when which with you your
    以下 下列 关于 阅读 练习 习题 问题 判断 选择 正确 错误 一个 这个 是否 的 是 与 和
""".split())
_EXERCISE = re.compile(
    r"[?？]|\b(?:questions?|quiz|exercises?|true\s*(?:or|/)\s*false|which of)\b"
    r"|^\s*\d{1,3}[.)、]\s*(?:compute|identify|find|explain|determine|select|calculate|choose)\b"
    r"|练习|习题|选择题|判断题|下列|对错", re.I | re.M
)
_OPTIONS = re.compile(r"^\s*(?:[（(]?[A-F][).:）、．]|答案\s*[:：]|answer\s*[:：])", re.I | re.M)


@dataclass(frozen=True)
class Passage:
    id: str
    source_id: str
    text: str


@dataclass(frozen=True)
class PassageIndex:
    passages: tuple[Passage, ...]
    term_counts: tuple[Counter[str], ...]
    idf: dict[str, float]
    average_length: float


def _terms(text: str) -> Iterator[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    for run in _TOKEN.findall(normalized):
        if "\u3400" <= run[0] <= "\u9fff":
            for i in range(max(1, len(run) - 1)):
                term = run[i:i + 2]
                if term not in _STOP:
                    yield term
        elif len(run) > 1 and not run.isdecimal():
            if len(run) > 4 and run.endswith("s") and not run.endswith(("ss", "us", "is")):
                run = run[:-1]
            if run not in _STOP:
                yield run


def topical_overlap(first: str, second: str) -> int:
    """Count shared content terms using the same tokenizer as the retrieval index."""
    return len(set(_terms(first)).intersection(_terms(second)))


def _chunks(text: str) -> Iterator[str]:
    start = 0
    while start < len(text):
        end = min(len(text), start + _CHUNK_SIZE)
        if end < len(text):
            newline = text.rfind("\n", start + _CHUNK_SIZE // 2, end)
            if newline >= 0:
                end = newline + 1
        excerpt = text[start:end].strip()
        if excerpt:
            yield excerpt
        if end == len(text):
            break
        start = end - _OVERLAP


def build_index(pages: Sequence[PdfPage]) -> PassageIndex:
    passages = []
    counts = []
    frequency = Counter()
    for page in pages:
        if page.error or not page.text.strip():
            continue
        source = f"p{page.number}"
        for number, text in enumerate(_chunks(page.text), 1):
            passages.append(Passage(f"{source}-c{number}", source, text))
            terms = Counter(_terms(text))
            counts.append(terms)
            frequency.update(terms.keys())
    size = len(passages)
    idf = {term: math.log1p((size - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}
    average_length = sum(terms.total() for terms in counts) / size if size else 0
    return PassageIndex(tuple(passages), tuple(counts), idf, average_length)


def _bm25(index: PassageIndex, position: int, query: dict[str, float]) -> float:
    terms = index.term_counts[position]
    length = terms.total() / (index.average_length or 1)
    normalization = 1.2 * (0.25 + 0.75 * length)
    return sum(
        weight * index.idf[term] * count * 2.2 / (count + normalization)
        for term, weight in query.items() if (count := terms.get(term, 0))
    )


def _flat(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def search(index: PassageIndex, query: str, limit: int = 5) -> tuple[Passage, ...]:
    """Rank every passage against free text, as a tutor's search tool would.

    Words are ranked with BM25. A query that appears verbatim, such as the code fragment
    ``x = x + 1`` whose single letters and digits are not indexed as words, ranks first.
    """
    terms = dict.fromkeys(_terms(query), 1.0)
    phrase = _flat(query)
    if len(phrase.replace(" ", "")) < 3:
        phrase = ""
    if not terms and not phrase:
        return ()
    scored = []
    for i, passage in enumerate(index.passages):
        score = _bm25(index, i, terms) if terms else 0.0
        if phrase and phrase in _flat(passage.text):
            score += _PHRASE_BONUS
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(index.passages[i] for _, i in scored[:limit])


def retrieve(index: PassageIndex, assignment: StudyAssignment) -> tuple[Passage, ...]:
    """Anchor questions to today's pages, then look for matching exercises elsewhere."""
    sources = set(assignment.source_ids)
    anchors = [i for i, passage in enumerate(index.passages) if passage.source_id in sources]
    if not anchors:
        return ()

    unit = assignment.unit
    focus = unit.title + " " + unit.objective
    if assignment.kind != "read":
        focus += " " + unit.activity
    query = dict.fromkeys(_terms(focus), 2.0)
    anchors.sort(key=lambda i: _bm25(index, i, query), reverse=True)
    # Give several cited pages a chance to supply evidence before using more
    # chunks from the same page. Ties retain the original document order.
    first_by_page = {}
    for i in anchors:
        first_by_page.setdefault(index.passages[i].source_id, i)
    ranked_anchors = list(dict.fromkeys([*first_by_page.values(), *anchors]))
    anchors_for_query = Counter()
    for i in ranked_anchors[:5]:
        anchors_for_query.update(index.term_counts[i])
    for term in sorted(anchors_for_query, key=lambda t: anchors_for_query[t] * index.idf[t], reverse=True)[:24]:
        query[term] = query.get(term, 0) + 1.0

    exercises = []
    anchor_set = set(anchors)
    for i, passage in enumerate(index.passages):
        if not (_EXERCISE.search(passage.text) or _OPTIONS.search(passage.text)):
            continue
        if i not in anchor_set and not anchors_for_query.keys() & index.term_counts[i].keys():
            continue
        score = _bm25(index, i, query)
        if score > 0:
            exercises.append((i, score))
    exercises.sort(key=lambda item: item[1], reverse=True)

    selected = dict.fromkeys(list(first_by_page.values())[:5])
    for i, _ in exercises:
        selected[i] = None
        # Multiple-choice options sometimes start in the next chunk or page.
        if i + 1 < len(index.passages) and len(selected) < _MAX_PASSAGES:
            following = index.passages[i + 1]
            adjacent = int(following.source_id[1:]) - int(index.passages[i].source_id[1:]) in (0, 1)
            if adjacent and _OPTIONS.search(following.text[:400]):
                selected[i + 1] = None
        if len(selected) >= _MAX_PASSAGES:
            break
    for i in ranked_anchors:
        if len(selected) >= _MAX_PASSAGES:
            break
        selected[i] = None
    # Supply the chosen evidence in PDF order so a stem precedes its options.
    return tuple(index.passages[i] for i in sorted(selected))
