"""CSV parsing (D3.1: "csv: new parser"). Each row becomes its own block
-- a CSV is typically a list of independent records (a product catalog, a
pricing table, a store-locations list), so one big combined table would
be a single unsplittable chunk; one block per row lets the chunker group
them naturally and lets retrieval surface individual rows. Each block
carries its own header so a row remains self-describing even if
retrieved on its own, without its neighboring rows.
"""
import csv
import io


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _row_to_markdown(header: list[str], row: list[str]) -> str:
    width = len(header)
    row = (row + [""] * width)[:width]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
        "| " + " | ".join(row) + " |",
    ]
    return "\n".join(lines)


def parse_csv(data: bytes) -> list[dict]:
    """Returns [{"heading": None, "page": None, "text": str}, ...], one
    block per data row, each rendered as a self-contained 2-row Markdown
    table (header + that row)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("csv_undecodable", "This file is not valid UTF-8 text.") from exc

    try:
        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise ParseError("csv_unreadable", "Could not parse this CSV file.") from exc

    if not rows:
        raise ParseError("csv_empty", "This CSV file has no rows.")

    header, *data_rows = rows
    header = [h.strip() or f"column_{i + 1}" for i, h in enumerate(header)]

    if not data_rows:
        raise ParseError("csv_header_only", "This CSV file has a header row but no data rows.")

    blocks = [{"heading": None, "page": None, "text": _row_to_markdown(header, row)} for row in data_rows]
    return blocks
