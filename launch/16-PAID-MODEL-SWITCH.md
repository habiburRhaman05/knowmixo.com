# 16 · Paid-model switch

Explicit steps + env + eval thresholds + cost model for moving off free LLMs to a paid tier.

## Preconditions

- `scripts/verify_launch.sh` green on current free stack
- Provider router (ADR 004) in place
- Eval harness + 150-case golden set live
- Public cost dashboard shows current $/reply ≤ $0.0005 (monitored)

## Steps

1. **Pick candidates** (verify terms + pricing current the day of switch):
   - Anthropic Claude Haiku 3.5 — strong grounded output, tool-calling
   - OpenAI GPT-4o-mini — baseline
   - Google Gemini Flash — cheapest grounded tier
2. **Env**: add `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` + `GEMINI_API_KEY` to `.env`.
3. **Register provider** in `backend/app/providers/`:
   - `anthropic.py`, `openai.py`, `gemini.py` — implement the `Chat`, `JSONMode`, `ToolCalling` interfaces.
   - Capability flags set accurately (context window, JSON, tools, commercial use, trains on input).
4. **Run eval**: `python -m eval.harness --config paid_candidate_<name>` three times at different hours; record median.
5. **Ship-gate thresholds for paid**:
   - Hit@5 ≥ 92 % (slightly above free)
   - Faithfulness ≥ 97 %
   - Correct-abstention ≥ 92 %
   - TTFT p50 ≤ 1.5 s
   - Cost per reply ≤ $0.006 (so Growth plan maintains > 75 % GM)
6. **Flip primary** in `backend/providers.yaml`:
   ```yaml
   providers:
     chat:
       primary: anthropic
       fallback: [groq, openrouter]
   ```
7. **Deploy** via staging → canary 10 % of traffic for 24 h (feature-flag `settings.providers.canary_fraction`).
8. **Observe** cost dashboard + Sentry for 48 h. Rollback at any time by flipping `primary` back to `groq`.
9. **Announce** model tier in /pricing. Upgrade plan copy.

## Cost model (benchmark day of switch)

| Provider | $/1k in | $/1k out | Avg tokens / reply | Avg $/reply |
| --- | --- | --- | --- | --- |
| Groq gpt-oss-120b (free) | 0 | 0 | 1 500 / 400 | ≈ 0 |
| Anthropic Haiku 3.5 | 0.80 | 4.00 | 1 500 / 400 | 0.0028 |
| OpenAI GPT-4o-mini | 0.15 | 0.60 | 1 500 / 400 | 0.00047 |
| Gemini 1.5 Flash | 0.075 | 0.30 | 1 500 / 400 | 0.00023 |

Numbers are illustrative — always re-benchmark on switch day. Our target: Growth plan ($99 for 10k replies = $0.0099 / reply) sustains > 75 % GM. Haiku clears 72 % which is borderline; GPT-4o-mini comfortable; Flash abundant.

## Rollback

Flip `primary` back; cached entitlements and usage metering don't change; no DB migration. Zero-downtime.

## Audit / communication

- Add ADR `010-paid-model-switch.md` recording the decision + eval numbers.
- Email all paying customers 7 days before switch + post on changelog.
- Status page banner for the canary window.
