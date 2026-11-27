# KNOWMIVO: LAUNCH MASTER PROMPT V2 (Claude Code, VS Code)

> **This file replaces `LAUNCH_MASTER_PROMPT.md`.** Put it in the repo root, open Claude Code, send:
> `Read LAUNCH_MASTER_PROMPT_V2.md completely, twice. Execute PART 1. Think deeply before writing anything. Stop when PART 1 is finished and wait for my approval.`
> Then, day by day: `Execute PART 2, DAY <n>.`
> Parallel work: one git worktree + one Claude session per lane (A Backend/AI, B Frontend/UX, C Infra/Billing/Realtime, D Quality/Security). Each session reads this file plus `launch/` and works only its lane's tasks.

---

## 0. ROLE, MISSION, STANDARD OF WORK

You are, simultaneously: a principal backend/AI engineer, a staff frontend/UX engineer, a security reviewer, a QA lead, and a launch manager. You work like a senior engineer at a company whose paying customers will use this tomorrow.

**Product:** Knowmivo, a multi-tenant AI chatbot SaaS. A business signs up, adds knowledge (files, text, FAQs, URLs, site crawl), gets a chatbot and a highly customizable embeddable widget with copy-paste code, monitors everything the bot does, and gets alerted with context (including on WhatsApp) when something important or urgent happens.

**Mission:** take this exact codebase to a **public paid launch in 10 days**, **with all features in section 2 delivered** and **every one of them proven by running it**.

**Target market: United States first** (English primary, Spanish secondary), USD billing, US privacy/compliance norms. Bangladesh/South Asia is no longer the primary target; remove any Bangla-specific launch work from the critical path (keep multilingual retrieval working because `bge-m3` is multilingual; Spanish must be tested).

**Standard of work (non-negotiable):**
- Think before you act. For every non-trivial task: read the relevant code first, write a short plan, then implement, then test, then self-review the diff as if you were a hostile reviewer.
- Prefer boring, proven designs over clever ones. Prefer extending existing code over rewriting it, **unless the audit shows the existing design cannot meet the requirement**; in that case rewrite that part and justify it in an ADR.
- No placeholder code, `TODO`s, mock data, hard-coded demo values, or "will implement later" in any shipped path. If something cannot be finished, it goes in the feasibility matrix, not into the code as a stub.
- Every UI surface has loading, empty, error, and success states, is keyboard accessible, and works on mobile.
- Every API has input validation, authz, tenant scoping, pagination where lists exist, consistent errors, rate limiting where abusable, and tests.
- Match the repo's existing style and conventions unless an ADR changes them. Small, reviewable commits.

---

## 1. WHAT YOU ALREADY KNOW ABOUT THE REPO (verify every line; trust nothing)

- Backend: FastAPI (Python), Alembic migrations 0001-0008, Neon Postgres, Redis, Pinecone (1024-dim vectors), Cloudflare Workers AI `bge-m3` embeddings, Groq `gpt-oss-120b` LLM, `free_only` mode, local file storage, in-memory upload grants, durable job queue with retry.
- Frontend: Next.js 15 with a BFF layer, iframe-based widget (`embed.js`), hosted chat page, SSE streaming.
- Current chat flow (the **OLD flow that must be replaced**): embed query (plus previous user message) -> Pinecone top 5 -> fixed threshold 0.25 -> Postgres validation -> LLM stream -> citations -> guardrails -> quota reserve.
- Quotas today: 100 chats/day/company, 1000/day global. Billing: not built (the PRD excludes it).
- Reusable tables: `analytics_events`, `feedback`, `leads`, `webhook_endpoints`, `memberships`.
- The repo's own status docs (`docs/21`, `docs/23`, `docs/24`) say migrations were never run end to end, DB tests were skipped, the smoke test never ran against real providers, and frontend/backend were never integrated live. **Assume the code is unproven.**
- Hygiene issues seen: junk root file with a Windows-path name, retired `infra/schema.sql`, `scripts/init_db.py`, stale README, naming drift `knowmixo` vs `Knowmivo`. Pick one product name (default **Knowmivo**) and unify everywhere including the widget's global JS namespace.

**Owner facts:** domain, hosting, and a Stripe account exist; a marketing team exists; the owner is a full-stack developer who will review security-critical code. **I provide keys only after you list exactly what you need.**

---

## 2. COMPLETE FEATURE SCOPE (ALL must ship; "all features lagbe")

Part 1 must audit each item (exists / partial / missing / broken), and Part 2 must deliver each one.

### A. Knowledge and ingestion
1. Sources: file upload (PDF, DOCX, TXT, MD, CSV), pasted text, FAQ pairs, single URL, whole-site crawl (respect robots.txt, depth/page limits, same-domain), sitemap import.
2. Structure-aware parsing: headings, lists, tables (tables kept intact and readable), page numbers, FAQ pairs as single units; scanned-PDF/OCR is a stretch goal (document feasibility).
3. Scheduled re-crawl / re-sync with change detection (only re-embed changed content), manual "re-index" button, per-source status, error messages a human can act on.
4. Knowledge manager UI: sources list, status, size, last synced, chunk preview ("see exactly what the bot knows"), delete/disable a source, bulk actions, source tags.
5. Versioning: draft vs published knowledge and bot config, one-click rollback.
6. Limits per plan (sources, MB, pages), clear upgrade prompts.

### B. RAG v2 (mandatory; see section 5)
Agentic, hybrid, reranked, grounded, verified, evaluated. The old single-shot flow must be gone from production paths.

### C. Chat experience
1. Streaming answers with markdown rendering (sanitized), clickable citations that open the exact source passage, suggested follow-ups, quick-reply buttons, typing indicator, retry on failure.
2. Conversation memory within a session; visitor identity (anonymous or identified via widget API); multilingual (English default, Spanish tested); language auto-detect.
3. Lead capture: configurable pre-chat form and conversational capture (name, email, phone, custom fields), consent text, validation, spam protection.
4. Visitor feedback (thumbs plus optional comment), conversation rating at close.
5. Business-hours aware behavior (in-hours: live handoff possible; out-of-hours: collect contact + promise follow-up).
6. AI disclosure shown by default in the widget (configurable text); the bot must never claim to be human.

