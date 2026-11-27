"""Cloudflare reranker adapter -- no live network call (docs/11-AGENT-RULES
rule 6). httpx.post is monkeypatched; the real response shape used here
was confirmed against a live call once, not guessed (see
app/providers/reranker.py's module docstring)."""
import httpx
import pytest

from app.jobs.runner import PermanentJobError, QuotaWaitError, TransientJobError
from app.providers.reranker import rerank


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}

    def json(self):
        return self._json


def _cloudflare_body(pairs: list[tuple[int, float]]) -> dict:
    return {"result": {"response": [{"id": i, "score": s} for i, s in pairs]}, "success": True}


def test_empty_passages_returns_empty_without_a_call(monkeypatch):
    called = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: called.append(1) or _FakeResponse(200))
    assert rerank("query", [], top_k=5) == []
    assert not called


def test_happy_path_returns_sorted_pairs_respecting_top_k(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, _cloudflare_body([(2, 0.9), (0, 0.5), (1, 0.1)])))
    result = rerank("q", ["a", "b", "c"], top_k=2)
    assert result == [(2, 0.9), (0, 0.5)]


def test_429_raises_quota_wait_with_retry_after(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(429, headers={"retry-after": "30"}))
    with pytest.raises(QuotaWaitError) as exc_info:
        rerank("q", ["a"], top_k=5)
    assert exc_info.value.retry_after_seconds == 30


def test_5xx_raises_transient(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(503))
    with pytest.raises(TransientJobError):
        rerank("q", ["a"], top_k=5)


def test_4xx_raises_permanent(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(422))
    with pytest.raises(PermanentJobError):
        rerank("q", ["a"], top_k=5)


def test_malformed_response_shape_raises_transient(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"unexpected": "shape"}))
    with pytest.raises(TransientJobError):
        rerank("q", ["a"], top_k=5)


def test_out_of_range_index_raises_transient(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, _cloudflare_body([(99, 0.9)])))
    with pytest.raises(TransientJobError):
        rerank("q", ["a", "b"], top_k=5)


def test_timeout_raises_transient(monkeypatch):
    def raise_timeout(*a, **k):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", raise_timeout)
    with pytest.raises(TransientJobError):
        rerank("q", ["a"], top_k=5)
