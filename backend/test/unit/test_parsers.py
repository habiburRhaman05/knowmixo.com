"""Parser unit tests -- no network, no DB. PDF coverage here is
deliberately limited to the negative (no-extractable-text) case, which is
the acceptance-critical path (docs/02-ACCEPTANCE.md: "Scanned PDFs show a
clear unsupported-file message"). A positive real-text PDF fixture needs
an actual sample file and is tracked for the test-fixture pass rather than
a hand-crafted raw PDF byte string here, which would be fragile across
pypdf versions.
"""
from io import BytesIO

import docx
import pypdf
import pytest

from app.ingestion.parsers.docx import ParseError as DocxParseError
from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.html import ParseError as HtmlParseError
from app.ingestion.parsers.html import parse_html
from app.ingestion.parsers.pdf import ParseError as PdfParseError
from app.ingestion.parsers.pdf import parse_pdf
from app.ingestion.parsers.text import ParseError as TextParseError
from app.ingestion.parsers.text import parse_faqs, parse_text


# --- PDF ---


def test_blank_pdf_raises_no_extractable_text():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)

    with pytest.raises(PdfParseError) as exc_info:
        parse_pdf(buf.getvalue())
    assert exc_info.value.code == "pdf_no_extractable_text"


def test_garbage_bytes_raise_unreadable():
    with pytest.raises(PdfParseError) as exc_info:
        parse_pdf(b"this is not a real pdf file")
    assert exc_info.value.code == "pdf_unreadable"


# --- DOCX ---


def test_docx_paragraphs_and_headings():
    document = docx.Document()
    document.add_heading("Chapter One", level=1)
    document.add_paragraph("First paragraph under chapter one.")
    document.add_paragraph("Second paragraph, still under chapter one.")
    buf = BytesIO()
    document.save(buf)

    blocks = parse_docx(buf.getvalue())
    assert len(blocks) == 2
    assert all(b["heading"] == "Chapter One" for b in blocks)
    assert blocks[0]["text"] == "First paragraph under chapter one."


def test_docx_table_rows_become_blocks():
    document = docx.Document()
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Name"
    table.rows[0].cells[1].text = "Price"
    buf = BytesIO()
    document.save(buf)

    blocks = parse_docx(buf.getvalue())
    assert any("Name" in b["text"] and "Price" in b["text"] for b in blocks)


def test_empty_docx_raises_parse_error():
    document = docx.Document()
    buf = BytesIO()
    document.save(buf)

    with pytest.raises(DocxParseError) as exc_info:
        parse_docx(buf.getvalue())
    assert exc_info.value.code == "docx_empty"


def test_garbage_bytes_docx_unreadable():
    with pytest.raises(DocxParseError) as exc_info:
        parse_docx(b"not a zip file at all")
    assert exc_info.value.code == "docx_unreadable"


# --- HTML ---


def test_html_extracts_headings_and_paragraphs():
    html = """
    <html><head><title>My Page</title></head>
    <body>
      <nav>Skip this navigation</nav>
      <h1>Welcome</h1>
      <p>This is the first paragraph.</p>
      <h2>Details</h2>
      <p>This is a detail paragraph.</p>
      <script>console.log('skip this too')</script>
    </body></html>
    """
    result = parse_html(html)
    assert result["title"] == "My Page"
    texts = [b["text"] for b in result["blocks"]]
    assert "This is the first paragraph." in texts
    assert "This is a detail paragraph." in texts
    assert not any("navigation" in t.lower() for t in texts)
    assert not any("console.log" in t for t in texts)

    detail_block = next(b for b in result["blocks"] if b["text"] == "This is a detail paragraph.")
    assert detail_block["heading"] == "Details"


def test_html_with_no_content_raises_parse_error():
    html = "<html><body><script>only script here</script></body></html>"
    with pytest.raises(HtmlParseError):
        parse_html(html)


def test_html_falls_back_to_title_fallback_when_no_title_tag():
    html = "<html><body><p>Some content.</p></body></html>"
    result = parse_html(html, title_fallback="Fallback Title")
    assert result["title"] == "Fallback Title"


# --- Text / Markdown / FAQ ---


def test_markdown_headings_split_blocks():
    content = "# Heading One\nFirst line.\n## Heading Two\nSecond line."
    blocks = parse_text(content, is_markdown=True)
    assert blocks[0]["heading"] == "Heading One"
    assert blocks[0]["text"] == "First line."
    assert blocks[1]["heading"] == "Heading Two"
    assert blocks[1]["text"] == "Second line."


def test_plain_text_has_no_headings():
    content = "Just a line.\nAnother line."
    blocks = parse_text(content, is_markdown=False)
    assert all(b["heading"] is None for b in blocks)


def test_empty_text_raises_parse_error():
    with pytest.raises(TextParseError):
        parse_text("   ", is_markdown=False)


def test_faq_pairs_become_blocks():
    items = [{"q": "What is your refund policy?", "a": "30 days, no questions asked."}]
    blocks = parse_faqs(items)
    assert len(blocks) == 1
    assert blocks[0]["heading"] == "What is your refund policy?"
    assert "30 days" in blocks[0]["text"]


def test_faq_skips_incomplete_pairs():
    items = [{"q": "", "a": "orphan answer"}, {"q": "orphan question", "a": ""}]
    with pytest.raises(TextParseError):
        parse_faqs(items)
