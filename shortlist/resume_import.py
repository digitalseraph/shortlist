"""Turn an uploaded resume into the plain text the ranking pipeline reads.

`embed_resume_cached` calls `read_text()` on the stored file, so every accepted
format is normalised to text here. PDF extraction is lossy - the caller is
expected to show the result for review before saving it.
"""

from __future__ import annotations

import io
from pathlib import Path

MAX_RESUME_BYTES = 2 * 1024 * 1024

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # a .docx is a zip container


class UnsupportedResumeError(ValueError):
    """The upload is not a resume we can read."""


def _as_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedResumeError("file is not valid UTF-8 text") from exc


def _from_pdf(data: bytes) -> str:
    if not data.startswith(_PDF_MAGIC):
        raise UnsupportedResumeError("file does not look like a PDF")
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _from_docx(data: bytes) -> str:
    if not data.startswith(_ZIP_MAGIC):
        raise UnsupportedResumeError("file does not look like a .docx")
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extract_text(data: bytes, filename: str) -> str:
    """Extract resume text, validating by extension and by leading bytes."""
    if len(data) > MAX_RESUME_BYTES:
        raise UnsupportedResumeError(f"file is larger than {MAX_RESUME_BYTES // (1024 * 1024)} MB")
    suffix = Path(filename).suffix.lower()
    if suffix in (".md", ".txt"):
        return _as_text(data)
    if suffix == ".pdf":
        return _from_pdf(data)
    if suffix == ".docx":
        return _from_docx(data)
    raise UnsupportedResumeError(f"unsupported file type {suffix or filename!r}")
