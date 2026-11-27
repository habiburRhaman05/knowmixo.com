# PART 1 — final reply

## 1 · Files created

### Launch pack (17 docs + verify script + 9 ADRs)

```
launch/
  00-BUILD-HEALTH.md               — real command output + 8 findings
  01-FEATURE-INVENTORY.md          — 142 features catalogued across 13 areas
  02-GAP-ANALYSIS.md               — 1 534 h of demand, line by line
  03-RISKS-AND-BLOCKERS.md         — 22 risks (10 P0) + full security review
  04-ARCHITECTURE.md               — target topology + 4 flow diagrams
  05-RAG-V2-SPEC.md                — stage-by-stage spec + prompts + schema
  06-ESCALATION-DESIGN.md          — tables + state machine + templates
  07-WIDGET-SPEC.md                — JS API + config schema + install matrix
  08-UX-SPEC.md                    — IA + flows + token set + components
  09-BILLING-PAYMENTS.md           — plans + schema + lifecycle + cost model
  10-COMPLIANCE-US.md              — privacy/terms/DPA/AI disclosure outlines
  11-KEYS-AND-ACCOUNTS.md          — every external account + env block
  12-FEASIBILITY-MATRIX.md         — honest arithmetic + per-feature verdicts
  13-SPRINT-10-DAYS.md             — 10 days × 4 lanes with task template
  14-API-TEST-PLAN.md              — 14 suites + verify_launch.sh
  15-LAUNCH-GATE.md                — Day-10 checklist
  16-PAID-MODEL-SWITCH.md          — switch steps + cost model
  adr/001-vector-store.md          — pgvector + FTS
  adr/002-rls.md                   — row-level security
  adr/003-queue-outbox.md          — reuse jobs runner + outbox
  adr/004-provider-router.md       — LLM router + cache + rate limit
  adr/005-realtime.md              — SSE + Redis pub/sub
  adr/006-widget-delivery.md       — loader + iframe + versioned CDN
  adr/007-api-conventions.md       — /v1 lock + OpenAPI SoT + TS client
  adr/008-billing.md               — Stripe SoT + reconciliation
  adr/009-data-lifecycle.md        — retention + backups + PII
scripts/
  verify_launch.sh                 — one-command PASS/FAIL table
```

### Supporting files pending PART 2 Day 1

- Updated `backend/.env.example` (new block per `11-KEYS-AND-ACCOUNTS.md` §5)
- Updated `frontend/.env.example`
- Eval harness skeleton at `backend/eval/` (Day 1 task D1.7)
- New tests in `backend/test/` and `frontend/e2e/` grow day by day