### D. Widget: maximum customization and copy-paste code
1. **Appearance:** brand colors (primary, background, text, accent, bubble colors), dark/light/auto, font family (system + Google fonts allow-list), font size, corner radius, shadow, widget width/height, position (4 corners, offsets), launcher shape/size/icon/label/animation, avatar, header title/subtitle, greeting, placeholder text, suggested prompts, "Powered by" visibility (plan-gated), custom CSS (sandboxed and sanitized).
2. **Behavior:** auto-open rules (delay, scroll %, exit intent, URL patterns, returning visitor), show/hide rules by URL pattern/device/language, sound on/off, persistent vs per-session history, offline mode message, pre-chat form builder, attachment upload by visitors (stretch; decide in feasibility), cookie/consent mode (no storage until consent when configured).
3. **JavaScript API:** `Knowmivo('init', {...})`, `open`, `close`, `toggle`, `sendMessage`, `identify` (user id, email, name, custom attributes, HMAC-signed identity for verified users), `setMetadata` (page/product/cart context passed to the bot), `setTheme`, `on(event, cb)` for `ready | open | close | message | lead | escalated | error`, `destroy`. Custom launcher: any element via `data-knowmivo-open`. Document everything.
4. **Install options with generated code:** plain `<script>` snippet, Next.js/React component (npm package or documented snippet), Google Tag Manager, WordPress, Shopify (theme snippet), Webflow/Wix/Squarespace instructions, raw iframe/hosted page link, QR code for hosted chat page. Each has a copy button and a "verify installation" check that confirms the widget loaded on the customer's domain.
5. **Live preview editor** in the dashboard: every setting changes the preview instantly; device toggle (desktop/mobile); test-chat inside the preview against the draft bot; presets/themes; save as draft, publish.
6. **Security:** domain allow-list enforced server-side (not just in JS), origin validation, CSP-safe, no customer-page DOM access, signed identity, rate limits per visitor/IP.
7. **Quality budget:** loader script small and async, lazy-load the chat UI, no layout shift, WCAG 2.1 AA (keyboard, focus management, screen-reader labels, color contrast, reduced motion), works on mobile Safari/Chrome/Firefox/Edge.

### E. Full monitoring (owner side)
1. **Live view:** conversations happening now, with takeover button.
2. **Transcripts:** search, filters (date, channel, page, language, status, rating, tag, resolved/unresolved, escalated, lead captured), full message detail including citations and the retrieval trace ("why did it answer this"), tags, notes, export (CSV/JSON).
3. **Analytics:** conversations, messages, unique visitors, resolution/deflection rate (define precisely in docs), escalation rate, lead conversion, CSAT, avg time to first token and response time, top questions, top topics, language mix, channel mix, per-page performance, widget funnel (loaded -> opened -> first message -> lead), cited-sources ranking, trend charts with date ranges and comparisons.
4. **Knowledge gaps:** unanswered/low-confidence questions clustered by topic with counts and examples; one-click "write the answer" (adds a FAQ, re-embeds, marks gap resolved).
5. **Quality review:** bad-answers queue (thumbs-down, low confidence, hallucination flag from verifier, escalations) with trace; owner can correct an answer and the correction becomes knowledge.
6. **Alerts and reports:** configurable alert rules (spike in unanswered, negative feedback streak, quota 80%/100%, ingestion failures, widget not loading), weekly/daily email digest (CAN-SPAM compliant: unsubscribe + physical address in footer).
7. **Audit log** of owner/team actions; data retention settings; PII redaction toggle in stored transcripts.

### F. Emergency / important-event escalation to the owner (WhatsApp first, with context)
Full design in Appendix A. Requirements in short: the bot detects emergencies and important events (urgent safety/medical language, angry or churning customer, high-value lead, legal threat, payment/fraud, repeated bot failure, owner-defined rules), tells the visitor what is happening, and **sends the owner a WhatsApp message with context** (severity, reason, short AI summary, key details, visitor contact if given, page, time, secure deep link to take over). It falls back through SMS/email/Slack/Telegram if WhatsApp is not delivered or acknowledged, supports an escalation chain (primary -> backup -> team), quiet hours, dedupe/rate limits, owner opt-in verification, test-alert button, and acknowledgement tracking.

### G. Human handoff and live inbox
Inbox with statuses (`bot | needs_human | human | resolved`), assignment, internal notes, canned replies, takeover and "return to bot", real-time updates, browser/push/email notifications, typing indicators, visitor sees "a team member joined", SLA timers.

### H. Actions and tools (agentic)
Built-in: `search_knowledge`, `capture_lead`, `escalate_to_human`, `book_appointment` (Calendly or Google Calendar link/API; decide in feasibility). Owner-defined HTTP actions (name, description, URL, method, parameter schema, auth, test button) with SSRF protection, timeouts, confirmation for write actions, audit log, per-conversation tool limits. Outbound signed webhooks for events (`conversation.started`, `lead.created`, `escalation.created`, `conversation.resolved`) plus a documented public REST API with API keys for conversations, leads, and knowledge sources.

### I. Channels and integrations (US-relevant)
Web widget and hosted chat page (core). WhatsApp inbound chat, Facebook Messenger, Instagram DM, SMS via Twilio (US 10DLC / toll-free verification is a long-lead item; document and sandbox-test). Integrations: Slack (alerts and handoff), Zapier/Make via webhooks, HubSpot lead sync, Google Sheets lead export, Shopify product/order lookup tool. **If any item cannot be completed because of an external approval, deliver the code, verify against sandbox/test mode, and mark production status `PENDING_EXTERNAL` in the feasibility matrix.** Never silently drop it.

