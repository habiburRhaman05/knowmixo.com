"""Typed exceptions for the rag_v2 pipeline, mapped to the stable
error_code/HTTP table in launch/05-RAG-V2-SPEC.md section 7. Only
failures that actually terminate the turn get an exception here --
Intent/Rewrite/Rerank timeouts are fallthroughs handled inline in their
own stage, never raised.
"""


class RagV2Error(Exception):
    def __init__(self, code: str, http_status: int, message: str, retry_after_seconds: int | None = None):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.retry_after_seconds = retry_after_seconds


class InputBlocked(RagV2Error):
    def __init__(self, message: str = "This message was blocked by input guardrails."):
        super().__init__("input_blocked", 400, message)


class RetrievalUnavailable(RagV2Error):
    def __init__(self, message: str = "Search is temporarily unavailable."):
        super().__init__("retrieval_unavailable", 503, message)


class LLMProviderError(RagV2Error):
    def __init__(self, message: str = "The assistant is temporarily unavailable."):
        super().__init__("llm_provider_error", 503, message)


class QuotaExhausted(RagV2Error):
    def __init__(self, message: str = "Quota exhausted.", retry_after_seconds: int = 60):
        super().__init__("quota_exhausted", 429, message, retry_after_seconds=retry_after_seconds)
