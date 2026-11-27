"""HTML main-content extraction for URL-imported pages (D3.1: table
detection; docs/03-TRD.md step 5: "HTML main content")."""
from bs4 import BeautifulSoup


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "svg", "form", "aside")
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_TEXT_TAGS = ("p", "li")


def _table_to_markdown(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(("th", "td"))]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(row) + " |" for row in rows]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def parse_html(html: str, title_fallback: str = "Untitled page") -> dict:
    """Returns {"title": str, "blocks": [{"heading": str|None, "page": None, "text": str}, ...]}.
    Tables are extracted as Markdown and excluded from the heading/
    paragraph pass below (a table's own cells would otherwise also be
    walked as nested <p>/<li> elements, duplicating their content)."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    title = title_fallback
    if soup.title and soup.title.string:
        stripped = soup.title.string.strip()
        if stripped:
            title = stripped

    body = soup.body or soup

    blocks = []
    current_heading = None
    for element in body.find_all(_HEADING_TAGS + _TEXT_TAGS + ("table",)):
        if element.find_parent("table"):
            continue  # a <p>/<li>/heading nested inside a table is part of that table's own cell text
        if element.name == "table":
            markdown = _table_to_markdown(element)
            if markdown:
                blocks.append({"heading": current_heading, "page": None, "text": markdown})
            continue
        text = element.get_text(separator=" ", strip=True)
        if not text:
            continue
        if element.name in _HEADING_TAGS:
            current_heading = text
            continue
        blocks.append({"heading": current_heading, "page": None, "text": text})

    if not blocks:
        raise ParseError("html_no_content", "No extractable text content found on this page.")

    return {"title": title, "blocks": blocks}