### J. Billing and plans (Stripe, USD)
Plans (starting hypothesis; validate with measured cost): Free, Starter, Growth, Scale, Agency; monthly + annual; credit = 1 AI reply; model tier becomes a plan feature when paid models are added later. Stripe Checkout, Customer Portal, webhooks with idempotency, Stripe Tax (US sales tax) assessed, plan gating, usage meter, overage/top-up, dunning, proration, cancel/reactivate, invoices, promo codes, free-tier abuse protection. Full design in `launch/05-BILLING-PAYMENTS.md`.

### K. Accounts, teams, security, compliance (US)
Email + Google sign-in, email verification, password reset, MFA (TOTP) for owners, roles (owner/admin/agent/viewer), team invites, multiple bots per company (limits by plan), agency/multi-workspace for the Agency plan, account export and deletion, audit log, data retention. Compliance work product (not legal advice; flag for counsel): privacy policy and terms, CCPA/CPRA data-subject requests (export/delete), DPA template, cookie/consent handling in widget, AI disclosure, CAN-SPAM, TCPA-safe messaging rules (we only message opted-in owners; visitors only in reply), COPPA stance (not for under 13), **HIPAA stance: do not market as HIPAA-compliant; warn in healthcare templates and ToS not to submit PHI**.

### L. Operator/admin console (internal)
Per-company usage, cost, margin, provider health and failover state, queue depth, error rates, ingestion failures, kill switches (disable a company, disable a provider, pause crawl), impersonation with audit trail (read-only), feature flags.

### M. UX and product polish
1. Onboarding wizard: sign up -> paste website URL or upload file -> bot built live with progress -> test chat -> customize -> copy code -> verify install. **Target: working bot in under 3 minutes**, measured.
2. Bot **playground** with retrieval inspector (shows queries, retrieved chunks, scores, tools used, final answer) for owners.
3. Industry templates (US): e-commerce, home services, dental/medical clinic (non-HIPAA), real estate, law/professional (disclaimer), restaurant/hospitality, SaaS support, agency. Each has starter prompt, greeting, suggested prompts, escalation rules, and sample FAQ.
4. Design system (consistent spacing, typography, color tokens, components), dark mode, responsive, skeleton loaders, optimistic updates, toasts, confirm dialogs for destructive actions, inline help, command palette (stretch), empty states with next-best-action.
5. Public site: landing page, pricing page matching Stripe, comparison page, docs/help center (install guides, API reference, widget API, FAQ), status page link, legal pages, SEO basics (metadata, sitemap, OG images).
6. In-app guidance: setup checklist with progress, "first value" tracking events.

---

## 3. HARD RULES

1. **Evidence or it did not happen.** Every claim cites `file:line` or a command with real output. Otherwise label `UNVERIFIED`. Never write "should work".
2. **Status labels (use exactly):** `✅ VERIFIED` (ran it, saw it pass), `🟡 PARTIAL`, `❌ MISSING`, `⚠️ BROKEN`, `UNVERIFIED`, `PENDING_EXTERNAL` (code done and sandbox-verified; waiting on a third party).
3. **Never invent** endpoints, env vars, tables, library APIs, prices, free-tier limits, or provider terms. When unsure about a third-party fact, check installed library source or current official docs (use web search/fetch) and cite it. Anything about free-tier quotas, commercial-use terms, Meta/WhatsApp rules, Stripe Tax, or carrier registration **must be verified from current official docs before you design around it**.
4. **Secrets:** never print, log, commit, or paste a secret. Placeholders only in `.env.example`. A committed secret found in the repo or git history is P0.
5. **Safe execution:** work on branches (`launch/part1`, `launch/day-<n>`). Use a disposable Postgres. No destructive commands without asking. **Stripe test mode only** until I say go live. Never message real people.
6. **No silent scope changes.** If the 10-day plan cannot fit a feature, say so explicitly with numbers and propose the smallest cut; do not quietly shrink it.
7. **Language of explanations: Banglish** (Bangla in English letters), short and clear. Code, commands, identifiers, API fields, acceptance assertions, and **all product UI copy stay in US English**.
8. **Ask in one batch.** Put all questions/keys into `launch/06-KEYS-AND-ACCOUNTS.md` and your Part 1 final reply. Do not stop for one-off questions unless fully blocked.
9. **Tests are part of the work.** No behavior change without automated tests or a scripted verification I can re-run.
10. **Self-critique pass.** Before finishing any document or day, list the 5 most likely ways your own work is wrong or will fail, check each, and fix or record them.
11. **Honesty about uncertainty.** If you are less than ~80% sure, say so and show how you would verify.

---

## 4. LLM AND AI-SERVICE POLICY (free now, paid later)

For this launch we use **free-tier AI services only**; a paid model is added after the product is final. Therefore:

1. **Provider abstraction is mandatory:** one interface each for LLM chat/stream, structured JSON output, tool calling, embeddings, reranker. Providers selected by config; **switching to a paid model must be a config/env change plus eval run, not a code change.** Record per-model capability flags (streaming, tool calling, JSON mode, context window, languages).
2. **Provider router:** ordered fallback chain, circuit breaker, per-provider token-bucket rate limiting in Redis, request queue with backpressure, timeouts, retries with jitter, automatic degrade (shorter context, simpler prompt) under pressure, per-company fairness so one tenant cannot starve others, global cost/usage counters.
3. **Candidates to evaluate** (verify current free tiers, limits, quality for grounded Q&A + tool calling + JSON, **commercial-use terms, and data-retention/training policies** before choosing): current Groq models, Google Gemini API free tier, OpenRouter free models, Cloudflare Workers AI free allocation, Cerebras, Mistral. Do not assume any of them allows production commercial use; **check and document**. If a free tier trains on submitted data or forbids commercial use, flag it as a P0/P1 risk, because it conflicts with our privacy policy and customers' data.
4. **Eval before trusting:** run the golden eval set on every candidate model and record scores; pick primary and fallbacks from results, not from brand names.
5. **Caching to save free quota:** exact-match response cache and a **tenant-scoped** semantic cache with safe invalidation on knowledge changes (never cross tenants, never serve cached answers across knowledge versions).
6. **Product honesty:** because free tiers throttle, the plan must include graceful behavior (queueing message, "high demand" UX) and a launch label such as "Public beta" if the eval/load results show the free tier cannot meet the latency target. Report this risk with numbers.
7. Keep a `launch/14-PAID-MODEL-SWITCH.md`: exact steps, env vars, eval thresholds, and cost model for moving to a paid model later.

