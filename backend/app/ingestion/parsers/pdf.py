"""PDF parsing via pdfplumber: per-page text with layout-inferred
headings, plus native table extraction as Markdown (D3.1,
docs/03-TRD.md step 5: "Parse PDF per page ... Reject empty/scanned
content with a useful error").

PDF has no semantic heading markup -- "heading" is inferred from font
size relative to the document's own body-text size (the standard
heuristic for this; there is no more reliable signal available from the
format itself). Table cells are excluded from the plain-text pass (they
would otherwise appear twice: once as a table block, once as flowing
text) by filtering out words whose bounding box falls inside a detected
table's bounding box.
"""
import statistics
from collections import Counter
from io import BytesIO

import pdfplumber


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_HEADING_SIZE_RATIO = 1.15  # a line's avg font size must exceed body size by this factor
_Y_TOLERANCE = 3  # points; words within this of each other's "top" are the same line


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    cells = [[(c or "").strip() for c in row] for row in rows]
    cells = [row for row in cells if any(row)]
    if not cells:
        return ""
    width = max(len(row) for row in cells)
    cells = [row + [""] * (width - len(row)) for row in cells]
    lines = ["| " + " | ".join(row) + " |" for row in cells]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def _word_in_any_bbox(word: dict, bboxes: list[tuple[float, float, float, float]]) -> bool:
    wx0, wtop, wx1, wbottom = word["x0"], word["top"], word["x1"], word["bottom"]
    for x0, top, x1, bottom in bboxes:
        if wx0 >= x0 - 1 and wx1 <= x1 + 1 and wtop >= top - 1 and wbottom <= bottom + 1:
            return True
    return False


def _group_into_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= _Y_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _body_size(all_words: list[dict]) -> float:
    sizes = [round(w["size"], 1) for w in all_words if w.get("size")]
    if not sizes:
        return 0.0
    return Counter(sizes).most_common(1)[0][0]


def parse_pdf(data: bytes) -> list[dict]:
    """Returns [{"heading": str|None, "page": int, "text": str}, ...] for
    each page with extractable text, plus one block per detected table
    (rendered as Markdown). Raises ParseError if the PDF has no
    extractable text at all (e.g. a scanned image-only PDF) -- callers
    must never turn this into an empty 'ready' source."""
    try:
        pdf = pdfplumber.open(BytesIO(data))
    except Exception as exc:  # noqa: BLE001 -- pdfplumber/pdfminer raise several distinct exception types
        raise ParseError("pdf_unreadable", "Could not open this PDF file.") from exc

    try:
        if getattr(pdf, "is_encrypted", False):
            raise ParseError("pdf_encrypted", "Encrypted PDFs are not supported.")

        all_words = []
        for page in pdf.pages:
            all_words.extend(page.extract_words(extra_attrs=["size"]))
        body_size = _body_size(all_words)

        blocks: list[dict] = []
        current_heading = None

        for page_number, page in enumerate(pdf.pages, start=1):
            # Lines-based detection only (pdfplumber's default): reliable
            # for genuinely ruled/bordered tables, which is how real
            # contracts, pricing sheets and policy documents render
            # tables in practice. A text-position-based strategy can
            # catch borderless tables too, but was tried and rejected --
            # on a whole page with no real ruled table, it misidentifies
            # ordinary paragraph text as one giant table. A borderless
            # table just falls through to normal line extraction below
            # (content preserved, not lost -- just not Markdown-shaped).
            tables = [t for t in page.find_tables() if len(t.rows) >= 2 and len(t.rows[0].cells) >= 2]
            table_bboxes = [t.bbox for t in tables]

            # Tables and text lines are merged into one list sorted by
            # vertical position so heading context tracks true reading
            # order (a table that appears right after a heading should
            # carry that heading, not whatever was last set on a
            # previous page).
            items: list[tuple[float, str, object]] = []
            for table in tables:
                markdown = _table_to_markdown(table.extract())
                if markdown:
                    items.append((table.bbox[1], "table", markdown))

            words = [w for w in page.extract_words(extra_attrs=["size"]) if not _word_in_any_bbox(w, table_bboxes)]
            for line_words in _group_into_lines(words):
                text = " ".join(w["text"] for w in line_words).strip()
                if not text:
                    continue
                avg_size = statistics.mean(w.get("size", body_size) for w in line_words)
                kind = "heading" if body_size and avg_size >= body_size * _HEADING_SIZE_RATIO else "text"
                items.append((line_words[0]["top"], kind, text))

            for _, kind, text in sorted(items, key=lambda item: item[0]):
                if kind == "heading":
                    current_heading = text
                    continue
                blocks.append({"heading": current_heading, "page": page_number, "text": text})

        if not blocks:
            raise ParseError("pdf_no_extractable_text", "This PDF has no extractable text -- it may be a scanned image.")

        return blocks
    finally:
        pdf.close()
