"""Plain text / Markdown / FAQ parsing: heading-aware splitting for
Markdown, paragraph splitting for plain text, Q/A pairing for FAQs
(docs/03-TRD.md step 5: "plain text headings")."""
import re

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_text(content: str, is_markdown: bool = False) -> list[dict]:
    """Returns [{"heading": str|None, "page": None, "text": str}, ...]."""
    content = content.strip()
    if not content:
        raise ParseError("empty_content", "This text source has no content.")

    blocks = []
    current_heading = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if is_markdown:
            match = _MD_HEADING_RE.match(line)
            if match:
                current_heading = match.group(2).strip()
                continue
        blocks.append({"heading": current_heading, "page": None, "text": line})

    if not blocks:
        raise ParseError("empty_content", "This text source has no content.")

    return blocks


def parse_faqs(items: list[dict]) -> list[dict]:
    """items: [{"q": str, "a": str}, ...]. Returns one block per Q/A pair
    so each FAQ entry can become its own chunk rather than being merged
    with neighbors during chunking."""
    blocks = []
    for item in items:
        question = (item.get("q") or "").strip()
        answer = (item.get("a") or "").strip()
        if not question or not answer:
            continue
        blocks.append({"heading": question, "page": None, "text": f"{question}\n{answer}"})

    if not blocks:
        raise ParseError("empty_content", "This FAQ source has no valid question/answer pairs.")

    return blocks
