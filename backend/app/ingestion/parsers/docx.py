"""DOCX parsing: paragraphs and tables, in document order (D3.1: tables
as Markdown; docs/03-TRD.md step 5: "DOCX paragraphs and tables")."""
from io import BytesIO

import docx


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _table_to_markdown(table) -> str:
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(row) + " |" for row in rows]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def parse_docx(data: bytes) -> list[dict]:
    """Returns [{"heading": str|None, "page": None, "text": str}, ...] in
    document order (paragraphs and tables interleaved as they actually
    appear, via python-docx's body-element iteration -- not all
    paragraphs followed by all tables). DOCX has no reliable page concept
    at the text-extraction layer, so page is always None here -- chunks
    carry heading references instead."""
    try:
        document = docx.Document(BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- python-docx raises several distinct exception types
        raise ParseError("docx_unreadable", "Could not open this DOCX file.") from exc

    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    current_heading = None

    for element in document.iter_inner_content():
        if isinstance(element, Paragraph):
            text = element.text.strip()
            if not text:
                continue
            style_name = (element.style.name or "").lower() if element.style else ""
            if style_name.startswith("heading"):
                current_heading = text
                continue
            blocks.append({"heading": current_heading, "page": None, "text": text})
        elif isinstance(element, Table):
            markdown = _table_to_markdown(element)
            if markdown:
                blocks.append({"heading": current_heading, "page": None, "text": markdown})

    if not blocks:
        raise ParseError("docx_empty", "This document has no extractable text.")

    return blocks
