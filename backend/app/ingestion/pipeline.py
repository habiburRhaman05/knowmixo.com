"""Ingestion pipeline: validate -> extract -> chunk -> embed -> upsert ->
reconcile (docs/03-TRD.md steps 4-9). Called by the 'ingest_document'
executor inside the single transaction the executor holds for this
attempt -- see app/jobs/executors.py for why the whole attempt is one
atomic unit rather than incrementally committed per stage.

Embedding/vector-store calls are passed in as callables so tests can
inject fakes instead of hitting live providers (docs/11-AGENT-RULES.md
rule 6).
"""
import hashlib
import json
from pathlib import Path
from typing import Callable

from app.ingestion.chunker import chunk_blocks
from app.ingestion.parsers.docx import ParseError as DocxParseError
from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.html import ParseError as HtmlParseError
from app.ingestion.parsers.html import parse_html
from app.ingestion.parsers.pdf import ParseError as PdfParseError
from app.ingestion.parsers.pdf import parse_pdf
from app.ingestion.parsers.text import ParseError as TextParseError
from app.ingestion.parsers.text import parse_faqs, parse_text
from app.ingestion.tokenizer import count_tokens
from app.config import settings
from app.jobs.runner import PermanentJobError, TransientJobError
from app.providers.vector_store import deterministic_vector_id
from app.security.ssrf_http import SSRFBlocked
from app.security.ssrf_http import fetch as ssrf_fetch
from app.storage import local as storage

# Every parser/SSRF error below is a property of the input itself (a
# scanned PDF, an empty FAQ list, a blocked private-IP URL) -- retrying
# the exact same bytes will never produce a different outcome, so all of
# these must surface as PermanentJobError, not the generic transient
# retry path. Without this mapping, a scanned PDF would be retried 4
# times with backoff before going dead, contradicting docs/03-TRD.md:
# "Invalid input is permanently failed."
_PERMANENT_INPUT_ERRORS = (
    PdfParseError,
    DocxParseError,
    HtmlParseError,
    TextParseError,
    SSRFBlocked,
    json.JSONDecodeError,  # malformed FAQ JSON is also a property of the input, not transient
)


def _extract_blocks(document: dict) -> list[dict]:
    kind = document["kind"]

    try:
        if kind in ("url", "crawl_page"):
            response = ssrf_fetch(document["source_url"])
            parsed = parse_html(response.text, title_fallback=document["title"])
            return parsed["blocks"]

        raw_bytes = storage.read_file(document["storage_key"])
        suffix = Path(document["storage_key"]).suffix.lower()

        if suffix == ".pdf":
            return parse_pdf(raw_bytes)
        if suffix == ".docx":
            return parse_docx(raw_bytes)
        if suffix == ".json":  # FAQ sources are stored as a JSON Q/A array
            items = json.loads(raw_bytes.decode("utf-8"))
            return parse_faqs(items)
        if suffix in (".txt", ".md"):
            return parse_text(raw_bytes.decode("utf-8", errors="replace"), is_markdown=suffix == ".md")
    except _PERMANENT_INPUT_ERRORS as exc:
        raise PermanentJobError(getattr(exc, "code", "ingestion_input_invalid")) from exc

    raise PermanentJobError("unsupported_file_suffix")


def run_ingestion(
    conn,
    document: dict,
    document_version: dict,
    embed_fn: Callable[[list[str]], list[list[float]]],
    upsert_fn: Callable[..., int],
    reconcile_fn: Callable[[str, str, int], bool],
    heartbeat: Callable[[], bool],
) -> int:
    """Returns the number of chunks persisted and confirmed upserted.
    Raises TransientJobError/PermanentJobError/QuotaWaitError from the
    provider adapters on any failure; the executor's caller (loop.py)
    handles those by requeuing/dead-lettering the job."""
    blocks = _extract_blocks(document)
    heartbeat()

    try:
        chunks = chunk_blocks(blocks, count_tokens_fn=count_tokens)
    except ValueError as exc:  # "No chunks produced" -- also a property of the input, not transient
        raise PermanentJobError("no_chunks_produced") from exc
    heartbeat()

    texts = [c["text"] for c in chunks]
    vectors = embed_fn(texts)
    heartbeat()

    chunk_rows = []
    for chunk, vector in zip(chunks, vectors):
        vector_id = deterministic_vector_id(document["company_id"], document["id"], document_version["id"], chunk["ordinal"])
        checksum = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
        chunk_rows.append(
            {
                "ordinal": chunk["ordinal"],
                "page": chunk["page"],
                "heading": chunk["heading"],
                "text": chunk["text"],
                "vector": vector,
                "vector_id": vector_id,
                "checksum": checksum,
            }
        )

    for row in chunk_rows:
        conn.execute(
            """
            INSERT INTO chunks (version_id, ordinal, page, heading, text, vector_id, checksum)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (document_version["id"], row["ordinal"], row["page"], row["heading"], row["text"], row["vector_id"], row["checksum"]),
        )
    heartbeat()

    embedding_model_name = settings().embedding_model
    upserted_count = upsert_fn(
        bot_id=document["bot_id"],
        company_id=document["company_id"],
        document_id=document["id"],
        version_id=document_version["id"],
        embedding_model=embedding_model_name,
        chunks=chunk_rows,
    )
    if upserted_count != len(chunk_rows):
        raise TransientJobError("chunk_manifest_mismatch_upsert_response", stage="upsert")
    heartbeat()

    # Independent recount, not just trusting the upsert call's own report
    # -- this is the explicit "chunk manifest reconciliation" step.
    if not reconcile_fn(document["company_id"], document_version["id"], len(chunk_rows)):
        raise TransientJobError("chunk_manifest_mismatch_reconciliation", stage="finalize")

    return len(chunk_rows)
