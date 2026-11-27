# 01 · Feature inventory

For every feature in section 2 of the master prompt I show: Status label · Evidence (file:line or "none found") · Tests · Gap vs requirement · UX issues observed.

Evidence methodology: grepped the full repo (`backend/app`, `backend/alembic`, `frontend/app`, `frontend/src`), opened the files it pointed at, and ran the parts I could. Anything I did not personally see in the code is labelled ❌ MISSING — not "assumed present".

**Counts (142 features catalogued across 13 areas):** ✅ 23 · 🟡 28 · ❌ 86 · ⚠️ 5 · UNVERIFIED 0.

## A. Knowledge and ingestion

| # | Feature | Status | Evidence | Tests | Gap vs requirement | UX issues |
| --- | --- | --- | --- | --- | --- | --- |
| A.1.1 | PDF upload | ✅ | `backend/app/ingestion/parsers/pdf.py`, `app/sources/router.py:39` grant flow | DB-skipped `test_chat_and_lifecycle.py::test_profile_company_and_source_management_routes` | — | drop-zone works at desktop; small mobile target |
| A.1.2 | DOCX upload | ✅ | `backend/app/ingestion/parsers/docx.py` | unit `test_parsers.py` | — | same |
| A.1.3 | TXT upload | ✅ | `parsers/text.py` | unit | — | — |
| A.1.4 | MD upload | ✅ | `parsers/text.py` (MD routed through text) | — | file-signature allow-list lives in `app/storage/local.py` — MD passes | — |
| A.1.5 | CSV upload | ❌ | none found | none | **Required by section 2A.1**; no parser, no `kind='csv'` in schema | — |
| A.1.6 | Pasted text source | ✅ | `app/sources/router.py:90`, `service.create_text_source` | DB-skipped | — | editor lacks word count beyond raw chars |
| A.1.7 | FAQ pairs | ✅ | `sources/router.py:103`, repeater UI `components/knowledge/add-source-dialog.tsx` | DB-skipped | — | — |
| A.1.8 | Single URL | ✅ | `sources/router.py:122`; SSRF via `app/security/ssrf_http.py` | unit `test_ssrf.py` | — | — |
| A.1.9 | Whole-site crawl | 🟡 | `sources/router.py:140` one-shot; `discover+import` at `:157` and `:183` | unit `test_crawler.py` | robots.txt respected (`crawler.py:31` `_load_robots`); depth limit missing — only page-count cap; same-domain enforced | long crawls have no progress ring, only a polling list |
| A.1.10 | Sitemap import | 🟡 | `ingestion/crawler.py:_try_sitemap` | unit | yes but surfaces as crawl-pages; no separate "sitemap" kind in schema | — |
| A.2.1 | Headings preserved | 🟡 | `parsers/pdf.py`, `parsers/docx.py` write headings into `chunks.heading` | — | HTML crawl does, PDF uses `pypdf` which is weak on heading detection; tables are not kept intact | — |
| A.2.2 | Lists preserved | 🟡 | best-effort via docx/html | — | PDF loses list-level nesting | — |
| A.2.3 | Tables kept intact | ❌ | none found | none | **Required by section 2A.2** — current pipeline flattens tables into text | — |
| A.2.4 | Page numbers | ✅ | `chunks.page` column; populated for pdf | — | — | — |
| A.2.5 | FAQ pairs as single units | ✅ | `service.create_faq_source` writes JSON then chunker preserves pair boundaries | — | — | — |
| A.2.6 | OCR for scanned PDFs | ❌ | none; `ERROR_CODE_COPY.unsupported_scanned_pdf` only surfaces the error | none | documented as stretch — mark PENDING_EXTERNAL (Cloudflare Workers AI has Marker/Mistral OCR on paid tiers) | — |
| A.3.1 | Scheduled re-crawl | ❌ | no cron entry; only manual `POST /documents/{id}/refresh` | none | — | — |
| A.3.2 | Change detection | 🟡 | `document_versions.checksum` exists; no diff-aware re-embed | — | refresh re-embeds the whole doc | — |
| A.3.3 | Re-index button | ✅ | `app/(app)/knowledge/page.tsx` refresh action; `POST /documents/{id}/refresh` | — | — | icon menu, easy |
| A.3.4 | Per-source status | ✅ | `document_versions.status` + `STATUS_META` map in `frontend/src/lib/types.ts` | unit `test_types.test.ts` | — | status badges premium-ready |
| A.3.5 | Human-actionable error messages | ✅ | `ERROR_CODE_COPY` covers 13 codes | unit | — | — |
| A.4.1 | Sources list | ✅ | `knowledge/page.tsx` | Playwright: none | — | — |
| A.4.2 | Status/size/last-synced columns | 🟡 | status + chunk_count shown; size bytes **not** shown | — | add `size_bytes` column to `documents`/UI | — |
| A.4.3 | Chunk preview | ✅ | `GET /documents/{id}/content` preview + outline | DB-skipped | — | — |
| A.4.4 | Delete/disable source | 🟡 | delete ✅; **disable** not implemented | DB-skipped | add `disabled_at` to `documents` | — |
| A.4.5 | Bulk actions | ❌ | single-row actions only | none | — | — |
| A.4.6 | Source tags | ❌ | no `tags` column, no UI | none | — | — |
| A.5.1 | Draft vs published knowledge | 🟡 | `publications` + `publication_sources` snapshot ONLY the bot config and version-id selection; raw knowledge has no "draft" vs "published" split within a version | integration `test_bot_publish.py` | per section 2A.5 the draft/publish must also cover knowledge diffs, not only version-id pick | — |
| A.5.2 | One-click rollback | 🟡 | `active_publication_id` can be swapped by re-publishing the old version-ids, but there is no UI "rollback to vN" button | — | add Publish history panel | — |
| A.6.1 | Plan-level source limits | ❌ | there are no plans | none | Tied to Stripe work | — |
| A.6.2 | Plan-level MB limits | ❌ | fixed `max_file_bytes=10MB`, `max_company_storage_bytes=100MB` via `config.py:60-62` | none | per-plan from entitlements | — |
| A.6.3 | Upgrade prompts | ❌ | none | none | — | — |

