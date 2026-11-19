"""Select assessable statements from a learning item's assigned PDF passages."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from hashlib import sha256
import re
import unicodedata

from tutor.planning import StudyAssignment

from .retrieval import Passage, _terms


@dataclass(frozen=True)
class Concept:
    id: str
    passage_id: str
    source_id: str
    text: str


_BULLET = re.compile(r"^(?:[•●○◦▪▫‣‒–—*·◆▶➢]|[-]|\d+[.)、])\s*")
_ASSESSMENT = re.compile(
    r"^(?:(?:(?:review|pop)\s+)?(?:exercises?|quiz)\b|questions?(?:\s*\d+|\s*[:：]|$)|"
    r"Q\.?\s*\d+\b|(?:\d+[.)]\s*)?true\s*(?:or|/)\s*false\b|(?:choose|select) (?:the|an?)\b|"
    r"第\s*\d+\s*[题題]|(?:练习|練習|习题|習題|选择题|選擇題|判断题|判斷題))", re.I,
)
_OPTION_OR_KEY = re.compile(
    r"^(?:[(（]?[A-FＡ-Ｆ](?:[)）.．、]\s*|$)|(?:correct answer|answer|solution|正确答案|正確答案|答案)\s*[:：=])",
    re.I,
)
_OUTLINE = re.compile(
    r"^(?:(?:agenda|outline|syllabus|table of contents|learning (?:goals|objectives)|references|"
    r"bibliography|course logistics|reading list)\b|目录|目錄|学习目标|學習目標|教学大纲|议程|議程)", re.I,
)
_OBJECTIVE = re.compile(r"^(?:(?:understand|describe|explain|identify|discuss|learn about|students will|"
                        r"you will)\b|了解|理解|学习目标|學習目標|介绍|介紹)", re.I)
_PREDICATE = (
    r"is|are|was|were|can|must|has|have|will|should|"
    r"(?:mean|set|add|store|contain|record|equal|increase|decrease|return|define|denote|represent|"
    r"require|use|keep|persist|retain|measure|compare|compute|divide|multiply|track|retrieve|"
    r"rank|select|prevent|depend|allow|capture|combine|map|predict|estimate|reduce|count|"
    r"preserve|save|limit|evaluate|include|link|provide|control|enable|update|improve|"
    r"convert|assess|determine|distinguish|support|differ|consist|hold|maintain)s?"
)
_RELATION = re.compile(
    rf"\b(?:{_PREDICATE}|because|whereas|unlike|before|after|when)\b|"
    r"是|可[以用]|能[够夠]|用于|用於|包含|包括|表示|等[于於]|增加|减[少小]|減[少小]|保存|"
    r"返回|存储|儲存|保留|衡量|分[为為]|通[过過]|依[据據赖賴]|需要|检索|檢索|"
    r"相比|而非|如果|当.+时|當.+時|首先|然后|然後|越.+越", re.I,
)
_DEPENDENT = re.compile(rf"^(?:{_PREDICATE}|it|they|these|this|those)\b|^(?:它们?|它們|用于|用於|可用|可以)", re.I)
_PROCEDURE = re.compile(r"^(?:first|next|finally|step\s*\d+|to\s+\w+,|首先|其次|随后|最後|最后)", re.I)
_HAN = re.compile(r"[\u3400-\u9fff]")
_FORMULA = re.compile(r"[\w)]\s*=\s*[\w(].*(?:[/*+×÷]|\s-\s)")
_KEYWORD_SEPARATOR = re.compile(r"\s[·•|]\s")
_SENTENCE_END = (".", "。", "!", "！", ";", "；")


def _label(text: str) -> bool:
    """Slide labels and keyword lists name a topic without stating anything about it."""
    if text.rstrip().endswith(_SENTENCE_END):
        return False
    # "LONG-TERM · THE STORE": a capitalized label, even if a word could be read as a verb.
    letters = [char for char in text if char.isascii() and char.isalpha()]
    if len(letters) >= 3 and sum(char.isupper() for char in letters) >= 0.7 * len(letters):
        return True
    # "write policy · read policy"
    return bool(_KEYWORD_SEPARATOR.search(text))


def _assertion(text: str) -> bool:
    if len(text) > 550 or _OBJECTIVE.match(text) or "?" in text or "？" in text:
        return False
    if _FORMULA.search(text):
        return True
    if _label(text):
        return False
    if len(text.split()) < 3 and len(_HAN.findall(text)) < 5:
        return False
    if _RELATION.search(text) or _PROCEDURE.match(text):
        return True
    # Slides often define a term using a noun phrase rather than a full sentence.
    parts = re.split(r"\s*[:：]\s*|\s+[—–]\s+", text, maxsplit=1)
    return len(parts) == 2 and 0 < len(parts[0]) <= 65 and len(set(_terms(parts[1]))) >= 2


def _lines(text: str) -> Iterator[tuple[int, str]]:
    """Preserve original offsets, including when a PDF wraps a sentence across lines."""
    pending = None
    for match in re.finditer(r"[^\r\n]+", text):
        line = match[0].strip()
        if not line:
            continue
        start = match.start() + match[0].index(line)
        if pending is not None:
            prev_start, prev_end = pending
            previous = text[prev_start:prev_end]
            if (line[0].islower() and "\n\n" not in text[prev_end:start]
                    and previous[-1] not in ".!?。！？:：" and not _OPTION_OR_KEY.match(line)
                    and not _ASSESSMENT.match(previous) and not _OUTLINE.match(previous)):
                pending = (prev_start, start + len(line))
                continue
            yield prev_start, previous
        pending = (start, start + len(line))
    if pending is not None:
        start, end = pending
        yield start, text[start:end]


def _single_column_statements(text: str) -> Iterator[tuple[str, str]]:
    lines = list(_lines(text))
    heading, heading_start = "", -1
    in_exercise = False
    for i, (start, raw) in enumerate(lines):
        body = _BULLET.sub("", raw, count=1).strip()
        if not body:
            continue
        if _ASSESSMENT.match(body) or _OPTION_OR_KEY.match(body) or _OUTLINE.match(body):
            in_exercise = True
            heading = ""
            continue
        # A keyed or lettered prompt may itself be phrased as a true statement.
        if i + 1 < len(lines) and _OPTION_OR_KEY.match(lines[i + 1][1]):
            continue
        is_heading = (body == raw and len(body) <= 105 and not body.endswith((".", "。"))
                      and (body.endswith(("?", "？")) or not _assertion(body)))
        if is_heading:
            heading, heading_start = body, start
            in_exercise = False
            continue
        if in_exercise:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|(?<=[。？！])", body):
            sentence = sentence.strip()
            if not sentence or not _assertion(sentence):
                continue
            if _DEPENDENT.match(sentence):
                if not heading or i == 0 or lines[i - 1][0] != heading_start:
                    continue
                end = start + raw.index(sentence) + len(sentence)
                sentence = text[heading_start:end]
            yield sentence, heading


def _statements(text: str) -> Iterator[tuple[str, str]]:
    if not re.search(r"\S[ \t]{5,}\S", text):
        yield from _single_column_statements(text)
        return
    # PDF layout extraction can place independent columns on one physical row.
    # Only use self-contained cells here; combining rows could attach a claim to
    # the wrong subject. On a quiz slide the same cells can be false distractors.
    cells = [cell.strip() for line in text.splitlines()
             for cell in re.split(r"[ \t]{5,}", line.strip()) if cell.strip()]
    if any(_ASSESSMENT.match(cell) or _OPTION_OR_KEY.match(cell) for cell in cells):
        return
    for cell in cells:
        yield from _single_column_statements(cell)


def find_concepts(assignment: StudyAssignment, passages: Sequence[Passage]) -> tuple[Concept, ...]:
    """Return up to five distinct, relevant claims with verbatim, assigned-page evidence."""
    unit = assignment.unit
    goal = unit.title + " " + unit.objective
    if assignment.kind != "read":
        goal += " " + unit.activity
    query = set(_terms(goal))
    ranked = []
    for passage in passages:
        if passage.source_id not in assignment.source_ids:
            continue
        for text, heading in _statements(passage.text):
            direct = len(query.intersection(_terms(text)))
            context = len(query.intersection(_terms(heading)))
            if direct or context:
                ranked.append((direct * 2 + context, passage, text))

    selected = {}
    for _, passage, text in sorted(ranked, key=lambda item: item[0], reverse=True):
        normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(".。")
        if normalized not in selected:
            digest = sha256(normalized.encode()).hexdigest()[:12]
            selected[normalized] = Concept(f"{passage.source_id}-{digest}", passage.id, passage.source_id, text)
            if len(selected) == 5:
                break
    return tuple(selected.values())
