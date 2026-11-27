"""Change detection for URL/crawl-page sources (D3.5 scaffolding,
launch/13-SPRINT-10-DAYS.md). Lets a periodic sweep re-check an external
source and only trigger re-ingestion when the fetched content actually
changed -- re-embedding unchanged content on every sweep would waste
provider quota for no benefit.

Scaffolding only: the owner-facing UI/API for setting `check_interval_hours`
per source is Day 7; nothing here is wired to an endpoint yet.
"""
import hashlib

from app.security.ssrf_http import fetch as ssrf_fetch


def fetch_checksum(url: str) -> str:
    """Fetches `url` through the same SSRF-validated path ingestion itself
    uses (app/ingestion/pipeline.py's `_extract_blocks`) and returns a
    sha256 hex digest of the raw response body. Raises SSRFBlocked /
    httpx errors exactly as `ssrf_fetch` does -- callers handle those the
    same way the ingestion pipeline already does."""
    response = ssrf_fetch(url)
    return hashlib.sha256(response.content).hexdigest()


def has_changed(document: dict, checksum_fn=fetch_checksum) -> tuple[bool, str]:
    """Returns (changed, new_checksum). `document` needs `source_url` and
    `source_checksum` (None before the first check -- always reported as
    changed, so the first sweep establishes a baseline)."""
    new_checksum = checksum_fn(document["source_url"])
    changed = document["source_checksum"] != new_checksum
    return changed, new_checksum
