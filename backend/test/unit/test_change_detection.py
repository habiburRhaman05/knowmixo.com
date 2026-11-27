"""app/ingestion/change_detection.py -- no real network call; checksum_fn
is injected (docs/11-AGENT-RULES rule 6)."""
import hashlib

from app.ingestion import change_detection
from app.ingestion.change_detection import has_changed


def test_fetch_checksum_hashes_the_response_body(monkeypatch):
    class _FakeResponse:
        content = b"hello world"

    monkeypatch.setattr(change_detection, "ssrf_fetch", lambda url: _FakeResponse())
    assert change_detection.fetch_checksum("https://example.com") == hashlib.sha256(b"hello world").hexdigest()


def test_no_prior_checksum_counts_as_changed():
    document = {"source_url": "https://example.com", "source_checksum": None}
    changed, new_checksum = has_changed(document, checksum_fn=lambda url: "abc123")
    assert changed is True
    assert new_checksum == "abc123"


def test_same_checksum_is_not_changed():
    document = {"source_url": "https://example.com", "source_checksum": "abc123"}
    changed, new_checksum = has_changed(document, checksum_fn=lambda url: "abc123")
    assert changed is False
    assert new_checksum == "abc123"


def test_different_checksum_is_changed():
    document = {"source_url": "https://example.com", "source_checksum": "abc123"}
    changed, new_checksum = has_changed(document, checksum_fn=lambda url: "def456")
    assert changed is True
    assert new_checksum == "def456"


def test_checksum_fn_receives_the_document_source_url():
    seen = []
    document = {"source_url": "https://example.com/page", "source_checksum": None}
    has_changed(document, checksum_fn=lambda url: seen.append(url) or "x")
    assert seen == ["https://example.com/page"]
