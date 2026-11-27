"""Per-bot config knobs for the rag_v2 pipeline (launch/05-RAG-V2-SPEC.md
section 5), loaded from `bots.draft_config` (preview) or the active
publication's `config_snapshot` (visitor-facing) -- the same two sources
`app/chat/pipeline.py` already reads for v1, just with more keys.
"""
from dataclasses import dataclass


@dataclass
class RagConfig:
    max_loop_iterations: int = 3
    rerank_top_k: int = 8
    min_rerank_score: float = 0.0  # calibrated per-bot by eval (D3.7/D4.4); 0.0 = no floor until then
    verifier_enabled: bool = True
    abstention_text: str = "I couldn't find an answer to that in the available information."
    cite_style: str = "numeric"  # numeric | footnote | none
    pii_redaction: bool = False
    follow_ups_count: int = 3

    @classmethod
    def from_bot_config(cls, config: dict) -> "RagConfig":
        rag = (config or {}).get("rag") or {}
        defaults = cls()
        return cls(
            max_loop_iterations=int(rag.get("max_loop_iterations", defaults.max_loop_iterations)),
            rerank_top_k=int(rag.get("rerank_top_k", defaults.rerank_top_k)),
            min_rerank_score=float(rag.get("min_rerank_score", defaults.min_rerank_score)),
            verifier_enabled=bool(rag.get("verifier_enabled", defaults.verifier_enabled)),
            abstention_text=config.get("fallback_message") or rag.get("abstention_text", defaults.abstention_text),
            cite_style=rag.get("cite_style", defaults.cite_style),
            pii_redaction=bool(rag.get("pii_redaction", defaults.pii_redaction)),
            follow_ups_count=int(rag.get("follow_ups_count", defaults.follow_ups_count)),
        )