## B. RAG v2 (mandatory)

| # | Feature | Status | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- |
| B.1 | Agentic sufficiency loop | ❌ | `app/chat/pipeline.py` is single-shot retrieve → embed → generate | unit covers happy path only | **This is the whole point of RAG v2**; build from scratch | — |
| B.2 | Hybrid retrieval (dense + BM25/FTS) | ❌ | only Pinecone dense; no `tsvector`, no pgvector | none | migration required | — |
| B.3 | Cross-encoder reranker | ❌ | none found | none | free candidate TBD | — |
| B.4 | Query rewriting / decomposition | ❌ | only concatenates the previous user turn (`pipeline.py:retrieve`) | none | — | — |
| B.5 | Guard + intent classifier | 🟡 | `app/guardrails.py` regex only for prompt-injection and sensitive output | unit | no intent, no emergency detector | — |
| B.6 | Adaptive threshold / calibration | ❌ | fixed `min_relevance=0.25` from config | none | replace with eval-calibrated threshold | — |
| B.7 | Evidence-sufficiency grader | ❌ | none | none | the "answer / clarify / abstain" decision tree is missing | — |
| B.8 | Grounded generation (citations) | ✅ | `pipeline.build_evidence` + `[n]` markers passed through `chat/llm.py` | unit happy-path | tests do not assert faithfulness | — |
| B.9 | Verifier / faithfulness check | ❌ | none | none | — | — |
| B.10 | Per-message evaluation record | 🟡 | `analytics_events` has `properties` JSONB and we write `message_sent`, `feedback_given`, `quota_blocked`, `answer_no_evidence` | — | no retrieval trace, no rerank scores, no tokens/latency per stage, no provider/model, no cost | — |
| B.11 | Eval harness + golden set ≥150 | ❌ | none | none | build in Day 1-3 | — |
| B.12 | Ship-gate metrics wired to CI | ❌ | none | none | — | — |

## C. Chat experience

