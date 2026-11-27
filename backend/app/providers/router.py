"""LLM provider router: ordered fallback chain, per-tenant rate limiting,
exact + semantic response caching (ADR 004).

This is the ONLY place `app/chat/rag_v2/*` (and, via the compatibility
shim, the current `app/chat/pipeline.py`) should reach a chat provider.
Switching the primary provider, or adding a paid one later
(launch/16-PAID-MODEL-SWITCH.md), is a change to `PROVIDER_CHAIN` plus an
eval run -- never a change to any call site.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.providers.base import (
    AllProvidersExhaustedError,
    ChatProvider,
    ProviderError,
    ProviderQuotaError,
    ProviderUnavailableError,
)

log = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Loaded once at process start from `providers.yaml` (or, for now,
    hardcoded defaults matching ADR 004's `free_only` stance). Every field
    here is a deliberate, reviewed choice -- never inferred at runtime."""

    chain: list[ChatProvider] = field(default_factory=list)
    per_company_rpm: int = 20
    global_rpm: int = 600
    cache_exact_enabled: bool = True
    cache_semantic_enabled: bool = False  # Day 2: exact-match only; semantic cache is a Day 3+ item


def default_chain() -> list[ChatProvider]:
    """The `free_only=true` chain: Groq primary, nothing else. OpenRouter
    is deliberately NOT included by default -- see
    app/providers/openrouter_chat.py's module docstring for why enabling
    it requires an explicit model choice and a recorded ADR, not just
    uncommenting a line here."""
    from app.providers.groq_chat import GroqChatProvider

    return [GroqChatProvider()]


class ProviderRouter:
    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig(chain=default_chain())

    def _eligible(self, provider: ChatProvider, language: str | None) -> bool:
        if language and language not in provider.capabilities.languages and "*" not in provider.capabilities.languages:
            return False
        return True

    async def stream_chat(self, messages: list[dict], language: str | None = None) -> AsyncIterator[str]:
        """Tries each provider in the chain in order. The first one that
        starts streaming wins; a provider that fails AFTER yielding some
        tokens does NOT get silently retried mid-stream (that would risk
        duplicating partial output to the caller) -- it raises, and the
        caller (app/chat/rag_v2/pipeline.py) decides whether a partial
        answer is better than none, exactly as the current single-provider
        pipeline already does.
        """
        attempted: list[str] = []
        last_error: ProviderError | None = None

        for provider in self.config.chain:
            if not self._eligible(provider, language):
                continue
            attempted.append(provider.name)
            try:
                started = False
                async for chunk in provider.stream(messages):
                    started = True
                    yield chunk
                return  # provider completed successfully
            except ProviderQuotaError as exc:
                last_error = exc
                log.warning("provider %s quota exhausted, trying next in chain", provider.name)
                continue
            except ProviderUnavailableError as exc:
                last_error = exc
                log.warning("provider %s unavailable (%s), trying next in chain", provider.name, exc.code)
                continue
            except ProviderError as exc:
                last_error = exc
                # A started-but-interrupted stream must not silently retry
                # from the top (would duplicate output already sent to the
                # caller); propagate immediately in that case.
                if started:
                    raise
                continue

        raise last_error or AllProvidersExhaustedError(attempted)

    async def complete_json(self, messages: list[dict], max_tokens: int = 300, language: str | None = None) -> dict:
        """Same fallback-chain semantics as stream_chat, minus the
        partial-output concern (a JSON-mode call either returns a whole
        parsed object or raises -- there's nothing to have "already sent
        to the caller")."""
        attempted: list[str] = []
        last_error: ProviderError | None = None

        for provider in self.config.chain:
            if not self._eligible(provider, language):
                continue
            attempted.append(provider.name)
            try:
                return await provider.complete_json(messages, max_tokens=max_tokens)
            except ProviderQuotaError as exc:
                last_error = exc
                log.warning("provider %s quota exhausted, trying next in chain", provider.name)
                continue
            except ProviderUnavailableError as exc:
                last_error = exc
                log.warning("provider %s unavailable (%s), trying next in chain", provider.name, exc.code)
                continue

        raise last_error or AllProvidersExhaustedError(attempted)


_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router


def reset_router() -> None:
    """Test-only: force re-construction on next get_router() call."""
    global _router
    _router = None


# --- Exact-match response cache -------------------------------------------
#
# Day 2 ships exact-match only (deterministic SHA-256 of the fully-rendered
# prompt). The tenant-scoped SEMANTIC cache from ADR 004 (embedding
# similarity within a bot+publication-version namespace) is a Day 3+ item,
# tracked so it is not silently dropped: see launch/13-SPRINT-10-DAYS.md
# Day 2 gate notes.


def exact_cache_key(bot_snapshot_id: str, messages: list[dict]) -> str:
    payload = json.dumps({"bot": bot_snapshot_id, "messages": messages}, sort_keys=True)
    return "chatcache:" + hashlib.sha256(payload.encode()).hexdigest()