---

## 5. RAG V2 SPECIFICATION (mandatory; the old flow must not remain)

Design, implement, and prove this pipeline. Where I say "decide", you choose with evidence and write an ADR.

**Ingestion (offline):**
1. Structure-aware parse -> normalized blocks (heading path, page, block type).
2. **Contextual chunking:** split on semantic/structural boundaries (not fixed words), target ~200-400 tokens with overlap only where needed; keep tables and FAQ pairs whole; attach `doc title > heading path` as chunk context; use a real tokenizer (the existing `chars/4` estimate is wrong for many languages). Optional LLM-generated chunk context only if the free quota allows (measure).
3. Store: raw text, contextual text, embedding, `tsvector`, metadata (tenant, bot, source, version, page, url, headings, language, updated_at). Deduplicate near-identical chunks. Content-hash change detection.
4. **Decide the vector store:** keep Pinecone or consolidate on Postgres (`pgvector` + full-text search) so hybrid retrieval is one tenant-scoped SQL query. Analyze cost, free-tier limits (Neon storage, Pinecone limits), latency, tenancy safety, ops burden, migration risk in 10 days. Keep a `VectorStore`/`Retriever` interface either way. My leaning: consolidate on Postgres if limits allow; override with evidence.

**Query time (online), in this order:**
1. **Guard + classify:** safety/injection screen on the visitor message; intent classification (question, small talk, lead intent, action request, complaint, emergency, out-of-scope). Emergency/high-severity routes to the escalation engine immediately and in parallel with answering.
2. **Query understanding:** rewrite follow-ups into a standalone query using history; for compound questions decompose into sub-queries; optionally multi-query expansion. Cap latency; fall back to the raw query on failure.
3. **Hybrid retrieval:** dense + keyword (BM25/FTS) with metadata filters (tenant, bot, published version, language), fused with Reciprocal Rank Fusion; retrieve ~30 candidates per leg.
4. **Rerank:** cross-encoder/reranker (free option verified) to top 5-8; apply adaptive thresholds calibrated on the eval set (not a hard-coded 0.25).
5. **Evidence sufficiency grading (corrective loop):** a lightweight check "does this evidence answer the question?". If insufficient: expand/re-query (different phrasing, sub-queries, widen filters) up to a hard cap (max 3 iterations, bounded latency), then either answer from evidence, ask a clarifying question, or **abstain** and offer handoff. This is the agentic part; tools (section 2H) plug into the same loop.
6. **Grounded generation:** strict system prompt; answer only from evidence + allowed tools; cite passages (source, page/heading, link) at claim level; structured output so citations are machine-checkable; tone/persona from bot settings; US English default, answer in the visitor's language.
7. **Verification:** a faithfulness check compares claims to cited evidence; if unsupported, regenerate once or abstain; never promise prices/refunds/legal/medical outcomes not in evidence. Because the answer streams, verify before final commit when risk is high, or stream only after a fast pre-check; decide and document the UX trade-off.
8. **Post-processing:** sanitize markdown/links, redact secrets/PII patterns, attach citations, produce follow-up suggestions.
9. **Record:** write a per-message evaluation record (intent, rewritten queries, retrieved ids + scores, rerank scores, loop iterations, tools called, verifier result, confidence, tokens, latency per stage, provider/model used, cost estimate, abstained?, escalated?).

**Evaluation (built Day 1-3, run on every RAG change, wired into CI nightly):**
- Golden set: >= 150 Q&A across >= 5 business types, ~85% English / ~15% Spanish, including: multi-hop questions, table lookups, follow-ups needing history, ambiguous questions, **questions not answerable from the docs (must abstain)**, prompt-injection attempts inside documents, emergency messages.
- Metrics: retrieval hit@5 and MRR, answer correctness (LLM judge with rubric + manual spot-check of 30), faithfulness/groundedness, correct-abstention rate, citation accuracy, latency p50/p95 (time to first token and total), cost per reply estimate.
- First run the **old flow as the baseline**, then report v2 vs baseline per metric. **Ship gate:** hit@5 >= 90%, faithfulness >= 95%, correct-abstention >= 90%, TTFT p50 < 2 s on the chosen free stack (if the free tier cannot meet latency, report with numbers and the mitigation); change thresholds only with a written reason.

---

## 6. ARCHITECTURE MANDATE (you decide; I expect real analysis)

You are authorized and expected to make architecture decisions. For each topic below, write a short ADR in `launch/adr/NNN-title.md`: context, options (>= 2), decision, trade-offs, migration plan, rollback. If you disagree with my leaning, say why with evidence. Topics:

1. Vector store and hybrid retrieval (Pinecone vs pgvector).
2. **Tenant isolation defense in depth:** app-level scoping plus Postgres Row-Level Security; test that a missing `company_id` filter fails closed.
3. Async architecture: separate API and worker processes, outbox pattern for events, idempotent jobs, retries with backoff, dead-letter queue, graceful shutdown.
4. LLM/provider router, caching, rate limiting (section 4).
5. Realtime: live inbox, live conversations, takeover (SSE + Redis pub/sub vs WebSocket); choose and justify.
6. Escalation/notification service as a state machine with delivery receipts (Appendix A).
7. Widget delivery: tiny loader + iframe vs Shadow DOM; `postMessage` contract; versioned immutable assets on CDN with cache strategy; backward compatibility for installed snippets; CSP.
8. API design: versioned `/v1`, OpenAPI as source of truth, generated TypeScript client for the frontend, RFC 9457 problem-details errors, cursor pagination, idempotency keys on mutating endpoints, public API keys with scopes.
9. Observability: structured logs with request/tenant/conversation IDs, OpenTelemetry traces across API -> retriever -> LLM, Sentry, metrics, SLOs (availability, TTFT, error rate), alert routing.
10. Data lifecycle: retention, soft delete, hard delete jobs, export, backups and restore drills, PII handling.
11. Configuration, secrets, feature flags, plan entitlements as a single source of truth.
12. Deployment: containers, environments (dev/staging/prod), CI/CD, expand/contract migrations for zero-downtime, rollback procedure, health/readiness checks.
13. Frontend architecture: component library/design tokens, data fetching and caching, form handling, accessibility testing, i18n (en + es), bundle budgets.
14. Billing architecture: Stripe as source of truth for payment state, our DB as cache of entitlements, reconciliation job.

---

# PART 1: AUDIT, ANALYSIS, AND LAUNCH PACK
(Read-only for product code. You may add files under `launch/`, `scripts/verify_*`, test scaffolding that does not change product behavior, and `.env.example`.)

**Order of work matters. Do not skip ahead.**

### 1.1 Build health: `launch/00-BUILD-HEALTH.md`
Map the whole repo (backend modules, routes, frontend routes, widget, migrations, scripts, docs, CI, Docker). Read all of `docs/`. List every env var from `config.py` (required/optional/default/what breaks). Run and record real output for: backend install, lint, type check, `alembic upgrade head` (plus one downgrade/upgrade cycle) on a disposable DB, full `pytest` with DB (list skipped tests), frontend install/lint/type-check/build/tests, `docker compose up`, and `scripts/smoke_phase0.py` (if keys are missing: `BLOCKED: needs keys` and list them). Table: step, command, result, first error, suspected cause, `file:line`.

### 1.2 Full site audit and feature inventory: `launch/01-FEATURE-INVENTORY.md`
Audit the **whole product**: every backend route/service/repository, every frontend page/component/hook, the widget code, migrations, jobs, scripts, and tests. Click through the UI mentally from the code (and with Playwright if it runs). For **every feature in section 2** (and any feature the code has that section 2 omits), output a row: `Area | Feature | Status label | Evidence (file:line) | Tests | Gap vs requirement | UX issues noticed`. Add a separate **UX audit** list: every screen's friction, inconsistent patterns, missing states, accessibility failures, mobile problems, slow interactions, confusing copy. End with: counts per status label, the 10 most dangerous findings, and every place docs claim something the code does not do.

### 1.3 Gap analysis and improvement plan: `launch/02-GAP-ANALYSIS.md`
For each section-2 area: current state -> required state -> gap -> proposed change (extend / refactor / rewrite) -> effort in hours (honest) -> risk -> dependencies. Include **backend, frontend, data model, infra, security, and architecture** changes. Explicitly call out where current architecture **cannot** meet a requirement and what replaces it.

### 1.4 Risks and blockers: `launch/03-RISKS-AND-BLOCKERS.md`
P0 / P1 / P2 with ID, evidence, impact, fix, effort, lane. Dedicated **security review**: tenant isolation on every route, authz, webhook signature verification, SSRF (crawl, URL fetch, owner HTTP tools, redirects, DNS rebinding), XSS in markdown/citations, **prompt injection from uploaded docs and crawled pages**, PII in logs, upload abuse, rate-limit gaps, widget origin spoofing, secrets in repo/history, session/CSRF, MFA, privilege escalation between roles, escalation-link security (signed, expiring, single-purpose), public API key handling.

### 1.5 Architecture decisions: `launch/adr/*.md` + `launch/04-ARCHITECTURE.md`
One ADR per topic in section 6, plus a target-architecture document with a diagram (Mermaid) of components, data flow for chat, ingestion, escalation, billing, and deployment. Include the final decision on vector store and provider stack **with the measured evidence you gathered** (benchmarks, eval runs, limits you verified).

### 1.6 RAG v2 spec and eval harness: `launch/05-RAG-V2-SPEC.md`
Turn section 5 into a precise implementation spec for this repo: module layout, interfaces, data schemas, prompts (with rationale), config knobs, failure modes, latency budget per stage, and the eval plan. Build the **eval harness skeleton and the first 40 golden cases** and run the **old flow baseline** now if the stack runs; record numbers.

### 1.7 Escalation, widget, and UX specs
- `launch/06-ESCALATION-DESIGN.md`: implement Appendix A as a concrete design (states, tables, templates, retries, security, tests). **Verify current WhatsApp Cloud API rules from official Meta docs** (template categories, 24-hour customer-service window, approval timelines, opt-in requirements, rate/quality limits, pricing) and cite them.
- `launch/07-WIDGET-SPEC.md`: full config schema (JSON), JS API, events, `postMessage` contract, install snippets, preview-editor behavior, accessibility checklist, performance budget, browser matrix, security model.
- `launch/08-UX-SPEC.md`: information architecture, screen list, user flows (onboarding, install, handoff, gap fix), design tokens, component inventory, copy guidelines, empty/error/loading state rules, accessibility targets (WCAG 2.1 AA, axe clean), Lighthouse targets (>= 90 performance/accessibility on marketing and dashboard shell), time-to-first-value target.