Not created yet (deferred to PART 2 Day 1 execution so I don't modify product code during PART 1):
- the env fixes identified in `00-BUILD-HEALTH.md` §2 (D1.1-D1.5)
- the alembic 0009 pgvector migration (D1.6)
- the file deletions (D1.4)

## 2 · Counts per status label

Across the 142 features inventoried in `01-FEATURE-INVENTORY.md`:

| Label | Count | % |
| --- | --- | --- |
| ✅ VERIFIED | 23 | 16 |
| 🟡 PARTIAL | 28 | 20 |
| ❌ MISSING | 86 | 60 |
| ⚠️ BROKEN | 5 | 4 |

The 5 BROKEN items: dev server /login render (stale `.next`, now cleared) · `redis_resilience` env read (R01) · `AUTH_SECRET` validation missing (R02) · `SMTP_HOST="gmail"` · junk root file.

## 3 · Top 10 blockers (ordered)

1. **R01 — Redis resilience reads `os.environ`** not settings; fix is 1 h; critical because rate limiting + live inbox fail in prod.
2. **R06 — No Row-Level Security**, only app-level filter. One typo = cross-tenant leak.
3. **Entire RAG v2 pipeline missing.** Single-shot retrieval today; master-prompt ship-gate unreachable without the rewrite.
4. **Escalation engine does not exist.** Appendix A is 140 h of work.
5. **Billing does not exist.** 108 h plus Stripe Tax PENDING_EXTERNAL.
6. **WhatsApp / Twilio approvals** are 1-8 weeks. Must start today.
7. **No markdown sanitiser in widget** → stored XSS risk if a crawled page carries HTML.
8. **No AI disclosure + no privacy/terms pages** — launch-blocking for a US SaaS.
9. **No MFA, no roles beyond `owner`** — launch acceptable for free beta but P1 before Agency.
10. **Backups unverified** — Neon PITR never restored to a scratch DB.

## 4 · Feasibility verdict

**Full section-2 scope will NOT fit 10 days.** Honest arithmetic in `12-FEASIBILITY-MATRIX.md`:

- Capacity: **~245 h** (4 lanes × 10 days × 8 h − 15 % buffer − 10 % reviews)
- Demand: **~1 534 h**
- Overshoot: **6.3×**

Recommended cuts (never-cut items preserved):
- OCR, scheduled re-crawl, change-aware re-embed → post-launch (Day 17-25)
- 6 of 9 install snippets → post-launch (keep script + React + Next.js on Day 7)
- Bulk actions + tags on Knowledge → post-launch (Day 14, 16)
- Multiple bots per company + Agency multi-workspace → post-launch (Day 12, 18-22)
- Messenger + Instagram + Shopify + HubSpot inbound → post-launch (Day 16-22)
- WhatsApp + Twilio live delivery → **PENDING_EXTERNAL** (code ships on Day 6; delivery flips on when Meta + Twilio approve)
- Analytics beyond 3 core charts → post-launch (Day 14-17)
- Playground filter/search, 6 of 8 industry templates, SLA timers, PII redaction → post-launch

After cuts the 10-day plan stays within ±10 % of lane capacity. See `13-SPRINT-10-DAYS.md` for day-by-day assignment.

**Biggest schedule risk**: pgvector migration + reranker/verifier latency budget in Lane A. Mitigation: 72-h dual-write to Pinecone + feature-flag `rag.engine='v1'` so rollback is instant.

**Launch label**: "Knowmivo v1.0 · public beta" — sets expectations around free-tier LLM throttling and remaining PENDING items; keeps the door open for paid tiers.

## 5 · Keys and accounts needed from owner (names only; start the long-leads today)

Long-lead (block launch if delayed):
- Meta Business Verification + WhatsApp Cloud API (WABA, phone, permanent token)
- WhatsApp templates: `escalation_critical_v1`, `escalation_high_v1`, `escalation_digest_v1`
- Twilio 10DLC / Toll-free verification
- Stripe Tax registration (home state)
- Postmark (or Resend) + verified sending domain + SPF/DKIM/DMARC
- `knowmivo.com` registered + DNS + Let's Encrypt
- Attorney review of privacy/terms/DPA

Day-1 fast:
- Stripe test keys + webhook secret
- Sentry DSNs (backend + frontend)
- Cloudflare R2 access key + bucket
- OpenRouter API key
- UptimeRobot + Instatus/statuspal

Day-5-7:
- Slack app credentials
- Telegram bot token
- HubSpot private app token
- Google Sheets service account
- Shopify partner credentials
- Calendly link(s) for sample templates

Full dashboard paths in `launch/11-KEYS-AND-ACCOUNTS.md`.

## 6 · Five architecture decisions that change the most

1. **ADR 001 — pgvector + FTS instead of Pinecone-only.** Collapses chat-latency variance, makes RLS work across the whole retrieval, avoids blowing Pinecone free tier. 72-h dual-write + feature flag = safe rollback.
2. **ADR 002 — RLS on every tenant table.** Defense in depth. Fail-closed regression test is the acceptance criterion.
3. **ADR 004 — In-house provider router with per-tenant rate limits + exact and semantic cache.** Makes the paid-model switch in `16-PAID-MODEL-SWITCH.md` a config change, not a code change.
4. **ADR 008 — Stripe as source of truth, our DB as cache.** Avoids drift between billing and entitlements; enables Day-10 live-switch with one manual test transaction.
5. **ADR 003 — Reuse the existing `jobs` runner with an `event_outbox`.** No new queueing dependency; preserves ACID around event emission for webhooks + escalation.

## 7 · Self-critique — 5 most likely ways this plan fails

1. **The RAG v2 rewrite slips past Day 4.** Multi-stage pipelines look clean on paper and bleed time on the hundred small integration points (JSON mode, tool calls, streaming vs. verifier ordering). Mitigation: feature-flag + dual-run v1 alongside v2 so launch ships on v1 if v2 lags — degrades quality to current single-shot but doesn't block launch. Second mitigation: if hit@5 slips at Day 9, lower the ship-gate to 85 % with a written note (per `03-RISKS-AND-BLOCKERS.md` §5), not silently.
2. **WhatsApp template approvals are denied or delayed past Day 10.** Escalation then ships with email/Slack/Telegram only. UX must explicitly say "WhatsApp coming soon" on `/pricing` — no silent cut.
3. **Neon storage + Pinecone deprecation cost more than estimated.** The 1.5 GB estimate for 150 companies is a back-of-envelope; a single large-doc customer could flip it. Mitigation: per-plan storage caps (A.6) and `retention_days` worker running from Day 7.
4. **Owner review bandwidth** is the hidden constraint. 2 h/day of your calendar on PRs for billing/security/escalation is tight; if you can't give it, we accumulate risky code. Mitigation: narrow the PR count — one PR per lane per day, batched reviews.
5. **Free-tier LLM throttling under load.** Groq daily caps + OpenRouter hop rates can produce `429` chains during peak hours. Our mitigation is "queued with high demand message", which is honest but will frustrate some users. If adoption outpaces plans, we accelerate `16-PAID-MODEL-SWITCH.md` earlier than scheduled.

---

**PART 1 is finished. Starting PART 2 Day 1 now, per owner's "once these done start part 2" instruction.**
