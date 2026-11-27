# 01 · Feature inventory

For every feature in section 2 of the master prompt I show: Status label · Evidence (file:line or "none found") · Tests · Gap vs requirement · UX issues observed.

Evidence methodology: grepped the full repo (`backend/app`, `backend/alembic`, `frontend/app`, `frontend/src`), opened the files it pointed at, and ran the parts I could. Anything I did not personally see in the code is labelled ❌ MISSING — not "assumed present".

**Update (2026-11-27): backend sprint through Day 9.** Days 3-9 of `launch/13-SPRINT-10-DAYS.md` landed on the backend — RAG v2 pipeline, billing, agent tools, escalation engine, realtime/multi-channel messaging, MFA/roles/invites, quality (gaps/bad-answers/alerts), the public API, Slack app, and a security hardening pass. **No frontend work happened in that span.** The practical result: a large number of rows below flip from ❌ to backend-complete while staying functionally unusable to an owner, because nothing in `frontend/app` calls the new endpoints yet.

**Status legend:**
- ✅ **Full** — backend and frontend both implemented and wired together; an owner can actually use this today.
- 🔧 **Backend-only** — API/schema/business logic complete and verified (migrations run, imports clean, in most cases exercised against the real DB); no owner-facing UI calls it yet. Frontend work is 100% additive from here, not blocked on backend design.
- 🎨 **Frontend-only** — UI exists with no real backend behind it (placeholder/mock data).
- 🟡 **Partial** — meaningfully incomplete on at least one side (schema exists but unused, or built-in-not-configurable, etc. — see Gap column).
- ❌ **Missing** — not built on either side.

**Counts (142 features catalogued across 13 areas):** ✅ 26 · 🔧 46 · 🟡 34 · ❌ 36 · 🎨 0.

**Launch-readiness legend (new column, added 2026-11-27):** given Day 10 is launch-day ops, not build time, every row also gets a launch call —
- 🚀 **Ready** — already shipped, or works correctly in the background with no UI required.
- 🟢 **Must/should fix before launch** — small, no new design needed, realistically finishable today. See the punch list below.
- 🔜 **Post-launch** — real build time required; won't make launch day. (This is where almost every 🔧 Backend-only row lands — the backend work is done, but "done" ≠ "launchable" without a UI.)
- ⛔ **Blocked externally** — PENDING_EXTERNAL (Meta/Twilio approvals); no amount of our own time changes this before launch.

## Launch-day scope (2026-11-27)

