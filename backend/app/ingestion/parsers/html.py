"""HTML main-content extraction for URL-imported pages
(docs/03-TRD.md step 5: "HTML main content")."""
from bs4 import BeautifulSoup


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "svg", "form", "aside")
_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_TEXT_TAGS = ("p", "li")


def parse_html(html: str, title_fallback: str = "Untitled page") -> dict:
    """Returns {"title": str, "blocks": [{"heading": str|None, "page": None, "text": str}, ...]}."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    title = title_fallback
    if soup.title and soup.title.string:
        stripped = soup.title.string.strip()
        if stripped:
            title = stripped

    blocks = []
    current_heading = None
    body = soup.body or soup
    for element in body.find_all(_HEADING_TAGS + _TEXT_TAGS):
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
