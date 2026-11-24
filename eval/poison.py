"""Build a poisoned copy of the course PDF: the original slides, then one extra page per injected text.

Each extra page looks like a slide (a title and a few lines of course content) with an instruction to
AI tutors hidden in it. It is what a learner would upload without noticing, and it reaches the tutor
the same way the real slides do: through text extraction, search and read_page.
"""

from io import BytesIO
import textwrap

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


_LINE_CHARS = 88
_LINE_HEIGHT = 14


def _font() -> DictionaryObject:
    return DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        # Latin-1 bytes as written: the standard encoding would turn ' into a curly quote.
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    })


def _lines(text: str) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        lines += textwrap.wrap(paragraph, _LINE_CHARS) or [""]
    return lines


def _add_text_page(writer: PdfWriter, text: str) -> None:
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): _font()}),
    })
    commands = []
    for row, line in enumerate(_lines(text)):
        if line:
            data = line.encode("latin-1", "replace").hex()
            commands.append(f"BT /F1 11 Tf 1 0 0 1 48 {744 - row * _LINE_HEIGHT} Tm <{data}> Tj ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    page.replace_contents(stream)


def poisoned_pdf(original: bytes, injected: list[str]) -> bytes:
    """The original PDF with one page appended for each injected text, in order."""
    writer = PdfWriter()
    for page in PdfReader(BytesIO(original)).pages:
        writer.add_page(page)
    for text in injected:
        _add_text_page(writer, text)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