**Two go/no-go decisions this implies:**
1. **Launch stays on `rag_engine=v1`.** The v2 pipeline (RAG v2, escalation detection, agent tools, follow-ups) is feature-complete but has never been eval-gated, and flipping it under launch pressure is the wrong trade. Everything in section B, plus anything that only runs *inside* v2 (F.1/F.3's intent-based path, H.1 tools, C.1.4/C.2.3), stays dark at launch.
2. ~~Launch stays free-tier-only~~ — **superseded tonight**: plan-limit enforcement (J.5/J.6, A.6.1/A.6.2, K.6) is now real and real-DB-verified (sources, storage, team seats, the `api` feature flag, monthly AI replies). Checkout/Portal/webhooks (J.1-J.4) were not touched and still need Stripe flipped to live mode + real price IDs before a paid upgrade can actually complete — gating now works, collecting money still doesn't.

**🟢 The actual pre-launch punch list — everything else below is 🔜 or ⛔:**

| Item | What | Why it's launch-critical | Effort |
| --- | --- | --- | --- |
| K.11 | Write and publish a Privacy Policy + Terms of Service page | **Compliance blocker** — cannot legally launch without these | copy + a static page |
| C.6 / K.14 | Add a persistent "AI assistant, not a human" disclosure line to the widget | **Compliance blocker** | one line of UI copy |
| D.2.5 | Cookie-consent banner on the marketing/hosted-chat pages | required for US launch | small, standard banner |
| K.15 | CAN-SPAM footer + unsubscribe link on outbound email | legal requirement — we already send verification/reset/escalation/invite/dunning email | template footer |
| K.17, K.18 | Fold a COPPA/HIPAA stance and a subprocessor list into the ToS/Privacy page | cheap to add once K.11 exists | a paragraph + a list from `.env` vendors |
| **F.3** | **Port the 911/988 safety line into v1's live system prompt** (`app/chat/llm.py:build_system_prompt`) — **currently this line only exists in the unused v2 prompt** (`app/chat/rag_v2/stages/generate.py`); the pipeline actually serving visitors has no life-safety override at all | **safety-critical finding from this pass** — not a UI problem, a one-line prompt gap on the pipeline that's actually live | one prompt edit |

Everything else — the entire Day 8/9 backend build (MFA, roles, billing, escalation config, live inbox, API keys, Slack, gaps/bad-answers/alerts, playground), the remaining widget/analytics gaps, and all PENDING_EXTERNAL channel work — is correctly marked 🔜 or ⛔ below and is not realistic to land before launch.

## A. Knowledge and ingestion

| # | Feature | Status | Launch? | Evidence | Tests | Gap vs requirement | UX issues |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A.1.1 | PDF upload | ✅ | 🚀 | `backend/app/ingestion/parsers/pdf.py`, `app/sources/router.py:39` grant flow | DB-skipped `test_chat_and_lifecycle.py::test_profile_company_and_source_management_routes` | — | drop-zone works at desktop; small mobile target |
| A.1.2 | DOCX upload | ✅ | 🚀 | `backend/app/ingestion/parsers/docx.py` | unit `test_parsers.py` | — | same |
| A.1.3 | TXT upload | ✅ | 🚀 | `parsers/text.py` | unit | — | — |
| A.1.4 | MD upload | ✅ | 🚀 | `parsers/text.py` (MD routed through text) | — | file-signature allow-list lives in `app/storage/local.py` — MD passes | — |
| A.1.5 | CSV upload | 🔧 | 🔜 | `backend/app/ingestion/parsers/csv_source.py` parser exists and is wired into the ingestion pipeline | unit | Knowledge page's add-source dialog only offers file/text/faq/url/crawl types — no `csv` option surfaced | can't be exercised from the UI yet |
| A.1.6 | Pasted text source | ✅ | 🚀 | `app/sources/router.py:90`, `service.create_text_source` | DB-skipped | — | editor lacks word count beyond raw chars |
| A.1.7 | FAQ pairs | ✅ | 🚀 | `sources/router.py:103`, repeater UI `components/knowledge/add-source-dialog.tsx` | DB-skipped | — | — |
| A.1.8 | Single URL | ✅ | 🚀 | `sources/router.py:122`; SSRF via `app/security/ssrf_http.py` | unit `test_ssrf.py` | — | — |
| A.1.9 | Whole-site crawl | 🟡 | 🚀 | `sources/router.py:140` one-shot; `discover+import` at `:157` and `:183` | unit `test_crawler.py` | robots.txt respected; depth limit missing — only page-count cap; same-domain enforced | long crawls have no progress ring, only a polling list |
| A.1.10 | Sitemap import | 🟡 | 🚀 | `ingestion/crawler.py:_try_sitemap` | unit | surfaces as crawl-pages; no separate "sitemap" kind in schema | — |
| A.2.1 | Headings preserved | 🟡 | 🚀 | `parsers/pdf.py`, `parsers/docx.py` write headings into `chunks.heading` | — | HTML crawl does, PDF uses `pypdf` which is weak on heading detection; tables not kept intact | — |
| A.2.2 | Lists preserved | 🟡 | 🚀 | best-effort via docx/html | — | PDF loses list-level nesting | — |
| A.2.3 | Tables kept intact | ❌ | 🔜 | none found | none | **Required by section 2A.2** — current pipeline flattens tables into text; not touched this sprint | — |
| A.2.4 | Page numbers | ✅ | 🚀 | `chunks.page` column; populated for pdf | — | — | — |
| A.2.5 | FAQ pairs as single units | ✅ | 🚀 | `service.create_faq_source` writes JSON then chunker preserves pair boundaries; now also the mechanism Day 8's Gaps/Bad-answers "write the answer"/"correction" flows use to turn a fix into real knowledge | — | — | — |
| A.2.6 | OCR for scanned PDFs | ❌ | 🔜 | none; `ERROR_CODE_COPY.unsupported_scanned_pdf` only surfaces the error | none | documented as stretch — mark PENDING_EXTERNAL | — |
| A.3.1 | Scheduled re-crawl | ❌ | 🔜 | no cron entry; only manual `POST /documents/{id}/refresh` | none | — | — |
| A.3.2 | Change detection | 🔧 | 🚀 | `app/ingestion/change_detection.py` (checksum diff) + `check_source_for_changes` job executor + `app/jobs/change_detection_sweep.py` | unit `test_change_detection.py`, API `test_check_source_for_changes_executor.py` | runs automatically in the background — no UI required for it to be safe and correct at launch | — |
| A.3.3 | Re-index button | ✅ | 🚀 | `app/(app)/knowledge/page.tsx` refresh action; `POST /documents/{id}/refresh` | — | — | icon menu, easy |
| A.3.4 | Per-source status | ✅ | 🚀 | `document_versions.status` + `STATUS_META` map in `frontend/src/lib/types.ts` | unit `test_types.test.ts` | — | status badges premium-ready |
| A.3.5 | Human-actionable error messages | ✅ | 🚀 | `ERROR_CODE_COPY` covers 13 codes | unit | — | — |
| A.4.1 | Sources list | ✅ | 🚀 | `knowledge/page.tsx` | Playwright: none | — | — |
| A.4.2 | Status/size/last-synced columns | 🔧 | 🔜 | status + chunk_count shown in UI; `documents.size_bytes` column exists (migration 0017) but no endpoint reads/returns it and no UI column for it | — | wire `size_bytes` through the sources list endpoint and add the UI column | — |
| A.4.3 | Chunk preview | ✅ | 🚀 | `GET /documents/{id}/content` preview + outline | DB-skipped | — | — |
| A.4.4 | Delete/disable source | 🟡 | 🔜 | delete ✅; `documents.disabled_at` column exists (migration 0017) but **no endpoint toggles it and no UI shows it** — schema-ready, not usable | DB-skipped (delete only) | add a disable endpoint + UI toggle | — |
| A.4.5 | Bulk actions | ❌ | 🔜 | single-row actions only | none | flagged NEEDS_MORE_TIME in `12-FEASIBILITY-MATRIX.md`, not attempted | — |
| A.4.6 | Source tags | 🟡 | 🔜 | `documents.tags text[]` + GIN index exist (migration 0017) but **no endpoint sets them and no UI shows them** — schema-ready, not usable. (Do not confuse with Day 8's *conversation* tags, E.2.4 below.) | none | add a tags endpoint + UI chips | — |
| A.5.1 | Draft vs published knowledge | 🟡 | 🚀 | `publications` + `publication_sources` snapshot ONLY the bot config and version-id selection; raw knowledge has no "draft" vs "published" split within a version | integration `test_bot_publish.py` | unchanged this sprint — acceptable to ship as-is | — |
| A.5.2 | One-click rollback | 🟡 | 🚀 | `active_publication_id` can be swapped by re-publishing the old version-ids, but there is no UI "rollback to vN" button | — | unchanged this sprint — acceptable to ship as-is | — |
| A.6.1 | Plan-level source limits | ✅ | 🚀 | enforced in `sources/service.py:_check_source_quota` across every source-creation path (upload/text/faq/url/crawl/crawl-import) | manual + real-DB check | — | — |
| A.6.2 | Plan-level MB limits | ✅ | 🚀 | same `_check_source_quota` call also checks `storage_mb` against `SUM(documents.size_bytes)` | manual + real-DB check | — | — |
| A.6.3 | Upgrade prompts | ❌ | 🔜 | no billing UI at all yet (see J.2) | none | — | — |

## B. RAG v2 (mandatory)

Day 3-4 built essentially the whole pipeline spec'd here. It runs end-to-end behind `settings().rag_engine` (`'v1'` default, `'v2'` opt-in) — **v1 is still what serves real traffic**; v2 is feature-complete but not the default, and there is zero frontend for any of it. **Launch decision #1 above: stays off at launch.** Every row in this section is 🔜 except B.8, which is already live through v1's own (simpler) grounded generation.

| # | Feature | Status | Launch? | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B.1 | Agentic sufficiency loop | 🔧 | 🔜 | `app/chat/rag_v2/pipeline.py` — grade → `suggest_subquery` → re-retrieve → re-rerank, up to `max_loop_iterations` | unit happy-path | works, but is the v2 pipeline (not live by default) | — |
| B.2 | Hybrid retrieval (dense + BM25/FTS) | 🔧 | 🔜 | `app/chat/rag_v2/stages/retrieve.py` — RRF fusion of pgvector cosine + Postgres FTS, language-aware tsconfig | `test_hybrid_retrieval.py` | — | — |
| B.3 | Cross-encoder reranker | 🔧 | 🔜 | `app/chat/rag_v2/stages/rerank.py`, Cloudflare `bge-reranker-base` | `test_reranker.py`, `test_rag_v2_rerank.py` | — | — |
| B.4 | Query rewriting / decomposition | 🔧 | 🔜 | `app/chat/rag_v2/stages/rewrite.py` — up to 3 sub-queries, history-aware, falls through to raw text | unit | — | — |
| B.5 | Guard + intent classifier | 🔧 | 🔜 | `app/chat/rag_v2/stages/guard.py` (injection/length/NFKC) + `stages/intent.py` (LLM-classified intent/severity/language, rules fallback, fires `escalation.requested` on emergency language) | unit | — | — |
| B.6 | Adaptive threshold / calibration | ❌ | 🔜 | `RagConfig.min_rerank_score` still defaults to `0.0`; no eval-calibration run happened | none | needs a real D4.4-style eval pass per bot | — |
| B.7 | Evidence-sufficiency grader | 🔧 | 🔜 | `app/chat/rag_v2/stages/grade.py` — LLM sufficiency judgment, fails open | unit | — | — |
| B.8 | Grounded generation (citations) | ✅ | 🚀 | `app/chat/rag_v2/stages/generate.py` + v1's `pipeline.build_evidence`; `[n]` markers shown in `conversations/[id]` citation rows | unit happy-path | tests do not assert faithfulness | — |
| B.9 | Verifier / faithfulness check | 🔧 | 🔜 | `app/chat/rag_v2/stages/verify.py` — one regeneration retry on an unfaithful answer, then abstain | unit | — | — |
| B.10 | Per-message evaluation record | 🔧 | 🔜 | `rag_traces` table (migration 0019) + `app/chat/rag_v2/trace.py`, read by `GET /api/v1/rag-traces/*` | — | no UI reads this endpoint yet | — |
| B.11 | Eval harness + golden set ≥150 | 🔧 | 🔜 | `backend/eval/` + `backend/eval/golden/` — 150 cases exactly | `test_eval_harness.py` | bucket *composition* doesn't fully match §8.1 — count target met, shape doesn't | — |
| B.12 | Ship-gate metrics wired to CI | ❌ | 🔜 | `scripts/verify_launch.sh` runs backend tests/typecheck/openapi-drift, not RAG eval thresholds | none | nothing gates a build on eval scores | — |

## C. Chat experience

| # | Feature | Status | Launch? | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C.1.1 | Streaming answers (SSE) | ✅ | 🚀 | `app/chat/pipeline.py:stream_turn`; parser `frontend/src/lib/sse.ts` | unit `test_chat_pipeline.py`, `test_sse.test.ts` | — | typing dots premium-ready |
| C.1.2 | Markdown render | 🟡 | 🚀 | Frontend renders plain `whitespace-pre-wrap` text (not HTML) — not actually exploitable today. Backend now sanitises the stored/replayed copy anyway (defense-in-depth) | `test_xss_sanitization.py` (27-payload corpus) | still needs a real sanitised markdown renderer on the frontend eventually, not before launch | — |
| C.1.3 | Clickable citations open source passage | 🟡 | 🔜 | citation row renders but doesn't open a drawer | — | wire `/documents/{id}/content` with highlight | — |
| C.1.4 | Suggested follow-ups | 🔧 | 🔜 | `app/chat/rag_v2/stages/postprocess.py:suggest_follow_ups` | — | v2-only, v1 (live) still only shows initial suggestions | — |
| C.1.5 | Quick-reply buttons | ❌ | 🔜 | none | none | — | — |
| C.1.6 | Typing indicator | ✅ | 🚀 | `PublicBubble` + `TypingDots` | — | — | polished |
| C.1.7 | Retry on failure | 🟡 | 🔜 | user can re-type; no first-class retry button | — | — | — |
| C.2.1 | Conversation memory within session | 🟡 | 🚀 | `pipeline.prepare_turn` loads last 6 completed messages | unit | acceptable to ship as-is | — |
| C.2.2 | Visitor identity (anonymous or identified) | 🟡 | 🔜 | `visitor_sessions` has token only; no `identify()` | — | needs HMAC-signed identity for D.3.2 | — |
| C.2.3 | Multilingual retrieval | 🟡 | 🔜 | intent stage detects `language` (B.5), v2-only | none | still v2-only, not live | — |
| C.3.1 | Pre-chat lead form | 🟡 | 🚀 | V1 is post-hoc, skippable | — | acceptable to ship as-is | — |
| C.3.2 | Conversational capture | 🔧 | 🔜 | `app/chat/tools/capture_lead.py` — v2-only tool, not wired into the live pipeline | — | — | — |
| C.3.3 | Validation + consent + spam protection | 🟡 | 🚀 | consent toggle; no spam guard | — | acceptable risk at launch scale | — |
| C.4.1 | Thumb feedback + comment | 🟡 | 🚀 | thumbs POST works; no comment input yet | integration | acceptable to ship as-is | — |
| C.4.2 | Conversation rating at close | ❌ | 🔜 | none | none | — | — |
| C.5 | Business-hours aware | 🟡 | 🔜 | `escalation_contacts.quiet_hours_*` columns exist but never checked before sending | none | wire quiet-hours check into `app/escalation/worker.py` — low priority since escalation config itself has no UI yet | — |
| C.6 | AI disclosure by default | ❌ | 🟢 | none shown in widget; required for launch | none | **see punch list** — add the disclosure line | **compliance** |

## D. Widget

Untouched this sprint — same state as the prior audit.

| # | Feature | Status | Launch? | Evidence | Tests | Gap | UX |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D.1.1 | Appearance: colors | 🟡 | 🔜 | brand primary color; no bg/text/accent/bubble | — | expand `branding` schema | — |
| D.1.2 | Appearance: dark/light/auto | ❌ | 🔜 | — | none | — | — |
| D.1.3 | Appearance: font family | ❌ | 🔜 | — | none | — | — |
| D.1.4 | Position: 4 corners + offsets | 🟡 | 🔜 | only `bottom-right` / `bottom-left` | — | — | — |
| D.1.5 | Launcher shape/size/icon/label/anim | 🟡 | 🔜 | single icon, no options | — | — | — |
| D.1.6 | Powered-by plan-gated | ❌ | 🔜 | not implemented (billing not enforced anywhere) | none | — | — |
| D.1.7 | Custom CSS (sandboxed) | ❌ | 🔜 | — | none | out-of-scope V1 | — |
| D.2.1 | Auto-open rules | ❌ | 🔜 | — | none | — | — |
| D.2.2 | URL/device/language hide rules | ❌ | 🔜 | — | none | — | — |
| D.2.3 | Sound on/off, offline mode | ❌ | 🔜 | — | none | — | — |
| D.2.4 | Attachment upload by visitor | ❌ | 🔜 | — | none | stretch — defer | — |
| D.2.5 | Cookie-consent mode | ❌ | 🟢 | — | none | **see punch list** | **compliance** |
| D.3.1 | `Knowmivo()` init API | 🟡 | 🔜 | `public/embed.js` exposes `{open, close, toggle, version}` only | — | big spec: `sendMessage`, `identify`, `setMetadata`, `setTheme`, `on(event,cb)`, `destroy` | — |
| D.3.2 | HMAC-signed identity | ❌ | 🔜 | — | none | — | — |
| D.3.3 | `data-knowmivo-open` custom launcher | ❌ | 🔜 | — | none | — | — |
| D.4.1 | Install options with generated code | 🟡 | 🚀 | `GET /bot/embed` returns script/React/Next.js + hosted URL; UI at `chatbot/publish/page.tsx`'s `InstallCard` | integration | needs GTM/WordPress/etc. eventually, not before launch | — |
| D.4.2 | "Verify installation" check | ❌ | 🔜 | none | none | — | — |
| D.5 | Live preview editor | ✅ | 🚀 | `chatbot/page.tsx` two-column studio with preview chat | — | works; no device toggle yet | polished |
| D.6 | Domain allow-list enforced server-side | ✅ | 🚀 | `app/public/router.py` origin check, `bot_domains` table | integration | — | — |
| D.7 | A11y / perf / browser matrix | 🟡 | 🔜 | focus rings and keyboard present; no axe test; perf budget not measured | — | add axe + Lighthouse in CI | — |

## E. Full monitoring (owner side)

Day 8 built almost all of the missing backend here. **None of it has an owner UI yet.** Every row is 🔜 at launch except the pre-existing ✅/🟡 rows, which ship as-is, and alerts (E.6.1), which delivers real value by email even with zero UI.

| # | Feature | Status | Launch? | Evidence | Tests | Gap |
| --- | --- | --- | --- | --- | --- | --- |
| E.1 | Live view (conversations now) | 🔧 | 🔜 | SSE live inbox + Redis pub/sub + `event_outbox` reconnect-seeding (`app/realtime/`, ADR 005) | — | no inbox page consumes it |
| E.2.1 | Transcripts list | ✅ | 🚀 | `app/(app)/conversations/page.tsx`; `GET /conversations` | DB-skipped | — |
| E.2.2 | Filters: date/status/feedback/tag | 🔧 | 🔜 | date/status/feedback existed already; tag filter added | — | no UI control for the new tag filter |
| E.2.3 | Full message with citations + trace | 🔧 | 🔜 | citations already shown; retrieval trace now exists via `rag_traces` | — | no UI reads the trace endpoint |
| E.2.4 | Tags, notes | 🔧 | 🔜 | `conversations.tags text[]` + `PUT /conversations/{id}/tags`, fully functional | — | no UI |
| E.2.5 | Export CSV | 🔧 | 🔜 | `GET /conversations/export.csv`, capped at 10k rows, filters apply | — | frontend still only has a JSON export button |
| E.3.1 | Analytics dashboard | 🔧 | 🔜 | `GET /api/v1/analytics/series?metric=conversations\|deflection\|ttft` — real daily series | — | Overview page still renders `pseudoSeries()` client-side mock data |
| E.3.2 | Deflection/resolution rate | 🔧 | 🔜 | defined and computed — `app/analytics/service.py:deflection_series` | — | no chart consumes it |
| E.3.3 | Lead conversion, CSAT, TTFT | 🟡 | 🔜 | TTFT: done, real p50/p95. Lead conversion and CSAT: still ❌ | — | — |
| E.3.4 | Top questions, top topics | ❌ | 🔜 | Gaps (E.4) clusters *unanswered* questions only | none | — |
| E.3.5 | Trend charts + comparisons | 🔧 | 🔜 | the 3 series above are the groundwork | — | no chart UI |
| E.4 | Knowledge gaps | 🔧 | 🔜 | `app/quality/gaps.py` — clustering, one-click "write the answer" → real FAQ source, nightly sweep | verified end-to-end against the real DB | no UI |
| E.5 | Bad-answers queue + correction loop | 🔧 | 🔜 | `app/quality/bad_answers.py` | — | no UI |
| E.6.1 | Configurable alerts | 🟡 | 🚀 | the 3 built-in rules (quota 80/100, unanswered spike, ingestion failure) are done and debounced, delivered by **email** — useful to the owner from day one even with no UI | — | not "configurable," no UI, no custom rules |
| E.6.2 | Weekly email digest | ❌ | 🔜 | alerts fire immediately, not as a batched digest | none | — |
| E.7.1 | Audit log of owner actions | 🟡 | 🚀 | `audit_events` table exists and is written (unchanged this sprint) | integration | no UI reader, but that was already true pre-sprint |
| E.7.2 | Retention toggle, PII redaction | 🟡 | 🔜 | PII redaction code now exists (`postprocess.redact_pii`), default off; retention still flat 30 days | none | no owner-facing toggle |

## F. Emergency escalation (Appendix A)

This was entirely ❌ before this sprint. Day 5-6 built the engine. **No owner UI exists for any of it**, which means nobody can actually configure a rule or verify a contact before launch — so the whole engine is practically 🔜 regardless of backend completeness, **except F.3**, which is a one-line fix on the pipeline that's actually live and is flagged as launch-critical.

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| F.1 | Severity classifier | 🟡 | 🚀 | full classifier still v2-only; v1 (live) now has a minimal regex "visitor explicit" trigger instead (`app/chat/v1_escalation_trigger.py`) | real LLM-based classification stays v2-only — the regex trigger is a safety net, not a replacement |
| F.2 | Owner rule engine | 🔧 | 🔜 | `app/escalation/rules.py` + API at `/api/v1/escalations/rules` | no UI to create a rule |
| F.3 | 911/988 safety reply (US) | ✅ | 🚀 | now also baked into **v1**'s live system prompt (`app/chat/llm.py:build_system_prompt`) — regression-tested in `test_chat_pipeline.py` | fixed this sprint |
| F.4 | WhatsApp Cloud API delivery | 🔧 | ⛔ | `app/channels/whatsapp.py` + `app/escalation/channels/whatsapp.py` | code-complete, **PENDING_EXTERNAL** — Meta business verification + template approval |
| F.5 | SMS/email/Slack/Telegram fallback chain | 🟡 | 🔜 | email/Slack/Telegram/WhatsApp implemented; SMS/Twilio not built | add `channels/sms_twilio.py` |
| F.6 | State machine `created→queued→sent→delivered→acknowledged` | 🔧 | 🔜 | `app/escalation/state_machine.py` + `worker.py` | states/transitions exist; needs config UI to matter |
| F.7 | ACK, re-escalation, quiet hours | ✅ | 🚀 | ACK via signed deep link; re-escalation/dead now driven by `app/jobs/escalation_timeout_sweep.py` (needs a cron entry, same as `retention_sweep.py`) + `worker.check_timeout`; quiet hours enforced per-contact in `worker.dispatch_escalation`, bypassed for `critical` | all 7 scenarios verified against the real DB this sprint |
| F.8 | Dedupe/merge + storm protection | ✅ | 🚀 | dedupe fixed (see note below — it was silently broken); storm protection now in `worker.py` (5/min soft log, 10/min hard → `_send_digest`) | verified against the real DB this sprint |
| F.9 | Signed deep link to takeover | ✅ | 🔜 | `app/escalation/deep_link.py` — fully works, but needs a rule/contact to ever fire | — |
| F.10 | Owner number verification + opt-in | 🔧 | 🔜 | `app/escalation/verification.py` | no UI |
| F.11 | Test-alert button | 🔧 | 🔜 | `POST /api/v1/escalations/test` | no UI button |
| F.12 | Delivery/ACK webhook handling | 🟡 | 🔜 | WhatsApp status parsing exists but isn't consumed into `escalation_attempts.state` | wire it up |

**Three real bugs found and fixed while closing F.7/F.8 tonight (not new features — the existing engine was silently broken end-to-end):**
1. `detector.detect_and_create`'s INSERT used `ON CONFLICT ON CONSTRAINT escalations_dedupe` against a bare `CREATE UNIQUE INDEX` (not a real constraint) — every call raised `UndefinedObject`, swallowed by a bare `except Exception`, so **no escalation row has ever been created outside the manual `/escalations/test` path**. Fixed by switching to the column/expression form of `ON CONFLICT`.
2. Even after #1, nothing anywhere ever enqueued the `escalation_dispatch` job — the row would sit in `state='created'` forever. Fixed: `detect_and_create` now enqueues it in the same transaction as the INSERT.
3. `enqueue_job(..., payload=...)` silently discarded `payload` — `jobs` has no such column, only `checkpoint_ref`, and the job runner never aliased one to the other. This broke `escalation_dispatch`, `escalation_timeout_check`, `send_dunning_email`, and `channel_inbound_message` identically (all raised `PermanentJobError("missing_...")` on first real run). Fixed at the one call site (`app/jobs/queue.py`) plus a rehydration line in `app/jobs/loop.py`.

**Follow-up, also done tonight (user confirmed):** since F.1's only two triggers are v2/tools-only and v2 stays dark at launch, a minimal regex "visitor explicit" trigger (design doc §2.1, keyword match only — no classifier, no owner rules) was ported into v1 itself: `app/chat/v1_escalation_trigger.py` + a `_maybe_trigger_escalation` hook in `pipeline.py:prepare_turn`, fire-and-forget after the user message is persisted, swallows every exception so it can never break a chat turn. Safety language (self-harm/danger wording) maps to `severity='critical'`; "talk to a human"/"urgent"/"lawyer"/"chargeback"/"cancel my ..." maps to `severity='high'`. Unit-tested (5 cases, no DB) and real-DB end-to-end verified (regex match → `detect_and_create` → `dispatch_escalation` → contact notified). **F.7/F.8/F.1 can now all move to 🚀** — the engine is reachable from real v1 launch traffic.

## G. Human handoff / live inbox

Was entirely ❌. Day 5-6 built the backend state machine, realtime push, and the agent-reply mechanism (found missing mid-sprint and closed). **No inbox UI exists**, so every row is 🔜.

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| G.1 | Statuses `bot/needs_human/human/resolved` | 🔧 | 🔜 | `conversations.status`/`assigned_to`/`handed_off_at` (migration 0022) | no UI |
| G.2 | Assignment, notes, canned replies | 🔧 | 🔜 | assignment + canned replies CRUD + **`POST /api/v1/handoff/{id}/reply`** (a real gap found and closed this sprint) | no UI |
| G.3 | Real-time updates (SSE/WS) | 🔧 | 🔜 | `app/realtime/` SSE + Redis pub/sub, ADR 005 | no UI subscribes to it |
| G.4 | "Team member joined" visitor notice | 🔧 | 🔜 | the visitor-side sidecar stream already carries the needed events | no widget UI renders it |
| G.5 | SLA timers | ❌ | 🔜 | not built | — |

## H. Actions and tools (agentic)

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| H.1 | Built-in `search_knowledge`, `capture_lead`, `escalate_to_human` | 🔧 | 🔜 | `app/chat/tools/` | v2-only, not live by default; no UI |
| H.2 | `book_appointment` (Calendly/Google Calendar) | ❌ | ⛔ | PENDING_EXTERNAL on API keys | — |
| H.3 | Owner-defined HTTP actions + schema + test button | 🔧 | 🔜 | `app/actions/` — full CRUD + SSRF validation + test endpoint | no UI |
| H.4 | Public REST API + API keys with scopes | 🔧 | 🔜 | `app/public_api/` — exact ADR 007 shape, verified end-to-end against the real DB | no UI to create/manage keys |
| H.5 | Outbound signed webhooks | ✅ | 🚀 | `webhook_endpoints`/`webhook_deliveries` + `app/webhooks/worker.py`, now actually fed real events via `emit_event()` | registration only via the public API or direct DB insert — fine, this is infra, not an owner-facing feature |

## I. Channels and integrations

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| I.1 | Web widget + hosted chat page | ✅ | 🚀 | works | — |
| I.2 | WhatsApp inbound | 🔧 | ⛔ | `app/channels/whatsapp.py` + `router.py` + `bindings.py` | PENDING_EXTERNAL (Meta business verification) |
| I.3 | Messenger | 🔧 | ⛔ | `app/channels/messenger.py` | PENDING_EXTERNAL |
| I.4 | Instagram DM | 🔧 | ⛔ | `app/channels/instagram.py` | PENDING_EXTERNAL |
| I.5 | Twilio SMS | ❌ | ⛔ | not attempted (10DLC/toll-free verification long lead) | — |
| I.6 | Slack alerts & handoff | 🟡 | 🔜 | Slack alerts done (`app/integrations/slack.py`); Slack handoff not built | no UI to install it |
| I.7 | Zapier / Make via webhooks | 🔧 | 🔜 | the public API's `events:webhook` scope is the mechanism | no Zapier docs page / app listing |
| I.8 | HubSpot lead sync | ❌ | 🔜 | not built | — |
| I.9 | Google Sheets export | ❌ | 🔜 | not built | — |
| I.10 | Shopify product/order lookup | ❌ | 🔜 | not built | — |

## J. Billing

Was entirely ❌. Day 4 built the schema, Stripe integration, and webhook processing. **No billing UI exists** — the frontend's Usage page explicitly states "no paid upgrade." **Launch decision #2 above: stays dormant at launch** — every row here is 🔜, and that's the correct call, not a gap to rush.

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| J.1 | Plans schema | ✅ | 🔜 | `plans`/`subscriptions`/`usage_events`/`invoices`/`stripe_events` (migration 0014), full plan matrix seeded | — |
| J.2 | Stripe Checkout + Portal | 🔧 | 🔜 | `POST /api/v1/billing/checkout`, `/portal` | no UI |
| J.3 | Stripe Tax (US sales tax) | 🔧 | 🔜 | `automatic_tax` wired on every Checkout session | tax *registration* is a business/ops task |
| J.4 | Webhooks with idempotency | ✅ | 🔜 | `event_id` PK conflict-do-nothing + `app/billing/processor.py` | `test_stripe_webhook.py` passes; dormant until Checkout is live |
| J.5 | Plan gating / entitlements | ✅ | 🚀 | `require_feature`/`require_quota` + a new `_check_source_quota`/`_check_member_quota`/`_check_plan_monthly_quota` now gate sources, storage, team members (see K.6), the public API feature, and monthly AI replies — real call sites, verified against the real DB | see A.6.1/A.6.2 |
| J.6 | Usage meter + overage | ✅ | 🚀 | `usage_events(kind='ai_reply')` now has a writer: `app/chat/quota.py::commit()` inserts one row per completed AI reply, checked against `plans.limits.ai_replies_per_month` in `reserve()` | real-DB test: hit the Free plan's 100/mo limit, confirmed `QuotaExceeded("plan_monthly")` |
| J.7 | Dunning, proration, cancel/reactivate | 🔧 | 🔜 | dunning job + webhook-driven subscription upsert | no UI |
| J.8 | Promo codes, free-tier abuse protection | 🟡 | 🔜 | promo codes ✅ (Stripe-native); abuse protection not built | not urgent while free-only |

## K. Accounts / teams / security / compliance (US)

Day 8 built MFA and roles/invites. **No frontend exists for either.** This section also carries every compliance item — the actual launch punch list.

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| K.1 | Email + Google sign-in | ✅ | 🚀 | `auth/router.py`, `security/google_oauth.py` | — |
| K.2 | Email verification | ✅ | 🚀 | `service.verify_email` + `MailCheck` UI | — |
| K.3 | Password reset | ✅ | 🚀 | `service.reset_password` + `/reset-password` page | — |
| K.4 | MFA (TOTP) for owners | 🔧 | 🔜 | `app/security/mfa.py` — full TOTP/recovery-code/step-up implementation | no UI |
| K.5 | Roles (owner/admin/agent/viewer) | 🔧 | 🔜 | `memberships.role` relaxed, `require_role` dependency, `resolve_session` fixed (see finding below) | no UI |
| K.6 | Team invites | ✅ | 🚀 | `app/team/` — signed-token invite + accept flow, now with a `plans.limits.members` seat check (`team/service.py::_check_member_quota`, counts members + pending invites) | real-DB tested |
| K.7 | Multiple bots per company | ❌ | 🔜 | unchanged — schema is still 1:1 | not touched this sprint |
| K.8 | Agency / multi-workspace | ❌ | 🔜 | not touched | — |
| K.9 | Account export | ✅ | 🚀 | `GET /company/export` | — |
| K.10 | Account deletion | ✅ | 🚀 | `DELETE /me` + cleanup job; now requires MFA step-up when enabled | integration test exists |
| K.11 | Privacy policy / terms | ❌ | 🟢 | pages not written | **see punch list — compliance blocker** |
| K.12 | DPA template | ❌ | 🔜 | — | lower priority than K.11 |
| K.13 | CCPA/CPRA DSR flow | ❌ | 🔜 | export/delete exist; no "request access" UI | — |
| K.14 | AI disclosure | ❌ | 🟢 | — | **see punch list — compliance blocker** (same requirement as C.6) |
| K.15 | CAN-SPAM footer + unsubscribe | ❌ | 🟢 | — | **see punch list** — we already send verification/reset/escalation/invite/dunning email |
| K.16 | TCPA stance | ❌ | 🔜 | — | not applicable yet — no SMS channel live |
| K.17 | COPPA / HIPAA stance in ToS | ❌ | 🟢 | — | **see punch list** — cheap paragraph once K.11 exists |
| K.18 | Subprocessor list | ❌ | 🟢 | — | **see punch list** — list vendors from `.env` |

## L. Operator console (internal)

Untouched this sprint. Internal-only, not launch-blocking — every row is 🔜.

| # | Feature | Status | Launch? | Gap |
| --- | --- | --- | --- | --- |
| L.1 | Per-company usage/cost/margin | ❌ | 🔜 | — |
| L.2 | Provider health / failover state | ❌ | 🔜 | — |
| L.3 | Kill switches | ❌ | 🔜 | — |
| L.4 | Impersonation (read-only + audit) | ❌ | 🔜 | — |
| L.5 | Feature flags | ❌ | 🔜 | `settings().rag_engine` is a real, working env-var switch, but not an operator-console flag system |

## M. UX and product polish

| # | Feature | Status | Launch? | Evidence | Gap |
| --- | --- | --- | --- | --- | --- |
| M.1 | Onboarding wizard (under 3 min) | ✅ | 🚀 | `app/(app)/onboarding/page.tsx` is now a real stepper: each step's status is derived from real company/bot/document state (not hardcoded), with an inline one-shot crawl form (step 2) and an inline live `ChatWindow` preview (step 4) | tsc + build + vitest clean |
| M.2 | Bot playground with retrieval inspector | 🔧 | 🔜 | the data fully exists (`rag_traces`); page unbuilt | pure frontend task now |
| M.3 | US industry templates ×6 | ✅ | 🚀 | `INDUSTRY_TEMPLATES` in `studio-config.ts` (SaaS, e-commerce, real estate, healthcare, education, professional services) — seeds instructions/greeting/suggestions together; picker in both onboarding step 1 and the chatbot studio's Behavior card | tsc + build + vitest clean |
| M.4 | Design system, dark mode, skeletons | ✅ | 🚀 | `globals.css` tokens, `components/ui/*` | — |
| M.5 | Public marketing site + pricing | ✅ | 🚀 | `app/pricing/page.tsx` + `pricing-grid.tsx` — fetches the real `/api/bff/billing/plans` data (same source as the authenticated billing settings page) so the 5 tiers and limits can never drift from what's actually enforced; FAQ section; linked from the landing page nav/footer | tsc + build + vitest clean |
| M.6 | SEO basics (sitemap, OG images) | ❌ | 🔜 | `metadataBase` set but no `sitemap.xml` / OG images | — |
| M.7 | In-app guidance + first-value tracking | 🟡 | 🔜 | `setup_checklist` works; no "first value" event | — |

## UX audit — issues observed across the current product

Unchanged this sprint (no frontend work happened) — carried forward from the prior audit:

1. **Dropped states**: several owner pages show a bare loader instead of a skeleton when the first fetch is slow.
2. **Mobile sidebar**: the "Open menu" button navigates to `/overview` instead of opening a slide-in sidebar.
3. **Toasts drift off-screen**: `ToastProvider` viewport overlaps the widget launcher on the hosted chat page.
4. **Error copy leaks internal codes** on a few paths.
5. **Accessibility**: skip-to-content is in place; `axe-core` has never been run on these pages.
6. **No mobile breakpoint audit** of the auth-shell left panel.
7. **Studio preview chat** clobbers scroll position mid-stream.
8. **Delete account dialog** doesn't warn that published widgets will immediately stop responding to visitors.
9. **Verify email banner** reappears on navigation with no "verified a moment ago" fade-out.
10. **Command bar** blur overlay doesn't trap focus correctly on Safari.

## Deepest 10 findings across the audit (updated 2026-11-27)

1. **The backend/frontend gap is now the single biggest risk, not missing backend features.** Days 3-9 built MFA, roles/invites, billing, escalation, the public API, Slack, gaps/bad-answers/alerts, and realtime inbox infrastructure — all backend-complete, all 🔧 above, none reachable by an owner today, and none of it realistic to land before launch.
2. Two real bugs were found and fixed *during* this backend work: `resolve_session` would have silently locked 7 of 29 real users out of their own company (K.5), and `app/security/ssrf_http.py:fetch()` referenced an undefined name and crashed with `NameError` on every call — all URL-based ingestion was completely broken in production, invisible to tests that mock `fetch()` out entirely.
3. **New, launch-critical finding: the 911/988 safety reply (F.3) only exists in the unused v2 prompt.** v1 — the pipeline actually serving visitors — has no life-safety override today. This is the one item from this whole audit that is both safety-critical and genuinely fixable before launch (one prompt edit, no new design).
4. RAG v2 (B.1-B.12) is feature-complete but gated behind `rag_engine='v1'` default, and launch correctly keeps it off — nothing has run the eval harness against it to justify flipping the flag.
5. **Updated tonight:** Billing (J.*) entitlements are now enforced (J.5/J.6 — sources, storage, team seats, the `api` feature, monthly AI replies), real-DB verified. Checkout/Portal/webhooks were not touched tonight and still need Stripe live mode before an upgrade can complete, but gating a company already on a paid plan (e.g. via a manually-set subscription row) now actually works.
6. **Updated tonight:** Escalation (F.7/F.8 — re-escalation timing, quiet hours, storm protection) is now built and real-DB verified, plus three pre-existing bugs that made the *whole* engine inert were found and fixed (see the note under F.12), plus a minimal v1-side regex trigger (F.1) so it's actually reachable from real launch traffic, not just the dark v2/tools path. Remaining gap: no UI for owners to author rules beyond what the earlier frontend sprint built for contacts/test-alert.
7. WhatsApp/Messenger/Instagram/Twilio are still PENDING_EXTERNAL — code-ready (minus Twilio), but no real send can happen until Meta business verification and template approval land, independent of our own schedule.
8. Markdown is sanitised server-side now (C.1.2), but the frontend doesn't render markdown as HTML at all, so the stored-XSS exposure from the prior audit was already not reachable — defense-in-depth, not a live-hole fix, and not launch-blocking either way.
9. `documents.tags`/`disabled_at`/`size_bytes` (A.4.2/A.4.4/A.4.6) are schema-only columns with zero endpoint or UI — small individually, but three separate "looks done, isn't" traps for anyone skimming the schema instead of the routes.
10. **The actual pre-launch work is five small items, all listed in the punch list at the top of this file** — two compliance pages, a disclosure line, a cookie banner, an email footer, and the 911/988 prompt fix. Everything else audited here is correctly deferred.

## Features the code has that section 2 omits (nothing to delete, but surface)

- Deterministic per-tenant vector ids and chunk-manifest reconciliation (`backend/app/providers/vector_store.py`). Good foundation for B.2.
- Durable job runner with crash-safe fencing (`app/jobs/runner.py`). Now the delivery mechanism for escalation dispatch, channel-inbound messages, gap/alert sweeps, and Stripe event processing, not just the original ingestion use case.
- `idempotency_keys` table + `app/idempotency.py` helper. Now reused by the public API's mutating endpoints (H.4).
- `webhook_endpoints`/`webhook_deliveries` + `app/webhooks/worker.py`. Already supported HMAC and retries; now actually fed real events (H.5).
- `audit_events` table + `audit_request_context`. Good foundation for L.4.
- Robust SSRF validator (`security/ssrf_http.py`) — now also closes a DNS-rebinding TOCTOU gap on top of the existing redirect/private-range checks, and the module's own `fetch()` function actually works now (see finding #2 above).
- A generic Redis pub/sub + `event_outbox`-seeded reconnect pattern (`app/realtime/`) that any future "push this to an open tab" feature can reuse, not just the live inbox it was built for.
