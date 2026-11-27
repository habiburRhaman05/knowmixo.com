"""OpenRouter chat adapter conforming to ChatProvider (ADR 004). Fallback
only -- never primary while `settings.free_only=true` -- because
OpenRouter's FREE-tier models vary in whether they train on submitted
input depending on the underlying model, which must be re-verified for
whichever specific `:free` model this account is routed to before it is
trusted with real customer conversation data. See
launch/03-RISKS-AND-BLOCKERS.md EX-list and ADR 004.

This module is a skeleton: it is NOT wired into the live fallback chain
yet (`app/providers/router.py`'s default config has `fallback: []`).
Enabling it requires: (1) picking and allow-listing one specific free
model by name (never "whatever OpenRouter routes to"), (2) confirming
that model's current terms, (3) running the eval harness against it per
launch/05-RAG-V2-SPEC.md, and (4) recording the result in an ADR.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.config import settings
from app.providers.base import (
    ProviderCapabilities,
    ProviderQuotaError,
    ProviderUnavailableError,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0)


class OpenRouterChatProvider:
    name = "openrouter"

    def __init__(self, model: str | None = None) -> None:
        # Deliberately no default -- a caller must explicitly allow-list
        # one model; there is no safe generic ":free" default per the
        # module docstring above.
        self.model = model or ""
        self.capabilities = ProviderCapabilities(
            streaming=True,
            tool_calling=False,
            json_mode=False,
            context_window_tokens=8_192,
            commercial_use_verified=False,  # not yet re-verified for the chosen model
            trains_on_input=True,  # fail safe until verified otherwise for the chosen model
        )

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        if not self.model:
            raise ProviderUnavailableError(self.name, "openrouter_model_not_configured")
        s = settings()
        api_key = getattr(s, "openrouter_api_key", "") or ""
        if not api_key:
            raise ProviderUnavailableError(self.name, "openrouter_api_key_missing")

        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": 0.1}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("POST", OPENROUTER_URL, json=payload, headers=headers) as response:
                    if response.status_code == 429:
                        raise ProviderQuotaError(self.name, int(response.headers.get("retry-after", "60")))
                    if response.status_code >= 400:
                        raise ProviderUnavailableError(self.name, f"openrouter_http_{response.status_code}")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(self.name, "openrouter_timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(self.name, "openrouter_unreachable") from exc