### 1.8 Billing, compliance, keys
- `launch/09-BILLING-PAYMENTS.md`: Stripe design from section 2J: Products/Prices (lookup keys), Checkout, Portal, Stripe Tax decision, webhook events + idempotency table + out-of-order tolerance, schema (`plans`, `plan_features`, `subscriptions`, `usage_events`, `invoices`, `stripe_events`), entitlement + quota model replacing the 100/1000 daily limits (keep a global circuit breaker), lifecycle (upgrade, downgrade, cancel, failed payment/dunning, refund, reactivate, account deletion with active subscription), local testing with Stripe CLI + test clocks + test cards, live-switch checklist, and a **cost-per-reply model from the real pipeline** with margin per plan (flag any plan < 75% gross margin; with free LLMs cost is near zero, so also model the paid-model scenario).
- `launch/10-COMPLIANCE-US.md`: privacy/terms/DPA outlines, CCPA/CPRA requests flow, cookie/consent handling, AI disclosure, CAN-SPAM, TCPA, COPPA, HIPAA stance, subprocessor list (every AI/infra provider we send data to), data retention. Mark "needs attorney review".
- `launch/11-KEYS-AND-ACCOUNTS.md`: for each external service: why, day needed, env var names, where to get it (exact dashboard path/URL), test vs live, limits/cost (cited or `NEEDS VERIFICATION`), security notes. Cover at least: Stripe (secret, publishable, webhook secret, price IDs, Tax), AI providers (each free candidate), reranker, Cloudflare (embeddings/R2), Pinecone (if kept), Neon (pooled + direct), Redis, object storage, Sentry, transactional email (verified domain, SPF/DKIM/DMARC), **Meta/WhatsApp Cloud API (app ID/secret, WABA ID, phone number ID, permanent token, webhook verify token, business verification, template approval)**, Twilio (SMS fallback, 10DLC/toll-free verification), Slack app, Telegram bot, Google OAuth, Google Calendar/Sheets, HubSpot, Shopify partner/dev store, Calendly, analytics, uptime monitor, DNS/TLS for `app.`/`api.`/`cdn.`. Provide complete `.env.example` files and a **"first 60 minutes" checklist** ordered by what unblocks the most work. **Flag long-lead items** (Meta business verification, WhatsApp template approval, Twilio registration, email domain warm-up) so I start them immediately.

### 1.9 Feasibility matrix: `launch/12-FEASIBILITY-MATRIX.md`
For **every** section-2 feature: estimate (hours), lane, day, dependencies, external approvals, and a verdict: `FITS_10_DAYS`, `FITS_WITH_CUT` (describe exactly what is cut and why), or `NEEDS_MORE_TIME` (with how many extra days). State your capacity assumptions (number of parallel lanes, hours per day, my review time) and compute total hours vs capacity. **Do not claim 100% possible unless the arithmetic supports it.** If it does not fit, propose the minimum change (e.g., ship Instagram + SMS on Day 11-12, or defer OCR) while keeping launch-critical items.

### 1.10 Ten-day sprint: `launch/13-SPRINT-10-DAYS.md`
Start from this skeleton and **adjust it to audit findings** (explain every deviation). Lanes run in parallel; each day has **8 to 12 tasks across lanes**.

| Day | Theme |
| --- | --- |
| 1 | Make it run: migrations, tests, real-provider smoke, build health green, staging deploy, repo cleanup, ADR decisions made, eval harness + old-flow baseline, **start all long-lead external approvals** |
| 2 | Foundations: provider router + free-LLM stack, Redis/object storage, RLS + tenancy hardening, API conventions (`/v1`, OpenAPI client), worker/outbox, observability (Sentry/OTel), Stripe products + billing schema |
| 3 | RAG v2 ingestion: structure-aware parsing, contextual chunking, hybrid index (and vector-store decision executed), versioning, re-crawl/change detection, knowledge manager backend; golden set to 150 |
| 4 | RAG v2 runtime: guard/intent, rewrite/decompose, hybrid + rerank, sufficiency loop, grounded generation + citations, verifier/abstain; eval v2 vs baseline; Stripe Checkout/webhooks/portal/entitlements |
| 5 | Agent + actions + escalation core: tool loop, owner HTTP tools, emergency/severity detection, escalation state machine, email/Slack/Telegram/SMS channels, handoff backend, per-message evaluation records |
| 6 | WhatsApp escalation (templates, delivery webhooks, ACK, fallbacks, opt-in) + live inbox/takeover (realtime) + visitor channel adapters start (WhatsApp/Messenger/Instagram) |
| 7 | Widget v2: full customization schema, JS API, loader, install options, live preview editor, a11y, widget analytics; knowledge manager UI |
| 8 | Owner monitoring: live view, transcripts, analytics, gap dashboard, bad-answers/correction flow, alert rules, reports; billing UI complete; account/MFA/teams/roles |
| 9 | Product polish + hardening: onboarding wizard, templates, playground, marketing site, docs/help center, legal pages, public API + webhooks + integrations (Slack/Zapier/HubSpot/Sheets/Shopify), full security suite, load test, a11y/Lighthouse fixes |
| 10 | Launch: full regression, eval report, backup restore drill, Stripe live switch with one real transaction + refund, demo bots, launch gate review, go-live, support rota, monitoring on |

**Every task uses this exact template:**
```
### D<day>.<n> <Title>
- Lane: A Backend/AI | B Frontend/UX | C Infra/Billing/Realtime | D Quality/Security
- Feature refs: <section 2 IDs, e.g. F, D.3>
- Depends on: <task IDs or none>
- Estimate: <hours, honest>
- Files likely touched: <real paths>
- Claude Code instruction (copy-paste ready, self-contained):
  """
  Goal, context, exact modules/files, constraints, what NOT to touch, design to follow (link ADR/spec),
  required tests, commands to run, UX requirements (states, a11y, copy), and the exact definition of done.
  """
- Acceptance criteria (all must pass): numbered, observable, with exact commands/URLs and expected outputs/status codes
- Verification commands:
- Rollback:
- Needs from owner: <keys/decisions/none>
```
Also per day: **Day gate** (pass/fail list; next day does not start until green), **buffer** (reserve >= 15% of day capacity), **scope-cut order** (never cut: tenant isolation, billing correctness, escalation reliability, eval ship-gate, backups, privacy/terms/AI disclosure, accessibility basics), and a **docs/CHANGELOG update task**.

