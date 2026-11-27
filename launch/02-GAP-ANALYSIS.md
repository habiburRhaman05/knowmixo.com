# 02 · Gap analysis and improvement plan

Rows map 1:1 to the status labels in `01-FEATURE-INVENTORY.md`. "Hours" is an honest point estimate for one competent engineer. "Lane" uses the four parallel lanes from the master prompt. Hours sum is at the bottom.

Legend: **Rewrite** = existing design cannot meet the requirement, replace. **Extend** = keep and add. **Build** = new module.

## A. Knowledge and ingestion — gap rows

| # | Required state | Current state | Change | Lane | Hrs | Risk | Depends on |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A.1.5 | CSV upload parses into chunks, respects header row | no parser, kind not in schema | Build: `parsers/csv.py` using `csv.DictReader`; add `'csv'` to `CHECK` constraint via mini-migration | A | 4 | low | 0009 migration |
| A.1.9 | Depth-limited crawl + progress stream | only page cap + sitemap fallback | Extend: add `max_depth` to `crawl_jobs`, emit progress events, surface in UI | A+B | 10 | low | — |
| A.2.3 | Tables kept intact in chunks | tables flattened to text | Extend: pdf → `pdfplumber` for tables (free), docx → `python-docx` table iteration; serialise tables as Markdown; detect in HTML via BeautifulSoup `<table>` | A | 12 | medium | add dep |
| A.2.6 | OCR scanned PDFs | marked `unsupported_scanned_pdf` | Build + PENDING_EXTERNAL: use Cloudflare Workers AI `@cf/mistral/mistral-small-latest` OR document as "upgrade PDF" instruction if free tier insufficient | A | 16 | high | eval + CF quota |
| A.3.1 | Scheduled re-crawl | manual only | Build: add `schedule` (cron) col on source, extend worker with `scheduled_crawl` job kind; cron-expression picker in UI | A+B | 10 | low | — |
| A.3.2 | Change-aware re-embed | re-embed whole doc | Extend: hash-per-chunk diff; only re-embed changed chunks (saves CF quota) | A | 12 | medium | eval |
| A.4.2 | Columns size + last synced | partial | Extend: add `size_bytes` to `documents`, surface in UI | A+B | 2 | low | — |
| A.4.4 | Disable (soft) a source | hard delete only | Extend: `disabled_at` + filter in retrieval SQL | A | 4 | low | — |
| A.4.5 | Bulk actions | row-at-a-time | Extend UI: selection checkbox + confirm dialog + bulk API | B | 10 | low | — |
| A.4.6 | Source tags | none | Build: `documents.tags text[]`, tag chip input, filter | A+B | 10 | low | — |
| A.5.1-2 | Draft/publish of knowledge + rollback | publications snapshot only bot config + version pick | Rewrite: add `knowledge_snapshot_id` with content hash; rollback endpoint reads prior snapshot's version-ids | A+B | 14 | medium | entitlements |
| A.6 | Plan-level limits | hardcoded | Extend: entitlements layer from J.5 reads caps | A | 4 | low | J |

**Area subtotal: 108 h**

## B. RAG v2 — gap rows

| # | Required | Current | Change | Lane | Hrs | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| B.1 | Sufficiency loop capped at 3 iterations | single shot | Build: `app/chat/rag_v2/pipeline.py` state machine (guard→rewrite→retrieve→rerank→grade→answer/clarify/abstain) | A | 20 | high |
| B.2 | Hybrid: dense + FTS/BM25, RRF | dense only | Build: adopt pgvector (ADR 1), populate `tsvector` column, retrieval SQL that fuses with RRF | A | 24 | high |
| B.3 | Reranker | none | Build: Cloudflare Workers AI reranker (`@cf/baai/bge-reranker-base` — free). If unavailable, Jina reranker API free tier | A | 10 | medium |
| B.4 | Query rewrite + decomposition | concat prev | Build: small-LLM call with safety cap + fallback | A | 8 | low |
| B.5 | Intent classifier | prompt-injection regex | Extend: cheap LLM + rules; outputs `{intent, severity, language}` | A | 10 | medium |
| B.6 | Adaptive threshold | fixed 0.25 | Build: per-bot calibrated threshold from eval set | A | 6 | low |
| B.7 | Sufficiency grader | none | Build: LLM-judged grade of retrieved context | A | 8 | medium |
| B.8 | Grounded gen (citations) | present | Extend: structured output w/ claim-level cites | A | 10 | low |
| B.9 | Verifier | none | Build: claim-vs-evidence faithfulness check | A | 12 | medium |
| B.10 | Per-message eval record | partial | Extend: `rag_traces` table with full stage timings + scores | A | 10 | low |
| B.11-12 | Eval harness + ship-gate CI | none | Build: 150 cases, LLM judge, nightly GHA run | D | 24 | medium |