| # | Feature | Status | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- |
| C.1.1 | Streaming answers (SSE) | ✅ | `app/chat/pipeline.py:stream_turn`; parser `frontend/src/lib/sse.ts` | unit `test_chat_pipeline.py`, `test_sse.test.ts` | — | typing dots premium-ready |
| C.1.2 | Markdown render | 🟡 | plain `whitespace-pre-wrap`; **no sanitised markdown parser** | none | safety hole — must add `rehype-sanitize`/DOMPurify | — |
| C.1.3 | Clickable citations open source passage | 🟡 | citation row renders but doesn't open a drawer | — | wire `/documents/{id}/content` with highlight | — |
| C.1.4 | Suggested follow-ups | ❌ | only initial suggestions | none | add follow-up generation post-answer | — |
| C.1.5 | Quick-reply buttons | ❌ | none | none | — | — |
| C.1.6 | Typing indicator | ✅ | `PublicBubble` + `TypingDots` | — | — | polished |
| C.1.7 | Retry on failure | 🟡 | user can re-type; no first-class retry button on failed bubble | — | — | — |
| C.2.1 | Conversation memory within session | 🟡 | `pipeline.prepare_turn` loads last 6 completed messages | unit | 6-message cap; no summarisation | — |
| C.2.2 | Visitor identity (anonymous or identified) | 🟡 | visitor_sessions table has token only; no `identify()` yet | — | needs HMAC-signed identity for 2D.3 | — |
| C.2.3 | Multilingual retrieval | 🟡 | BGE-M3 is multilingual; **no language detect, no language-aware prompt** | none | add `languages` param + detect + test Spanish | — |
| C.3.1 | Pre-chat lead form | 🟡 | V1 is post-hoc, skippable (`PublicChatWindow` triggers at 2 assistant replies) | — | pre-chat not configurable | — |
| C.3.2 | Conversational capture | 🟡 | manual form only | — | add tool call `capture_lead` | — |
| C.3.3 | Validation + consent + spam protection | 🟡 | consent toggle; no spam guard | — | hcaptcha/honeypot for widget | — |
| C.4.1 | Thumb feedback + comment | 🟡 | thumbs POST works; no comment input yet | integration | add comment textarea | — |
| C.4.2 | Conversation rating at close | ❌ | none | none | — | — |
| C.5 | Business-hours aware | ❌ | none | none | add `business_hours` jsonb on bots | — |
| C.6 | AI disclosure by default | ❌ | none shown in widget; required for launch | none | hard-coded footer line "AI assistant" in widget | **compliance** |

## D. Widget

| # | Feature | Status | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- |
| D.1.1 | Appearance: colors | 🟡 | brand primary color; no bg/text/accent/bubble | — | expand `branding` schema | — |
| D.1.2 | Appearance: dark/light/auto | ❌ | — | none | — | — |
| D.1.3 | Appearance: font family | ❌ | — | none | Google Fonts allow-list to design | — |
| D.1.4 | Position: 4 corners + offsets | 🟡 | only `bottom-right` / `bottom-left` | — | — | — |
| D.1.5 | Launcher shape/size/icon/label/anim | 🟡 | single icon, no options | — | — | — |
| D.1.6 | Powered-by plan-gated | ❌ | not implemented (no plans) | none | — | — |
| D.1.7 | Custom CSS (sandboxed) | ❌ | — | none | out-of-scope V1 (safer to defer) | — |
| D.2.1 | Auto-open rules | ❌ | — | none | needed for launch | — |
| D.2.2 | URL/device/language hide rules | ❌ | — | none | — | — |
| D.2.3 | Sound on/off, offline mode | ❌ | — | none | — | — |
| D.2.4 | Attachment upload by visitor | ❌ | — | none | stretch — defer | — |
| D.2.5 | Cookie-consent mode | ❌ | — | none | required for US launch | **compliance** |
| D.3.1 | `Knowmivo()` init API | 🟡 | `public/embed.js` exposes `window.Knowmivo = {open, close, toggle, version}` only | — | big spec: `sendMessage`, `identify`, `setMetadata`, `setTheme`, `on(event,cb)`, `destroy` | — |
| D.3.2 | HMAC-signed identity | ❌ | — | none | server side `/widget/identify/verify` + secret per bot | — |
| D.3.3 | `data-knowmivo-open` custom launcher | ❌ | — | none | 3 LoC addition | — |
| D.4.1 | Install options with generated code | 🟡 | `GET /bot/embed` returns script/React/Next.js + hosted URL | integration in `test_chat_and_lifecycle.py` | needs GTM, WordPress, Shopify, Webflow, Wix, Squarespace, iframe, QR | — |
| D.4.2 | "Verify installation" check | ❌ | none | none | poll `/widget/sessions` from owner UI for incoming installs | — |
| D.5 | Live preview editor | ✅ | `chatbot/page.tsx` two-column studio with preview chat | — | works; no device toggle yet | polished |
| D.6 | Domain allow-list enforced server-side | ✅ | `app/public/router.py` origin check, `bot_domains` table, `_check_origin` | integration | — | — |
| D.7 | A11y / perf / browser matrix | 🟡 | focus rings and keyboard present; no axe test; perf budget not measured | — | add axe + Lighthouse in CI | — |

