"""PDF parsing: per-page text extraction, preserving page numbers
(docs/03-TRD.md step 5: "Parse PDF per page ... Reject empty/scanned
content with a useful error")."""
from io import BytesIO

import pypdf


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_pdf(data: bytes) -> list[dict]:
    """Returns [{"heading": None, "page": int, "text": str}, ...] for each
    page with extractable text. Raises ParseError if the PDF has no
    extractable text at all (e.g. a scanned image-only PDF) -- callers
    must never turn this into an empty 'ready' source."""
    try:
        reader = pypdf.PdfReader(BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- pypdf raises several distinct exception types
        raise ParseError("pdf_unreadable", "Could not open this PDF file.") from exc

    if reader.is_encrypted:
        raise ParseError("pdf_encrypted", "Encrypted PDFs are not supported.")

    blocks = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append({"heading": None, "page": i, "text": text})

    if not blocks:
        raise ParseError("pdf_no_extractable_text", "This PDF has no extractable text -- it may be a scanned image.")

    return blocks