**Area subtotal: 142 h** *(this is the single biggest area; most of it is net-new work)*

## C. Chat experience — gap rows

| # | Change | Lane | Hrs | Risk |
| --- | --- | --- | --- | --- |
| C.1.2 | Sanitised markdown render in widget via DOMPurify + sanitisation unit tests with XSS corpus | B+D | 6 | low |
| C.1.3 | Citation-opens-passage drawer in widget + owner | B | 8 | low |
| C.1.4 | Follow-up suggestions after answer | A+B | 6 | low |
| C.1.5 | Quick-reply chips surfaced from intent/entity | A+B | 4 | low |
| C.1.7 | First-class Retry button on failed bubble | B | 2 | low |
| C.2.1 | Conversation summarisation at 6-message cap | A | 10 | medium |
| C.2.2 | `identify()` with HMAC verification | A+B+D | 8 | medium |
| C.2.3 | Language detect (`langdetect`) + per-language system prompt tuning + Spanish eval slice | A+D | 10 | medium |
| C.3.1 | Pre-chat form builder | A+B | 12 | low |
| C.3.2 | `capture_lead` tool-call integration with form | A | 6 | low |
| C.3.3 | hCaptcha invisible on widget bootstrap | B | 6 | low |
| C.4.1 | Comment textarea under feedback | B | 2 | low |
| C.4.2 | Conversation rating at close | A+B | 6 | low |
| C.5 | Business-hours jsonb + behavior branching | A+B | 10 | low |
| C.6 | AI disclosure line in widget header (configurable but on by default) | B | 2 | low |

**Area subtotal: 98 h**

## D. Widget customisation — gap rows

| # | Change | Lane | Hrs | Risk |
| --- | --- | --- | --- | --- |
| D.1.1 | Branding schema → colors (primary, bg, text, accent, bubble x2) + CSS vars → runtime theme | B | 10 | low |
| D.1.2 | Light/dark/auto toggle | B | 4 | low |
| D.1.3 | Font allow-list (16 Google Fonts) | B | 4 | low |
| D.1.4 | 4 positions + x/y offsets | B | 3 | low |
| D.1.5 | Launcher shape/size/icon/label/anim + preview | B | 10 | low |
| D.1.6 | Plan-gated "Powered by" | B+C | 2 | low |
| D.2.1 | Auto-open rules builder | B | 12 | medium |
| D.2.2 | Hide rules | B | 6 | low |
| D.2.3 | Sound/offline | B | 4 | low |
| D.2.5 | Consent-before-storage mode | B+D | 6 | low |
| D.3.1 | Full JS API (`sendMessage`, `identify`, `setMetadata`, `setTheme`, `on`, `destroy`) + events | B | 12 | medium |
| D.3.2 | HMAC identity server-side verify | A+B | 6 | medium |
| D.3.3 | `data-knowmivo-open` | B | 1 | low |
| D.4.1 | Install options: GTM/WordPress/Shopify/Webflow/Wix/Squarespace/iframe/QR | B | 16 | low |
| D.4.2 | Verify-install check | A+B | 6 | low |
| D.7 | axe + Lighthouse + browser matrix CI | D | 10 | medium |

**Area subtotal: 112 h**

## E. Monitoring — gap rows

| # | Change | Lane | Hrs | Risk |
| --- | --- | --- | --- | --- |
| E.1 | Live view page (SSE from Redis pub/sub), takeover button | A+B+C | 20 | high |
| E.2.2 | Add 7 missing filters | A+B | 8 | low |
| E.2.3 | Retrieval-trace side panel using `rag_traces` | A+B | 10 | medium |
| E.2.4 | Tags + notes CRUD | A+B | 10 | low |
| E.2.5 | CSV export | A | 4 | low |
| E.3.1 | `/analytics/series` endpoint + 7 charts (recharts) | A+B | 20 | medium |
| E.3.2-5 | Define deflection/CSAT/TTFT metrics, implement, backfill | A | 12 | medium |
| E.4 | Gap clustering (nightly batch job that groups low-confidence Qs by embedding similarity) | A | 14 | medium |
| E.5 | Bad-answers queue + "write a correction" → FAQ | A+B | 16 | medium |
| E.6 | Alerts + weekly digest email | A+B+C | 20 | medium |
| E.7.2 | PII redaction toggle + regex library | A+D | 8 | low |

