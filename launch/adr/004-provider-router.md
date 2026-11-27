# ADR 004 — LLM provider router, caching, rate limiting

**Status**: Decided 2026-11-25. Implementation Day 2.

## Context

Master prompt §4 mandates provider abstraction, ordered fallback, per-tenant rate limits, caching, and the ability to flip to a paid model with only a config change. Current code has a single Groq adapter (`backend/app/chat/llm.py`) and a single Cloudflare embeddings adapter (`backend/app/providers/embeddings.py`).

## Options

**A — Build a generic router.**
**B — Use LiteLLM / OpenRouter directly.** OpenRouter has a free tier but routes through their endpoint — rate-limited by their IPs, not ours; no per-tenant isolation.
**C — Two half-measures.**

## Decision

**Option A — a thin in-house provider router.**

```
app/providers/
  router.py           # orchestrates chain
  base.py             # interfaces: Chat, Embed, Rerank, JSONMode, ToolCalling
  groq.py             # primary
  openrouter.py       # fallback
  gemini.py           # future paid
  cloudflare_embed.py # kept
  cloudflare_rerank.py# new (bge-reranker-base)
  jina_rerank.py      # fallback reranker
  cache.py            # exact + semantic cache
  rl.py               # token-bucket in Redis
```

Config schema:

```yaml
providers:
  chat:
    primary: groq
    fallback: [openrouter]
    on_quota: queue       # or degrade
    cache:
      exact: true
      semantic:
        enabled: true
        namespace: company:{company_id}:bot:{bot_id}:kversion:{v}
        ttl_seconds: 3600
    rate_limit:
      per_company: 20/min
      global: 600/min
```

Capability flags per model (`supports_streaming`, `supports_tool_calling`, `supports_json_mode`, `context_window`, `commercial_use`, `trains_on_input`) captured so switching is a data change, not code.

## Trade-offs

- **Risk**: additional 5-8 ms overhead vs direct Groq call. Acceptable.
- **Benefit**: switching to a paid model is a YAML + env change plus running the eval; the ship-gate stays green or we roll back. `16-PAID-MODEL-SWITCH.md` codifies the steps.
- **Risk**: free-tier providers may train on input. Current status:
  - Groq: free-tier terms state customer data is NOT used for training. (needs verification against current ToS before launch — flagged P0 in `03-RISKS-AND-BLOCKERS.md` EX-list.)
  - OpenRouter: depends on the underlying model; default routing can land on free models that train. We route only through specifically allow-listed free models.
  - Cloudflare Workers AI: terms say inference requests are not used for training.
  - Gemini: free tier trains on input. Explicitly excluded from chain while in free-mode.

## Caching

- **Exact-match**: SHA-256 of `(bot_snapshot_id, system_prompt_hash, last_user_message, prior_turn_ids)` → response. TTL 1 h.
- **Semantic cache**: embedding of the last user message; find nearest cached response above threshold 0.93 within the same namespace; TTL 1 h. Namespace includes `kversion` so publishing a new bot snapshot invalidates all cached responses for that bot.
- **Safety**: cache hits inherit the original visitor's auth check? No — the cache value is deterministic per (bot_snapshot, prompt, user_turn); it does NOT bypass the per-request quota or the current bot's active publication. Confirmed pattern from `app/chat/pipeline.py` tests that cache paths still trigger quota.

## Rate limiting

Token bucket in Redis per `(scope, identifier)` via `app/redis_resilience.py` `RateLimiter` once R01 is fixed.

## Rollback

Set `providers.chat.primary=groq, fallback=[]` and `cache.exact=false, cache.semantic.enabled=false` — effectively disables all routing and caches; behaves like today.
