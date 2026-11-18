"""Extract text from uploaded PDFs while retaining physical page numbers."""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PageObject, PdfReader
from pypdf.errors import DependencyError, EmptyFileError, FileNotDecryptedError


class PdfInputError(ValueError):
    """The uploaded document could not be opened for preview."""


@dataclass(frozen=True)
class PdfPage:
    number: int
    text: str
    error: str | None = None


def _read_page(page: PageObject, number: int) -> PdfPage:
    try:
        text = page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=False)
        if text.strip():
            return PdfPage(number, text)
    except Exception:
        # Malformed fonts or positioning can break layout extraction alone.
        pass

    try:
        text = page.extract_text()
    except Exception:
        # A damaged content stream should not hide the other pages.
        return PdfPage(number, "", "The text on this page could not be read.")
    return PdfPage(number, text if text.strip() else "")


def read_pdf_pages(data: bytes) -> list[PdfPage]:
    """Read one preview per page, in document order, without performing OCR."""
    try:
        with PdfReader(BytesIO(data)) as reader:
            pages = [_read_page(page, n) for n, page in enumerate(reader.pages, start=1)]
    except EmptyFileError as exc:
        raise PdfInputError("This file is empty. Choose a PDF with content.") from exc
    except (FileNotDecryptedError, DependencyError) as exc:
        raise PdfInputError("This PDF is encrypted. Upload an unlocked copy.") from exc
    except Exception as exc:
        # Invalid PDFs can surface low-level decoding errors as well as PdfReadError.
        raise PdfInputError("This file could not be read as a PDF. Try another copy.") from exc

    if not pages:
        raise PdfInputError("This PDF contains no pages.")
    return pages