**Area subtotal: 142 h**

## F. Escalation (Appendix A) — gap rows

Separate full design in `06-ESCALATION-DESIGN.md`. High-level budget here.

| Component | Hrs | Risk |
| --- | --- | --- |
| Severity classifier (LLM + rules) | 12 | medium |
| Owner rule engine (CRUD + eval at runtime) | 14 | medium |
| Safety-reply library (US 911/988) with locale awareness | 6 | low |
| State machine + outbox + delivery workers (reuse existing `jobs/runner.py`) | 20 | medium |
| WhatsApp provider adapter + templates (code + submission) | 16 + PENDING_EXTERNAL approval | high |
| Twilio SMS fallback (code + 10DLC/toll-free verification code path) | 10 + PENDING_EXTERNAL | high |
| Slack + email + Telegram channels | 16 | low |
| Signed deep link (JWT with jti + expiry, single-use) | 8 | medium |
| Owner setup UX (number + verify code) | 10 | low |
| Dedupe/merge + storm protection | 8 | medium |
| Quiet hours + severity SLAs + re-escalation chain | 10 | medium |
| Test-alert button + e2e tests against fake WA/Twilio | 10 | low |

**Area subtotal: 140 h + external approvals**

## G. Handoff / inbox

| Component | Hrs | Risk |
| --- | --- | --- |
| Status column on conversations + assignment + notes + canned replies tables | 10 | low |
| Realtime (SSE via Redis pub/sub per-tenant channel; see ADR 5) | 20 | medium |
| Visitor-side "team member joined" indicator | 4 | low |
| SLA timers + breach alerts (reuses E.6) | 8 | low |

**Subtotal: 42 h**

## H. Actions and tools

| Component | Hrs | Risk |
| --- | --- | --- |
| Tool framework (`BaseTool` + arg schemas + per-tenant limits + audit) | 14 | medium |
| Built-ins (search_knowledge, capture_lead, escalate_to_human) | 10 | low |
| Owner HTTP action (CRUD, SSRF gate via existing module, timeouts, confirmation for mutating) | 14 | medium |
| book_appointment via Calendly link (link-only first) | 6 | low |
| Public REST API + API keys with scopes (reuses `idempotency_keys`) | 20 | medium |
| Outbound webhook emitters at key events | 8 | low |

**Subtotal: 72 h**

## I. Channels

Code budget only — approvals tracked in `11-KEYS-AND-ACCOUNTS.md`.

| Channel | Hrs | Risk |
| --- | --- | --- |
| Slack alerts + inbound app (incoming-webhook outbound, slash command inbound) | 16 | low |
| Zapier/Make generic webhook docs | 2 | low |
| HubSpot lead sync (private app with API key) | 16 | medium |
| Google Sheets lead export (service account) | 10 | low |
| Shopify product/order lookup tool (Admin API with storefront hint) | 20 | medium |
| WhatsApp/Messenger/Instagram inbound chat (reuses escalation channel adapters) | 24 | high |

**Subtotal: 88 h**

## J. Billing

| Component | Hrs | Risk |
| --- | --- | --- |
| Schema: `plans`, `plan_features`, `subscriptions`, `usage_events`, `invoices`, `stripe_events` (0009) | 8 | low |
| Stripe Products/Prices + lookup keys + env | 4 | low |
| Checkout + Portal + Tax decision | 14 | medium |
| Webhook endpoint with idempotency + out-of-order handling | 14 | medium |
| Entitlements layer + replace `free_only=true` daily caps | 14 | medium |
| Lifecycle (upgrade/downgrade/cancel/dunning/refund/reactivate) | 18 | medium |
| Promo codes + free-tier abuse (email/domain/device fingerprint) | 10 | low |
| Billing UI (plan picker, usage card, invoices list) | 16 | low |
| Reconciliation cron + `/billing/sync` audit endpoint | 10 | medium |

**Subtotal: 108 h**

## K. Accounts / teams / compliance

| Component | Hrs | Risk |
| --- | --- | --- |
| MFA TOTP + recovery codes + step-up on destructive actions | 14 | medium |
| Role matrix (owner/admin/agent/viewer) + authz middleware | 12 | medium |
| Team invites via email with RBAC pick | 10 | low |
| Multiple bots per company (data migration) | 12 | medium |
| Agency / multi-workspace (for Agency plan) | 20 | medium |
| Privacy/Terms/DPA pages (markdown + reviewer flag) | 10 | low — attorney review PENDING_EXTERNAL |
| CCPA/CPRA DSR UI and queue | 10 | medium |
| AI disclosure widget copy + settings | 2 | low |
| CAN-SPAM footer + unsubscribe link in digest emails | 4 | low |
| HIPAA/COPPA stance in ToS + warning banner on healthcare templates | 4 | low |
| Subprocessor list page + generator | 2 | low |

