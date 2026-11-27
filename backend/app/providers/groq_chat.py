"""Groq chat adapter conforming to ChatProvider (ADR 004). This wraps the
existing, already-proven `app/chat/llm.py` streaming call -- it does not
reimplement the HTTP logic, just adapts it to the router's interface so
`app/providers/router.py` can treat Groq as one interchangeable chain
entry rather than a hardcoded primary.
"""
from __future__ import annotations

from typing import AsyncIterator

from app.config import settings
from app.providers.base import (
    ProviderCapabilities,
    ProviderError,
    ProviderQuotaError,
    ProviderUnavailableError,
)


class GroqChatProvider:
    name = "groq"

    def __init__(self) -> None:
        self.model = settings().chat_model
        # Verified against Groq's published free-tier terms as of the
        # stack decision in docs/04-STACK-AND-SERVICES.md: customer data
        # is not used for training on the current free tier. Re-verify
        # before relying on this in ADR 004's provider chain for anything
        # beyond the current beta -- terms can change without notice.
        self.capabilities = ProviderCapabilities(
            streaming=True,
            tool_calling=False,
            json_mode=True,
            context_window_tokens=128_000,
            languages=("en", "es", "bn", "*"),  # Groq's hosted models are multilingual
            commercial_use_verified=True,
            trains_on_input=False,
            cost_per_1k_input_cents=0.0,
            cost_per_1k_output_cents=0.0,
        )

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        from app.chat.llm import LLMError, LLMQuotaError, stream_completion

        try:
            async for chunk in stream_completion(messages):
                yield chunk
        except LLMQuotaError as exc:
            raise ProviderQuotaError(self.name, exc.retry_after_seconds) from exc
        except LLMError as exc:
            raise ProviderUnavailableError(self.name, exc.code) from exc

    async def complete_json(self, messages: list[dict], max_tokens: int = 300) -> dict:
        from app.chat.llm import LLMError, LLMQuotaError, complete_json as _complete_json

        try:
            return await _complete_json(messages, max_tokens=max_tokens)
        except LLMQuotaError as exc:
            raise ProviderQuotaError(self.name, exc.retry_after_seconds) from exc
        except LLMError as exc:
            raise ProviderUnavailableError(self.name, exc.code) from exc
