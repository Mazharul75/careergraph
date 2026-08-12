"""Document text extraction.

Pure functions over ``bytes``. No database, no network, no filesystem — so every branch is
unit-testable in milliseconds with an in-memory fixture, and the same code runs identically in
a test, in the API, and in a worker.
"""

from __future__ import annotations

import io
import re
from enum import StrEnum

import pypdf
from docx import Document

# Content types we accept. `.doc` (the pre-2007 binary format) is deliberately excluded: parsing
# it needs a heavyweight dependency, and failing loudly beats silently extracting garbage.
PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Magic bytes. Content-Type and file extension are both supplied by the client and can say
# anything; the first bytes of the file cannot. This is what stops an executable being uploaded
# as "resume.pdf" and reaching a parser that was never designed to see it.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # .docx is a zip archive

# Collapse runs of whitespace but keep paragraph breaks: PDF extraction produces ragged spacing,
# and downstream skill matching (Phase 2b) works better on normalised text.
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+(\n|$)")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


class DocumentKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"


class ExtractionError(Exception):
    """The document could not be read.

    Carries a message safe to show a user: no file paths, no library versions, no traceback.
    """


def detect_kind(data: bytes) -> DocumentKind:
    """Identify a document by its leading bytes, ignoring what the client claimed."""
    if data.startswith(_PDF_MAGIC):
        return DocumentKind.PDF
    if data.startswith(_ZIP_MAGIC):
        return DocumentKind.DOCX
    raise ExtractionError("File is not a readable PDF or DOCX document.")


def normalise(text: str) -> str:
    """Tidy extracted text without destroying its structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Non-breaking spaces and soft hyphens are endemic in PDFs and break naive word matching.
    text = text.replace("\xa0", " ").replace("­", "")
    text = _MULTI_SPACE.sub(" ", text)
    text = _TRAILING_SPACE.sub(r"\1", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Some PDFs are encrypted with an empty owner password and open fine.
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ExtractionError("This PDF is password protected.") from exc

        pages = [page.extract_text() or "" for page in reader.pages]
    except ExtractionError:
        raise
    except Exception as exc:
        # pypdf raises a wide variety of types on malformed input. The message is deliberately
        # generic; the real exception is logged by the caller, not returned to the user.
        raise ExtractionError("This PDF could not be read. It may be corrupt.") from exc

    return normalise("\n\n".join(pages))


def extract_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        blocks = [paragraph.text for paragraph in document.paragraphs]

        # Skills and dates commonly live in tables, which `paragraphs` does not include.
        # Missing them would silently halve the useful text on a large minority of resumes.
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))
    except Exception as exc:
        raise ExtractionError("This DOCX could not be read. It may be corrupt.") from exc

    return normalise("\n".join(blocks))


def extract_text(data: bytes) -> tuple[DocumentKind, str]:
    """Extract text from an uploaded document.

    Returns the detected kind alongside the text so the caller can record what was actually
    parsed, rather than what the upload claimed to be.
    """
    if not data:
        raise ExtractionError("File is empty.")

    kind = detect_kind(data)
    text = extract_pdf(data) if kind is DocumentKind.PDF else extract_docx(data)

    if not text.strip():
        # A scanned resume is images with no text layer. Saying so is far more useful than
        # reporting success and producing an empty skill profile.
        raise ExtractionError(
            "No text could be extracted. If this is a scanned document, "
            "please upload a text-based PDF or DOCX instead."
        )

    return kind, text