**Subtotal: 100 h**

## L. Operator console

Budget: 40 h, mostly read-only dashboards reading existing tables plus kill-switch toggles.

## M. UX / polish

| Component | Hrs | Risk |
| --- | --- | --- |
| Onboarding wizard (URL → auto-crawl → test chat) | 20 | medium |
| Bot playground / retrieval inspector (reads `rag_traces`) | 16 | medium |
| 8 industry templates (JSON config + seed sources) | 12 | low |
| Marketing site: pricing, compare, docs/help, status link, legal | 24 | low |
| SEO basics: sitemap.xml, OG image generator, metadata | 6 | low |
| In-app guidance + first-value event ("widget_loaded_once") | 6 | low |
| Fix UX issues listed in `01-FEATURE-INVENTORY.md` UX audit (10 items) | 12 | low |

**Subtotal: 96 h**

## Infra / security / platform (cross-cutting)

| Component | Hrs | Risk |
| --- | --- | --- |
| Provider router + rate limiting + fallback chain (`04-ARCHITECTURE.md` + ADR 4) | 20 | medium |
| Caching: exact-match + tenant-scoped semantic | 14 | medium |
| Observability: Sentry, OTel traces, structured logs with tenant/conversation ids | 16 | medium |
| Load test + chaos (k6 + kill scripts) | 16 | medium |
| Backups verified (Neon PITR restore drill) | 6 | low |
| RLS + tenancy hardening (ADR 2) | 20 | high |
| CI pipelines (build + test + axe + lighthouse + eval nightly) | 12 | low |
| Dockerfile + compose + deploy scripts + staging + prod | 20 | medium |
| Secret scanning (gitleaks) + dependency audit | 6 | low |
| Status page + health pingers | 6 | low |
| Domain/DNS/TLS/email domain SPF-DKIM-DMARC | 10 | low |

**Subtotal: 146 h**

## Totals

| Area | Hours |
| --- | --- |
| A Knowledge | 108 |
| B RAG v2 | 142 |
| C Chat | 98 |
| D Widget | 112 |
| E Monitoring | 142 |
| F Escalation | 140 |
| G Handoff | 42 |
| H Actions | 72 |
| I Channels | 88 |
| J Billing | 108 |
| K Accounts/Compliance | 100 |
| L Operator console | 40 |
| M UX / polish | 96 |
| Infra / security | 146 |
| **Grand total** | **1,534 h** |

That is the honest effort number. Capacity analysis and the resulting cut are in `12-FEASIBILITY-MATRIX.md`.

## Where the current architecture cannot meet the requirement

Four places. Each needs a rewrite, not an extension. ADRs flag these.

1. **Chat pipeline is single-shot.** `app/chat/pipeline.py:retrieve` is a one-pass dense query. The master prompt requires an agentic, verified, cited, abstention-capable loop. Rewrite into `app/chat/rag_v2/` with the state machine from `05-RAG-V2-SPEC.md`. The old pipeline stays as a compatibility shim for V1 draft preview until Day 4.
2. **No provider abstraction.** `app/chat/llm.py` is a direct Groq adapter. `app/providers/embeddings.py` is a direct Cloudflare adapter. The master prompt mandates a provider router. Build `app/providers/router.py` and move both current providers into it (ADR 4).
3. **Bots are 1:1 per company.** `app/bots/service.py:get_or_create_bot_for_company` and the UNIQUE index assume one. Section 2K.7 and the Agency plan require N. Rewrite publishing semantics to the bot, not the company.
4. **Role model is a stub.** The `memberships.role` CHECK accepts only `owner`. Section 2K.5 and the team-invite story need 4 roles with route-level authz. Extend the CHECK, add an `authz` dep for every route, migrate rows.

## No-change list (deliberate)

The following are already good enough for launch; leave them alone unless a Day-N task explicitly says to touch them.

- SSRF validator (`app/security/ssrf_http.py`)
- Durable job runner (`app/jobs/runner.py`) — lease + fencing is correct
- `idempotency_keys` + `app/idempotency.py`
- `audit_events` + ContextVar-safe writer
- SSE parser on the frontend (`src/lib/sse.ts`)
- Alembic layout