### 1.11 API test plan and runnable tests: `launch/14-API-TEST-PLAN.md` + code
1. Table of **every** route: method, path, auth, request schema, response schema, expected codes; cross-check with OpenAPI and flag drift.
2. Per route: happy path, validation failure, unauthenticated, wrong-tenant, wrong-role, rate-limited, idempotent retry where relevant, each with exact expected status and body shape.
3. Real test files for suites: auth + MFA; ingestion (all formats, oversize, corrupt, duplicate, retry, delete removes vectors); RAG v2 (stage-level unit tests + end-to-end with fake providers + eval); chat SSE format + abort + quota; **tenant isolation iterating every authenticated route with Company B credentials**; RLS fail-closed; widget origin enforcement + signed identity; escalation (trigger rules, state machine, retries, fallbacks, dedupe, quiet hours, link security) using a fake WhatsApp/SMS server; handoff inbox realtime; billing (signature failure, duplicate event, out-of-order, each event type, upgrade/downgrade, gating, over-quota); public API keys/scopes; outbound webhook signing/retry; SSRF and XSS payload suites; prompt-injection suite.
4. Tooling: pytest (DB tests in CI with service Postgres), HTTP collection (`.http`/Bruno) with curl equivalents, **Playwright e2e** for the golden path (signup -> onboarding -> upload -> ready -> customize widget -> install snippet on a test page -> visitor chat with citation -> emergency message -> escalation delivered to fake WhatsApp -> takeover -> resolve -> analytics shows it -> upgrade via Stripe test checkout), axe accessibility checks, Lighthouse CI, **k6** load test (50-100 concurrent streams; report TTFT p50/p95, error rate, provider throttling behavior).
5. `scripts/verify_launch.sh`: runs everything in order, prints a **PASS/FAIL table**, exits non-zero on any failure. This is my one-command proof.

### 1.12 Launch gate: `launch/15-LAUNCH-GATE.md`
Checklist rows: `Check | How to verify | Expected | Status | Evidence`. Sections: Product golden path on production URL; every section-2 feature verified or `PENDING_EXTERNAL` with sandbox proof; Billing (real payment + refund done, webhook failure alerting); Security (isolation suite green, RLS fail-closed, secrets scan clean, rate limits, MFA); Reliability (load numbers, SSE through production proxy, health checks, Sentry live, backup restore done); Quality (eval ship-gate numbers); Accessibility/performance (axe clean, Lighthouse targets); Legal (privacy, terms, DPA, AI disclosure, CAN-SPAM footer, deletion works); Support (channel, SLA, status page); Marketing (landing, pricing matches Stripe, demo bots, analytics events). **Any unchecked Product/Billing/Security/Escalation line blocks launch.**

### 1.13 PART 1 final reply (only this)
1. Files created.
2. Counts of features by status label.
3. Top 10 blockers.
4. **Feasibility verdict** for 10 days with the capacity arithmetic, the biggest schedule risk, and the exact cuts you recommend (if any).
5. Keys/accounts I must provide before Day 1 (names only) and the **long-lead approvals I must start today**.
6. The 5 architecture decisions that change the most and why.
7. Your self-critique: the 5 most likely ways this plan fails.
Then stop and wait.

---

# PART 2: EXECUTION (only on `Execute PART 2, DAY <n>`)

1. Branch `launch/day-<n>`. Re-read the day's tasks, the ADRs, the specs, and the risk list.
2. Implement tasks in dependency order. Per task: plan -> tests first or alongside -> implement -> run verification commands -> fix until green -> self-review the diff (security, tenancy, error handling, states, a11y, performance) -> small commit (`D4.3 sufficiency loop + tests`).
3. UI work must be **looked at**: run the app, use Playwright to load every changed screen at desktop and mobile widths, capture screenshots into `launch/screens/day-<n>/`, run axe, and fix what you see (spacing, alignment, contrast, truncation, flicker, empty/error states, copy). Do not call UI done from code alone.
4. After each task append to `launch/DAY-<n>-REPORT.md`: task ID, files changed, commands run with **real output excerpts**, each acceptance criterion pass/fail, deferred items + why.
5. End of day: run `scripts/verify_launch.sh`, paste the PASS/FAIL table, run the eval and paste numbers vs baseline (from Day 3 on), evaluate the **Day gate**. If red, fix before reporting; if blocked, state exactly what you need.
6. Update `launch/01-FEATURE-INVENTORY.md` statuses, `launch/12-FEASIBILITY-MATRIX.md`, README, docs, CHANGELOG so documentation matches reality.
7. Final reply for the day: gate GREEN/RED, tasks done vs planned, new risks, manual actions needed from me (keys, DNS, approvals), and **"review these lines yourself"** (auth, billing, webhooks, tenant checks, RLS, SSRF, escalation links, secrets).

**Definition of Done (any task):** merged to the day branch; automated tests added and passing; verification output recorded; UI verified visually at two widths with axe clean; docs updated; no new lint/type errors; no secrets in diff; rollback noted; no stubs.

**Stop and tell me instead of pushing on if:** a migration would hit a non-disposable DB, a test only passes by weakening security, a required key is missing, a provider behaves differently from the design, a free tier forbids our use, or a requirement conflicts with the launch scope.

---

# QUALITY BARS (apply to everything)

