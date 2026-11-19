"""Recover the wording of one clearly delimited exercise from verified PDF quotes."""

import re
import unicodedata
from collections.abc import Iterator


_NUMBER = re.compile(
    r"(?<!\w)(?:question|exercise|q\.?)\s*\d+\b[.．:：)）]?\s*"
    r"|第\s*\d+\s*[题題][.．:：、]?\s*"
    r"|(?:^|(?<=[.?!。？！])[ \t]+)\s*\d+[.)）．、][ \t]+", re.I | re.M,
)
_CHOICE = re.compile(r"(?<!\S)[(（]?([A-FＡ-Ｆ])[.)）．、][ \t]*", re.I)
_KEY = re.compile(r"(?<!\w)(?:correct answer|answer|答案)\s*[:：]\s*", re.I)
_TF = re.compile(r"(?:true\s*(?:or|/)\s*false|t/f|判[断斷][题題]?)\s*[:：.．、?？]\s*", re.I)
_IMPERATIVE = re.compile(r"^(?:choose|select|determine|identify|calculate|compute|find|which)\b|^(?:选择|選擇|求|计算|計算)", re.I)


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def recover_printed_stem(excerpt: str, kind: str, options: tuple[str, ...]) -> str | None:
    """Return only a verbatim stem; refuse ambiguous boundaries or mismatched choices."""
    text = excerpt.strip()
    choices = tuple(_normalized(option) for option in options)
    if not 2 <= len(choices) <= 6 or any(not choice for choice in choices):
        return None

    # Only trim a standalone answer at the end. A quote containing another
    # question or an explanation after the key cannot safely identify one stem.
    key = _KEY.search(text)
    if key:
        answer = _normalized(text[key.end():]).rstrip(".。").casefold()
        valid_keys = {chr(ord("a") + i) for i in range(len(choices))}
        valid_keys.update(choice.casefold().rstrip(".。") for choice in choices)
        if answer not in valid_keys:
            return None
        text = text[:key.start()].rstrip()

    prefix = _NUMBER.match(text)
    if prefix:
        text = text[prefix.end():]
    if not text or _NUMBER.search(text):
        return None
    if kind == "true_false":
        directive = _TF.match(text)
        if len(choices) != 2 or not directive:
            return None
        statement = text[directive.end():].strip()
        if not statement or _TF.search(statement) or _CHOICE.search(statement):
            return None
        return statement
    if kind != "multiple_choice":
        return None

    labels = list(_CHOICE.finditer(text))
    if len(labels) != len(choices):
        return None
    for i, (label, choice) in enumerate(zip(labels, choices, strict=True)):
        end = labels[i + 1].start() if i + 1 < len(labels) else len(text)
        letter = _normalized(label[1]).upper()
        printed_choice = _normalized(text[label.end():end])
        if letter != chr(ord("A") + i) or printed_choice != choice:
            return None
    stem = text[:labels[0].start()].strip()
    questions = stem.count("?") + stem.count("？")
    if not stem or questions > 1 or (questions == 0 and not prefix and not _IMPERATIVE.match(stem)):
        return None
    return stem


def keyed_exercises(text: str) -> Iterator[tuple[str, str, tuple[str, ...], int]]:
    """Read numbered exercises whose choices and explicit answer are on the same page."""
    starts = [match.start() for match in _NUMBER.finditer(text)]
    for start, end in zip(starts, starts[1:] + [len(text)]):
        block = text[start:end]
        marker = _KEY.search(block)
        if not marker:
            continue
        exercise = block[:marker.start()].strip()
        answer_line = block[marker.end():].strip().splitlines()
        if not answer_line:
            continue
        answer = _normalized(answer_line[0]).rstrip(".。").casefold()
        labels = list(_CHOICE.finditer(exercise))
        if labels:
            kind = "multiple_choice"
            ends = [label.start() for label in labels[1:]] + [len(exercise)]
            options = tuple(exercise[label.end():stop].strip() for label, stop in zip(labels, ends))
        elif answer in {"true", "false"}:
            kind, options = "true_false", ("True", "False")
        elif answer in {"正确", "错误", "对", "错", "正確", "錯誤"}:
            kind = "true_false"
            options = next(pair for pair in (("正确", "错误"), ("对", "错"), ("正確", "錯誤")) if answer in pair)
        else:
            continue
        stem = recover_printed_stem(exercise, kind, options)
        matches = [i for i, option in enumerate(options)
                   if answer in {_normalized(option).casefold(), chr(ord("a") + i)}]
        if stem and len(matches) == 1:
            yield kind, stem, options, matches[0]
