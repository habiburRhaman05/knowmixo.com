"""app/chat/rag_v2/stages/rerank.py -- provider calls are monkeypatched
(docs/11-AGENT-RULES rule 6); the provider's own real-shape test lives in
test/unit/test_reranker.py."""
from app.chat.rag_v2 import base
from app.chat.rag_v2.stages import rerank as rerank_module
from app.jobs.runner import TransientJobError


def _passage(text: str) -> base.Passage:
    return base.Passage(
        chunk_id=text, document_id="doc", version_id="v1", title="Doc",
        page=None, heading=None, text=text, score_dense=0.5, score_fts=0.0, rrf=0.01,
    )


def test_empty_passages_returns_empty_without_a_call(monkeypatch):
    called = []
    monkeypatch.setattr(rerank_module, "rerank_provider", lambda *a, **k: called.append(1))
    assert rerank_module.rerank("q", []) == []
    assert not called


def test_reorders_and_sets_score_rerank(monkeypatch):
    passages = [_passage("a"), _passage("b"), _passage("c")]
    monkeypatch.setattr(rerank_module, "rerank_provider", lambda query, texts, top_k: [(2, 0.9), (0, 0.5)])

    result = rerank_module.rerank("q", passages, top_k=2)

    assert [p.chunk_id for p in result] == ["c", "a"]
    assert result[0].score_rerank == 0.9
    assert result[1].score_rerank == 0.5


def test_provider_failure_falls_back_to_incoming_order_truncated(monkeypatch):
    passages = [_passage("a"), _passage("b"), _passage("c")]

    def _fail(*a, **k):
        raise TransientJobError("rerank_provider_error", stage="rerank")

    monkeypatch.setattr(rerank_module, "rerank_provider", _fail)

    result = rerank_module.rerank("q", passages, top_k=2)

    assert [p.chunk_id for p in result] == ["a", "b"]
    assert all(p.score_rerank is None for p in result)