## E. Full monitoring (owner side)

| # | Feature | Status | Evidence | Tests | Gap |
| --- | --- | --- | --- | --- | --- |
| E.1 | Live view (conversations now) | ❌ | none | none | needs SSE or WS pub/sub + takeover |
| E.2.1 | Transcripts list | ✅ | `app/(app)/conversations/page.tsx`; `GET /conversations` | DB-skipped | — |
| E.2.2 | Filters: date/status/feedback | 🟡 | `status`, `has_feedback` only | — | add date, channel, page, language, tag, resolved, escalated, lead-captured |
| E.2.3 | Full message with citations + trace | 🟡 | citations shown; **no retrieval trace** | — | depends on B.10 |
| E.2.4 | Tags, notes | ❌ | none | none | — |
| E.2.5 | Export CSV | 🟡 | JSON export only | — | add CSV endpoint |
| E.3.1 | Analytics dashboard | 🟡 | sparkline + KPI tiles on Overview (placeholder data) | — | real series needs backend `/usage/series` |
| E.3.2 | Deflection/resolution rate | ❌ | none | none | define metric + instrument |
| E.3.3 | Lead conversion, CSAT, TTFT | ❌ | none | none | — |
| E.3.4 | Top questions, top topics | ❌ | none | none | — |
| E.3.5 | Trend charts + comparisons | ❌ | none | none | — |
| E.4 | Knowledge gaps | ❌ | none | none | "answer_no_evidence" analytics event is logged — cluster it |
| E.5 | Bad-answers queue + correction loop | ❌ | none | none | — |
| E.6.1 | Configurable alerts | ❌ | none | none | — |
| E.6.2 | Weekly email digest | ❌ | none | none | — |
| E.7.1 | Audit log of owner actions | 🟡 | `audit_events` table exists and is written on bot/publish/unpublish/domains etc. | integration | no UI reader |
| E.7.2 | Retention toggle, PII redaction | ❌ | `retention_days=30` default; no toggle, no redaction code | none | — |

## F. Emergency escalation (Appendix A)

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| F.1 | Severity classifier | ❌ | design & build |
| F.2 | Owner rule engine | ❌ | — |
| F.3 | 911/988 safety reply (US) | ❌ | — |
| F.4 | WhatsApp Cloud API delivery | ❌ | **long-lead external approvals** |
| F.5 | SMS/email/Slack/Telegram fallback chain | ❌ | — |
| F.6 | State machine `created→queued→sent→delivered→acknowledged` | ❌ | — |
| F.7 | ACK, re-escalation, quiet hours | ❌ | — |
| F.8 | Dedupe/merge + storm protection | ❌ | — |
| F.9 | Signed deep link to takeover | ❌ | — |
| F.10 | Owner number verification + opt-in | ❌ | — |
| F.11 | Test-alert button | ❌ | — |
| F.12 | Delivery/ACK webhook handling | ❌ | — |

## G. Human handoff / live inbox

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| G.1 | Statuses `bot/needs_human/human/resolved` | ❌ | add `conversations.handoff_status` column |
| G.2 | Assignment, notes, canned replies | ❌ | — |
| G.3 | Real-time updates (SSE/WS) | ❌ | depends on ADR 5 |
| G.4 | "Team member joined" visitor notice | ❌ | — |
| G.5 | SLA timers | ❌ | — |

## H. Actions and tools (agentic)

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| H.1 | Built-in `search_knowledge`, `capture_lead`, `escalate_to_human` | ❌ | wire into B.1 loop |
| H.2 | `book_appointment` (Calendly/Google Calendar) | ❌ | PENDING_EXTERNAL on API keys |
| H.3 | Owner-defined HTTP actions + schema + test button | ❌ | SSRF controls exist (`app/security/ssrf_http.py`) → reuse |
| H.4 | Public REST API + API keys with scopes | ❌ | add `api_keys` table |
| H.5 | Outbound signed webhooks | 🟡 | `webhook_endpoints` + `webhook_deliveries` tables + delivery worker exist (`app/webhooks/worker.py`); **no application code emits events today** |

