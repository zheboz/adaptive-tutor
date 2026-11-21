"""Where a quoted sentence sits on a PDF page, so the reader can highlight it.

pypdf's layout mode knows where each line of text starts and ends; a quote's words are matched to
those lines in order, the way knowledge-card quotes are checked, and each line they cover becomes a
rectangle. Positions within a line are estimated from character offsets, which is close enough to
mark the sentence. Anything the page's text cannot place gives no rectangles: a highlight is a
convenience, never required. No Streamlit code belongs here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import io
import re
import unicodedata

from pypdf import PdfReader
from pypdf.generic import ArrayObject, ContentStream, StreamObject


# A Han character on its own, or a run of other letters and digits.
_TOKEN = re.compile(r"[㐀-鿿]|(?:(?![㐀-鿿])[^\W_])+")
_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


@dataclass(frozen=True)
class TextLine:
    """One line of text in PDF coordinates: x from left, baseline y from the bottom."""
    text: str
    x0: float
    x1: float
    baseline: float
    height: float


@dataclass(frozen=True)
class Box:
    """A rectangle in viewer coordinates: points from the page's top-left corner."""
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PageLines:
    lines: tuple[TextLine, ...]
    left: float
    top: float


def page_lines(pdf: bytes, number: int) -> PageLines:
    """The page's lines of text with their positions; empty when the page cannot be read that way."""
    from pypdf._text_extraction._layout_mode import _fixed_width_page as layout
    from pypdf._text_extraction._layout_mode._text_state_manager import TextStateManager

    empty = PageLines((), 0.0, 0.0)
    try:
        reader = PdfReader(io.BytesIO(pdf))
        page = reader.pages[number - 1]
        box = page.cropbox
        if int(page.get("/Rotate", 0) or 0) % 360:
            return empty
        contents = page.get("/Contents")
        contents = contents.get_object() if contents is not None else None
        if not isinstance(contents, (ArrayObject, StreamObject)):
            return empty
        fonts = page._layout_mode_fonts()
        operations = iter(ContentStream(contents, reader, "bytes").operations)
        # As pypdf's text_show_operations, without shifting the lines to the left margin.
        state = TextStateManager()
        groups = []
        for operands, operator in operations:
            if operator in (b"BT", b"q"):
                found, _ = layout.recurse_to_target_op(
                    operations, state, b"ET" if operator == b"BT" else b"Q", fonts, True,
                )
                groups.extend(found)
            elif operator == b"Tf":
                layout.set_font_operation(state, fonts, operands)
            else:
                state.set_state_param(operator, operands)
    except Exception:  # noqa: BLE001 - an unusual PDF only means no highlight
        return empty
    lines = tuple(
        TextLine(group["text"], float(group["tx"]), float(group["displaced_tx"]), float(group["ty"]),
                 float(group["font_height"]))
        for group in groups
        if group["flip_sort"] == 1 and group["text"].strip() and group["displaced_tx"] > group["tx"]
    )
    return PageLines(lines, float(box.left), float(box.top))


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """Each word of the text, normalized, with where it starts and ends in the text."""
    return [(unicodedata.normalize("NFKC", match.group()).casefold(), match.start(), match.end())
            for match in _TOKEN.finditer(text)]


def _match(page: Sequence[str], quote: Sequence[str]) -> list[int] | None:
    """Positions of the quote's words on the page, in order, allowing words in between (the other
    column of a slide) within a span of three times the quote's length plus 20 words."""
    if not quote:
        return None
    span = 3 * len(quote) + 20
    for start, word in enumerate(page):
        if word != quote[0]:
            continue
        found = []
        for position in range(start, min(start + span, len(page))):
            if page[position] == quote[len(found)]:
                found.append(position)
                if len(found) == len(quote):
                    return found
    return None


def quote_boxes(page: PageLines, quote: str) -> list[Box]:
    """One rectangle per line the quote covers, or none when its words are not on the page."""
    quote = _ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), quote)
    words: list[str] = []
    places: list[tuple[int, int, int]] = []  # line, start, end
    for index, line in enumerate(page.lines):
        for word, start, end in _tokens(line.text):
            words.append(word)
            places.append((index, start, end))
    found = _match(words, [word for word, _, _ in _tokens(quote)])
    if not found:
        return []
    spans: dict[int, tuple[int, int]] = {}
    for position in found:
        index, start, end = places[position]
        first, last = spans.get(index, (start, end))
        spans[index] = (min(first, start), max(last, end))
    boxes = []
    for index, (start, end) in sorted(spans.items()):
        line = page.lines[index]
        scale = (line.x1 - line.x0) / max(len(line.text), 1)
        x0, x1 = line.x0 + start * scale, line.x0 + end * scale
        # From a little below the baseline to the top of the capitals.
        top = line.baseline + 0.85 * line.height
        boxes.append(Box(x0 - page.left, page.top - top, x1 - x0, 1.1 * line.height))
    return boxes
