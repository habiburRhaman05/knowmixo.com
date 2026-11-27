"""Parser unit tests -- no network, no DB. Positive-path PDF fixtures
(D3.1: pdfplumber for tables + headings) are built with reportlab so
heading font sizes and table structure are under test control, rather
than depending on a committed sample file."""
from io import BytesIO

import docx
import pypdf
import pytest

from app.ingestion.parsers.csv_source import ParseError as CsvParseError
from app.ingestion.parsers.csv_source import parse_csv
from app.ingestion.parsers.docx import ParseError as DocxParseError
from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.html import ParseError as HtmlParseError
from app.ingestion.parsers.html import parse_html
from app.ingestion.parsers.pdf import ParseError as PdfParseError
from app.ingestion.parsers.pdf import parse_pdf
from app.ingestion.parsers.text import ParseError as TextParseError
from app.ingestion.parsers.text import parse_faqs, parse_text


def _build_pdf(story) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate

    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=letter).build(story)
    return buf.getvalue()


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


def test_pdf_large_font_lines_become_headings_not_blocks():
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph

    styles = getSampleStyleSheet()
    pdf_bytes = _build_pdf(
        [
            Paragraph("Pricing Overview", styles["Heading1"]),
            Paragraph("This is the body text explaining our pricing.", styles["Normal"]),
            Paragraph("Support Hours", styles["Heading1"]),
            Paragraph("We are open 9 to 5 on weekdays.", styles["Normal"]),
        ]
    )

    blocks = parse_pdf(pdf_bytes)
    texts = [b["text"] for b in blocks]
    assert "Pricing Overview" not in texts  # the heading itself is context, not a block
    assert "This is the body text explaining our pricing." in texts
    assert next(b for b in blocks if "pricing" in b["text"]).get("heading") == "Pricing Overview"
    assert next(b for b in blocks if "9 to 5" in b["text"]).get("heading") == "Support Hours"


def test_pdf_bordered_table_extracted_as_markdown():
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Table, TableStyle

    styles = getSampleStyleSheet()
    table = Table([["Plan", "Price"], ["Starter", "$29"], ["Growth", "$99"]])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    pdf_bytes = _build_pdf([Paragraph("Plans", styles["Heading1"]), table])

    blocks = parse_pdf(pdf_bytes)
    table_block = next(b for b in blocks if b["text"].startswith("|"))
    assert "Plan" in table_block["text"] and "Price" in table_block["text"]
    assert "Starter" in table_block["text"] and "$29" in table_block["text"]
    assert table_block["text"].count("\n") == 3  # header + separator + 2 data rows
    assert table_block["heading"] == "Plans"


def test_pdf_page_number_tracked_across_pages():
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph

    styles = getSampleStyleSheet()
    pdf_bytes = _build_pdf(
        [
            Paragraph("First page text.", styles["Normal"]),
            PageBreak(),
            Paragraph("Second page text.", styles["Normal"]),
        ]
    )

    blocks = parse_pdf(pdf_bytes)
    assert next(b for b in blocks if "First" in b["text"])["page"] == 1
    assert next(b for b in blocks if "Second" in b["text"])["page"] == 2


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


def test_docx_table_rendered_as_markdown():
    document = docx.Document()
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Name"
    table.rows[0].cells[1].text = "Price"
    table.rows[1].cells[0].text = "Widget"
    table.rows[1].cells[1].text = "$9"
    buf = BytesIO()
    document.save(buf)

    blocks = parse_docx(buf.getvalue())
    table_block = next(b for b in blocks if b["text"].startswith("|"))
    assert "Name" in table_block["text"] and "Price" in table_block["text"]
    assert "Widget" in table_block["text"] and "$9" in table_block["text"]
    assert table_block["text"].count("\n") == 2  # header + separator + 1 data row


def test_docx_preserves_document_order_of_paragraphs_and_tables():
    document = docx.Document()
    document.add_paragraph("Before the table.")
    table = document.add_table(rows=1, cols=1)
    table.rows[0].cells[0].text = "In the table"
    document.add_paragraph("After the table.")
    buf = BytesIO()
    document.save(buf)

    blocks = parse_docx(buf.getvalue())
    texts = [b["text"] for b in blocks]
    assert texts.index("Before the table.") < next(i for i, t in enumerate(texts) if t.startswith("|"))
    assert next(i for i, t in enumerate(texts) if t.startswith("|")) < texts.index("After the table.")


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


def test_html_table_extracted_as_markdown_in_document_order():
    html = """
    <html><body>
      <h1>Pricing</h1>
      <p>See our plans below.</p>
      <table>
        <tr><th>Plan</th><th>Price</th></tr>
        <tr><td>Starter</td><td>$29</td></tr>
      </table>
      <p>Contact us for enterprise pricing.</p>
    </body></html>
    """
    result = parse_html(html)
    texts = [b["text"] for b in result["blocks"]]
    table_idx = next(i for i, t in enumerate(texts) if t.startswith("|"))
    assert texts.index("See our plans below.") < table_idx < texts.index("Contact us for enterprise pricing.")
    table_text = texts[table_idx]
    assert "Plan" in table_text and "Price" in table_text and "Starter" in table_text and "$29" in table_text
    assert result["blocks"][table_idx]["heading"] == "Pricing"
    # Table cell contents must not ALSO appear as separate paragraph blocks.
    assert not any(t == "Starter" or t == "$29" for t in texts)


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


# --- CSV ---


def test_csv_each_row_becomes_its_own_block():
    data = b"Name,Price\nWidget,$9\nGadget,$19\n"
    blocks = parse_csv(data)
    assert len(blocks) == 2
    assert "Name" in blocks[0]["text"] and "Widget" in blocks[0]["text"] and "$9" in blocks[0]["text"]
    assert "Name" in blocks[1]["text"] and "Gadget" in blocks[1]["text"] and "$19" in blocks[1]["text"]


def test_csv_header_only_raises_parse_error():
    with pytest.raises(CsvParseError) as exc_info:
        parse_csv(b"Name,Price\n")
    assert exc_info.value.code == "csv_header_only"


def test_csv_empty_file_raises_parse_error():
    with pytest.raises(CsvParseError) as exc_info:
        parse_csv(b"")
    assert exc_info.value.code == "csv_empty"


def test_csv_blank_header_cells_get_placeholder_names():
    data = b"Name,,Price\nWidget,extra,$9\n"
    blocks = parse_csv(data)
    assert "column_2" in blocks[0]["text"]


def test_csv_handles_utf8_bom():
    data = "Name,Price\nWidget,$9\n".encode("utf-8-sig")
    blocks = parse_csv(data)
    assert "Name" in blocks[0]["text"]  # BOM must not leak into the first header cell