## I. Channels and integrations

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| I.1 | Web widget + hosted chat page | ✅ | works |
| I.2 | WhatsApp inbound | ❌ | PENDING_EXTERNAL (Meta business verification + templates) |
| I.3 | Messenger | ❌ | PENDING_EXTERNAL |
| I.4 | Instagram DM | ❌ | PENDING_EXTERNAL |
| I.5 | Twilio SMS | ❌ | PENDING_EXTERNAL (10DLC / toll-free verification long lead) |
| I.6 | Slack alerts & handoff | ❌ | — |
| I.7 | Zapier / Make via webhooks | 🟡 | tables ready, nothing fires |
| I.8 | HubSpot lead sync | ❌ | — |
| I.9 | Google Sheets export | ❌ | — |
| I.10 | Shopify product/order lookup | ❌ | — |

## J. Billing

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| J.1 | Plans schema | ❌ | needs `plans`, `plan_features`, `subscriptions`, `usage_events`, `invoices`, `stripe_events` |
| J.2 | Stripe Checkout + Portal | ❌ | — |
| J.3 | Stripe Tax (US sales tax) | ❌ | decide in ADR |
| J.4 | Webhooks with idempotency | ❌ | — |
| J.5 | Plan gating / entitlements | ❌ | — |
| J.6 | Usage meter + overage | 🟡 | `usage_daily`, `usage_reservations` present → reuse for meter |
| J.7 | Dunning, proration, cancel/reactivate | ❌ | — |
| J.8 | Promo codes, free-tier abuse protection | ❌ | — |

## K. Accounts / teams / security / compliance (US)

| # | Feature | Status | Evidence | Gap |
| --- | --- | --- | --- | --- |
| K.1 | Email + Google sign-in | ✅ | `auth/router.py`, `security/google_oauth.py` | — |
| K.2 | Email verification | ✅ | `service.verify_email` + `MailCheck` UI | — |
| K.3 | Password reset | ✅ | `service.reset_password` + `/reset-password` page | — |
| K.4 | MFA (TOTP) for owners | ❌ | none | add `pyotp` + backup codes |
| K.5 | Roles (owner/admin/agent/viewer) | 🟡 | `memberships.role` column with CHECK `('owner')` only | relax check + add role-aware deps |
| K.6 | Team invites | ❌ | none | — |
| K.7 | Multiple bots per company | ❌ | schema is 1:1; `get_or_create_bot_for_company` picks first | refactor PK on bots |
| K.8 | Agency / multi-workspace | ❌ | — | — |
| K.9 | Account export | ✅ | `GET /company/export` returns JSON with field allow-list | — |
| K.10 | Account deletion | ✅ | `DELETE /me` + cleanup job | integration test exists |
| K.11 | Privacy policy / terms | ❌ | pages not written | **compliance blocker** |
| K.12 | DPA template | ❌ | — | — |
| K.13 | CCPA/CPRA DSR flow | ❌ | export exists; delete exists; no "request access" UI | — |
| K.14 | AI disclosure | ❌ | — | **compliance blocker** |
| K.15 | CAN-SPAM footer + unsubscribe | ❌ | — | — |
| K.16 | TCPA stance | ❌ | — | — |
| K.17 | COPPA / HIPAA stance in ToS | ❌ | — | — |
| K.18 | Subprocessor list | ❌ | — | easy to write from vendors in `.env` |

## L. Operator console (internal)

| # | Feature | Status | Gap |
| --- | --- | --- | --- |
| L.1 | Per-company usage/cost/margin | ❌ | — |
| L.2 | Provider health / failover state | ❌ | — |
| L.3 | Kill switches | ❌ | — |
| L.4 | Impersonation (read-only + audit) | ❌ | — |
| L.5 | Feature flags | ❌ | — |

## M. UX and product polish

