"""DOCX parsing: paragraphs and tables, in document order
(docs/03-TRD.md step 5: "DOCX paragraphs and tables")."""
from io import BytesIO

import docx


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_docx(data: bytes) -> list[dict]:
    """Returns [{"heading": str|None, "page": None, "text": str}, ...].
    DOCX has no reliable page concept at the text-extraction layer, so
    page is always None here -- chunks carry heading references instead."""
    try:
        document = docx.Document(BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- python-docx raises several distinct exception types
        raise ParseError("docx_unreadable", "Could not open this DOCX file.") from exc

    blocks = []
    current_heading = None

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "").lower() if para.style else ""
        if style_name.startswith("heading"):
            current_heading = text
            continue
        blocks.append({"heading": current_heading, "page": None, "text": text})

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append({"heading": current_heading, "page": None, "text": " | ".join(cells)})

    if not blocks:
        raise ParseError("docx_empty", "This document has no extractable text.")

    return blocks
