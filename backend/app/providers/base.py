"""Provider interfaces (ADR 004). Every chat/embedding/rerank provider
implements these Protocols so `app/providers/router.py` can treat them
interchangeably -- switching the primary provider, or adding a paid one
later (launch/16-PAID-MODEL-SWITCH.md), is a config change, never a code
change to the call sites in app/chat/*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a given (provider, model) pair can actually do. The router
    uses this to decide whether a candidate in the fallback chain is even
    eligible for a given call, not just to document it."""

    streaming: bool = True
    tool_calling: bool = False
    json_mode: bool = False
    context_window_tokens: int = 8192
    languages: tuple[str, ...] = ("en",)
    # Per ADR 004 / launch/04-ARCHITECTURE.md: whether the provider's
    # terms, as last verified, permit commercial use of outputs and
    # whether they train on submitted input. Both must be checked against
    # current provider docs before a provider is ever added to a live
    # fallback chain -- see launch/03-RISKS-AND-BLOCKERS.md EX-list.
    commercial_use_verified: bool = False
    trains_on_input: bool = True  # fail safe: assume yes until verified False
    cost_per_1k_input_cents: float = 0.0
    cost_per_1k_output_cents: float = 0.0


@runtime_checkable
class ChatProvider(Protocol):
    name: str
    model: str
    capabilities: ProviderCapabilities

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yields text deltas. Raises ProviderError/ProviderQuotaError on
        failure -- never silently returns an empty stream."""
        ...

    async def complete_json(self, messages: list[dict], max_tokens: int = 300) -> dict:
        """Non-streaming JSON-mode call for internal pipeline decisions
        (intent/rewrite/grade/verify -- never shown to the visitor).
        Raises ProviderError/ProviderQuotaError on failure."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


@runtime_checkable
class RerankProvider(Protocol):
    name: str
    model: str

    def rerank(self, query: str, passages: list[str], top_k: int) -> list[tuple[int, float]]:
        """Returns (original_index, score) pairs, sorted best-first."""
        ...


class ProviderError(Exception):
    """Base for any provider-adapter failure. `code` matches the stable
    error_code enum surfaced to clients (docs/16 'Error-code stability')."""

    def __init__(self, code: str, provider: str | None = None):
        super().__init__(code)
        self.code = code
        self.provider = provider


class ProviderQuotaError(ProviderError):
    def __init__(self, provider: str, retry_after_seconds: int = 60):
        super().__init__("quota_exhausted", provider)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ProviderError):
    """Transient: network/5xx/timeout. The router tries the next provider
    in the fallback chain rather than failing the whole request."""

    def __init__(self, provider: str, reason: str = "provider_unavailable"):
        super().__init__(reason, provider)


class AllProvidersExhaustedError(ProviderError):
    """Every provider in the chain failed or is ineligible. The caller
    (app/chat/rag_v2/pipeline.py) maps this to a 503 with Retry-After,
    never a silent paid-model fallback outside the configured chain."""

    def __init__(self, attempted: list[str]):
        super().__init__("all_providers_exhausted")
        self.attempted = attempted