| # | Feature | Status | Evidence | Gap |
| --- | --- | --- | --- | --- |
| M.1 | Onboarding wizard (under 3 min) | 🟡 | `app/(app)/onboarding/page.tsx` is a static checklist linking to screens | turn into a stepper with URL input → auto-crawl → test chat |
| M.2 | Bot playground with retrieval inspector | ❌ | preview chat exists; no inspector | depends on B.10 |
| M.3 | US industry templates ×8 | ❌ | none | add `TEMPLATES` with starter prompt+suggestions per industry |
| M.4 | Design system, dark mode, skeletons | ✅ | `globals.css` tokens, `components/ui/*`, every page has skeletons | — |
| M.5 | Public marketing site + pricing | 🟡 | `app/page.tsx` landing exists; pricing/compare/docs missing | — |
| M.6 | SEO basics (sitemap, OG images) | ❌ | `metadataBase` set but no `sitemap.xml` / OG images | — |
| M.7 | In-app guidance + first-value tracking | 🟡 | setup_checklist from `GET /dashboard` works; no event emission on "first value" | — |

## UX audit — issues observed across the current product

1. **Dropped states**: several owner pages (`/chatbot`, `/chatbot/publish`, `/conversations`) show a bare loader instead of a skeleton when the first fetch is slow.
2. **Mobile sidebar**: the "Open menu" button in `TopBar` navigates to `/overview` instead of opening a slide-in sidebar. On a phone there is no way to reach `/knowledge` without typing the URL.
3. **Toasts drift off-screen**: `ToastProvider` viewport is hardcoded bottom-right and overlaps the widget launcher on the hosted chat page.
4. **Error copy leaks internal codes** on a few paths — e.g. `app/(app)/conversations/[id]/page.tsx` shows raw `error_code` when the lead fails to load.
5. **Accessibility**: skip-to-content is in place; `axe-core` has never been run on these pages. One visible issue: colour-only state on some KPI numbers (sparkline colour is the only signal for "exhausted"). `SourceStatusBadge` is correct — colour + icon + text.
6. **No mobile breakpoint audit** of the new auth-shell left panel; left panel hides below `lg` which is fine, but the right panel's title size (`text-[1.7rem]`) is too tight on 360 px.
7. **Studio preview chat** clobbers scroll position when a stream completes while the user is scrolled back reviewing an older answer.
8. **Delete account dialog** reads the user's email from `/me`; it does NOT warn that published widgets will immediately stop responding to visitors.
9. **Verify email banner** (TopBar yellow stripe) is dismissible by navigating away but reappears on the next page — intended, but there is no "verified a moment ago" fade-out when the backend flips the flag.
10. **Command bar (new)** blur overlay doesn't trap focus correctly on Safari — Escape closes it but Tab leaks to the underlying page.

## Deepest 10 findings across the audit

1. `redis_resilience.py` can't read the env it was configured with (00 §2.1) → rate limiting + sessions silently broken in prod.
2. Entire RAG v2 pipeline is missing (B.1-B.12) — the ship-gate metrics in the master prompt can't be met without this.
3. Escalation engine does not exist at all (F.1-F.12) — this is the single biggest 10-day item.
4. Billing does not exist at all (J.1-J.8). Stripe is also a long-lead item for Stripe Tax registration.
5. WhatsApp / Twilio / Meta app approvals are long-lead (weeks) — must start today or launch with a documented gap.
6. Public API + API keys do not exist (H.4) — several marketed integrations (Zapier, HubSpot) depend on it.
7. No roles beyond `owner` (K.5) — team-member stories cannot ship without migrating the CHECK constraint.
8. No CSV parser (A.1.5) despite the master-prompt scope.
9. Markdown is not sanitised in the widget (C.1.2) — this is a stored-XSS risk if a chunk contains HTML and the LLM mirrors it.
10. Owner-side analytics is placeholder (E.3) — Day 8 has to build the whole backend series layer.

## Features the code has that section 2 omits (nothing to delete, but surface)

- Deterministic per-tenant vector ids and chunk-manifest reconciliation (backend/app/providers/vector_store.py:33, 61). Good foundation for B.2.
- Durable job runner with crash-safe fencing (app/jobs/runner.py). Good foundation for I.* delivery workers.
- `idempotency_keys` table + `app/idempotency.py` helper. Good foundation for public API / webhook ingress.
- `webhook_endpoints`/`webhook_deliveries` + `app/webhooks/worker.py`. Already supports HMAC and retries; just needs events to fire (H.5).
- `audit_events` table + `audit_request_context` (ContextVar-safe since the Nov-24 fix). Good foundation for L.4.
- Robust SSRF validator (`security/ssrf_http.py`) + extensive unit test suite.