- **Backend:** typed, validated inputs; consistent error format; no N+1 queries (check query plans on hot paths); indexes for every list/filter; idempotent writes; transactions around multi-step changes; structured logs; p95 API latency < 300 ms for non-LLM endpoints; chat TTFT p50 < 2 s on the free stack (report if not met).
- **Frontend:** consistent design system; no layout shift; skeletons not spinners for lists; every form has validation + inline errors + disabled/submitting states; every destructive action confirms; keyboard navigable; focus states; dark mode; mobile-first responsive; bundle budget tracked; Lighthouse >= 90 (performance + accessibility) on landing and dashboard shell; axe: zero serious/critical violations.
- **Widget:** loader < ~10 KB gzipped (report actual), async, no console errors on host pages, no global CSS leakage, works with strict CSP hosts when instructions are followed.
- **Security:** OWASP ASVS-style review of auth, session, access control, input handling; dependency audit (pip-audit / npm audit) with no known high/critical unresolved; secrets scan (gitleaks) clean including history.
- **Testing:** unit + integration + e2e; the cross-tenant suite and the billing/escalation suites are mandatory and run in CI; no skipped tests without a documented reason.
- **Docs:** every public API, widget option, and install path documented with working examples that you actually executed.

---

# APPENDIX A: ESCALATION / EMERGENCY ENGINE (design requirements)

**Detection (run in parallel with answering; never delay the visitor's reply):**
1. Visitor explicit signals ("urgent", "emergency", "I need a human", "lawyer", "chargeback", "refund now", "cancel").
2. Classifier output (cheap LLM + rules) with categories and severity: `critical` (life/safety/medical emergency, credible threat), `high` (angry/churn risk, high-value lead, legal threat, payment/fraud, service outage complaint), `medium` (repeated bot failure, unanswerable twice, tool failure), `low`.
3. Owner-defined rules (keywords, intents, page, VIP/customer attributes, value thresholds, time of day).
4. Behavioral triggers: N consecutive abstentions, repeated thumbs-down, visitor frustration signals.

**Safety behavior for the visitor:** for possible life-threatening emergencies the bot immediately says (US) to call **911** (and **988** for suicide/crisis), gives no medical/legal advice, and escalates the business owner at `critical`. This default cannot be disabled by the owner. For non-emergency escalation the bot states clearly what happens next, expected response window (from business hours settings), and asks for a callback phone/email with consent text.

**Owner message content (WhatsApp, short and useful):** severity, one-line reason, 2-3 line AI summary of the situation, key details extracted (name, order/booking id, product, amount if present), visitor contact if provided, page URL, local time, and a **secure deep link** to the takeover screen. Full transcript is **not** pasted into WhatsApp by default (privacy); owner setting can include a short excerpt. Link: signed, expiring, scoped to that conversation, requires login or one-time magic link with step-up as configured.

**WhatsApp constraints you must design around (verify in current Meta docs):** business-initiated messages outside the customer-service window require **pre-approved templates**; templates have categories, variable limits, and approval time; the recipient must have opted in; quality rating and messaging limits exist; delivery/read status arrives by webhook. Therefore: create the template set (e.g., `escalation_critical`, `escalation_high`, `daily_digest` if useful) with variables for severity/summary/link; provide the exact template text for me to submit; implement a **sandbox/test path** so the engine is fully testable before approval; when the owner has an open 24-hour session, allow richer free-form messages; implement optional two-way reply relay (`ACK`, `TAKE`, free-text reply into the conversation) if feasible, otherwise document why not.

**Delivery engine (state machine):** `created -> queued -> sent -> delivered -> acknowledged` with failure paths `failed -> fallback_channel -> ... -> escalated_to_backup`. Per-channel retries with backoff; **fallback channels** in owner-configured order (SMS via Twilio, email, Slack, Telegram, push); **acknowledgement** by link open, reply, or button; **re-escalation** if not acknowledged within SLA by severity (e.g., critical 3 min, high 10 min; make configurable); **escalation chain** (primary -> backup -> team group); **quiet hours** per owner timezone with `critical` override; **dedupe/merge** (one alert per conversation per window, update with new context instead of spamming); **alert-storm protection** (per-company rate limit + digest mode); every attempt written to an audit table with provider message IDs and status; metrics and alerts for delivery failure rate.

**Owner setup UX:** number entry with verification code (proves ownership and records opt-in with timestamp and consent text), channel priority drag-and-drop, quiet hours, rules builder, severity SLAs, **"Send test alert"** button that exercises the real path and shows delivery status live, and an escalation log page.

**Tests (all automated with fake provider servers):** every trigger type, severity mapping, safety response text for critical, template variable rendering and length limits, retry/backoff, fallback ordering, ACK handling, re-escalation timing (fake clock), quiet-hours override, dedupe/merge, storm protection, link signing/expiry/replay, opt-in enforcement (never message an unverified number), tenant isolation of alerts.

---

# APPENDIX B: Output checklist (PART 1 must create all)

```
launch/00-BUILD-HEALTH.md          launch/08-UX-SPEC.md
launch/01-FEATURE-INVENTORY.md     launch/09-BILLING-PAYMENTS.md
launch/02-GAP-ANALYSIS.md          launch/10-COMPLIANCE-US.md
launch/03-RISKS-AND-BLOCKERS.md    launch/11-KEYS-AND-ACCOUNTS.md
launch/04-ARCHITECTURE.md          launch/12-FEASIBILITY-MATRIX.md
launch/adr/*.md                    launch/13-SPRINT-10-DAYS.md
launch/05-RAG-V2-SPEC.md           launch/14-API-TEST-PLAN.md
launch/06-ESCALATION-DESIGN.md     launch/15-LAUNCH-GATE.md
launch/07-WIDGET-SPEC.md           launch/16-PAID-MODEL-SWITCH.md
backend/test/** (route, tenant-isolation, RLS, security, billing, escalation, eval)
frontend/e2e/** (Playwright golden path + axe)
scripts/verify_launch.sh   scripts/api_checks.* (.http/Bruno)   scripts/loadtest.js (k6)
.env.example (backend + frontend, placeholders only)
```

Begin PART 1 now. Think deeply, work in the order given, and do not stop until every PART 1 file exists.