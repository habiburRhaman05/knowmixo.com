# Backend sprint plan — refined, phase-ordered (supersedes day-to-day ordering in 14)

This refines [14-SPRINT-PLAN.md](14-SPRINT-PLAN.md) per the owner's direction: backend fully before frontend, credentials/accounts gathered as one explicit phase before rapid development starts, and each phase strictly sequenced where a real dependency exists ("authentication, then X, then X") while calling out where two phases can run in parallel. The DB design referenced throughout is [13-DB-ENGINEERING-GAP-ANALYSIS.md](13-DB-ENGINEERING-GAP-ANALYSIS.md) + [18-DATABASE-V2-V3-SCALABLE-SCHEMA.md](18-DATABASE-V2-V3-SCALABLE-SCHEMA.md) combined. Test gates from doc 14 are unchanged and still apply per phase — this document changes **sequencing and phase boundaries**, not the testing bar.

## Phase 0 — Credentials, accounts, and environment (blocks everything else)

Nothing in Phase 1 can be tested end-to-end without real provider credentials. This phase is pure setup, not code, and must finish first. Checklist is in [20-CREDENTIALS-CHECKLIST.md](20-CREDENTIALS-CHECKLIST.md) — use that file as the literal tracking sheet.

**Deliverable:** every environment variable in the Phase 0 checklist has a real value, verified reachable (not just "account created"), recorded in a `.env` file that is never committed, with a redacted copy of *which variables exist* (not their values) committed to the deployment manifest.

**Exit gate:** a single smoke script connects to Postgres (Neon), Redis (Upstash), Pinecone, calls the Cloudflare embedding endpoint once, and calls the OpenRouter free model once — all four succeed. This is the same spike work as old Sprint 0, elevated to a hard phase boundary because the user asked for credential-gathering to be done "first together" before rapid development begins.

## Phase 1 — Authentication and identity (hard dependency for every later phase)

Nothing else can be built against real data without this — every table from Phase 2 onward has a `company_id`/`owner_user_id` foreign key that only means something once real users and sessions exist.

**Scope:** Alembic baseline; migration 0001 (`users, oauth_accounts, sessions, auth_tokens, companies, memberships`); Argon2id signup/login; email verification + resend; forgot/reset/change password; logout/logout-all; Google OAuth with independent ID-token validation; delete `app/demo_context.py` from every reachable route.

**Test gate:** per 14-SPRINT-PLAN.md Sprint 1 gate (auth unit tests, isolated-DB API tests, session revocation, Google token forgery rejection). Additionally: grep confirms zero production imports of `demo_context`.

**Exit condition to move to Phase 2:** a real user can sign up, verify, log in, and get a company row created — with every unauthenticated/cross-user request provably rejected.

## Phase 2 — Company/tenancy hardening + job infrastructure (can start once Phase 1's schema exists, does not need Phase 1's auth *endpoints* finished)

This is the one place two workstreams can run **in parallel** rather than strictly sequentially, if you have two engineers: (a) finishing auth endpoint polish, (b) building the durable job runner skeleton against the `jobs`/`job_attempts` tables, since the job runner's claim/lease/retry logic has no dependency on auth being done — it only needs the `companies` table to exist for scoping, which Phase 1's migration already created.

**Scope:** migration 0002 (`bots, documents, document_versions, chunks, jobs, job_attempts`); the Python job runner (claim/lease/heartbeat/attempt-fencing, `main`/`retry`/`dead` queues, backoff schedule, `quota_wait` state) built and tested against synthetic no-op jobs *before* real ingestion logic is wired in — prove the runner is crash-safe with a trivial job first, then attach real work.

**Test gate:** job runner crash-recovery suite (kill worker mid-lease, confirm fencing) passing against synthetic jobs, independent of any parser code.

**Exit condition:** the job runner survives a kill-and-restart cycle with zero duplicate completions on a fake job, before a single real document has ever been parsed.

## Phase 3 — Knowledge ingestion (depends on Phase 2's job runner being proven)

**Scope:** local storage upload adapter (replacing boto3/S3); PDF/DOCX/HTML/TXT parsers; tokenizer-aware chunker; Cloudflare embeddings adapter with dimension validation; Pinecone upsert with deterministic IDs and chunk-manifest reconciliation; text/FAQ/URL-paste sources; SSRF-hardened URL client; crawl discovery + bounded same-domain crawl.

**Test gate:** per 14-SPRINT-PLAN.md Sprint 2 gate (format fixtures, SSRF fixture suite, quota-simulation, crash-mid-embed recovery using the *real* parser this time, not the synthetic job from Phase 2).

**Exit condition:** a real PDF upload reaches `ready` status only when the Postgres chunk manifest count matches Pinecone's upserted vector count.

## Phase 4 — Bot configuration, publication, tenant isolation proof (depends on Phase 3 — needs ready source versions to select from)

**Scope:** migration 0003 (`publications, publication_sources, bot_links`); draft config with optimistic revision control; publish/unpublish with immutable snapshot semantics; source management (refresh/replace/delete with immediate revocation).

**Test gate:** per 14-SPRINT-PLAN.md Sprint 3 gate — this phase's tenant isolation suite is gate-blocking and must be **re-run at the end of every subsequent phase**, not just once here.

**Exit condition:** publishing creates a snapshot a later draft edit cannot mutate; the full cross-owner ID-substitution suite returns 403/404 everywhere, with zero exceptions.

## Phase 5 — Lead capture (V1 shape, V2-ready schema) — can run in parallel with Phase 4

Because the V2-aware schema in doc 18 makes `lead_forms`/`lead_form_fields`/`lead_submissions` a self-contained feature with only a `bot_id` and later `conversation_id` dependency, this can be built alongside Phase 4 rather than strictly after it, if resourcing allows. If working solo/sequentially, it slots in right after Phase 4.

**Scope:** migration 0004's lead tables (brought forward from the original Sprint 4 migration since they have no dependency on chat/messages being built yet — only on `bots` existing); default lead-form seeding on bot creation; the V1 skippable post-hoc capture endpoint. **Not in scope for V1**: `trigger='before_chat_start'` enforcement, multiple forms per bot, webhook firing on submission — the schema supports them, the V1 application code does not call them yet.

**Test gate:** a lead submission writes a `lead_submissions` row with a `values` JSONB payload matching the seeded `lead_form_fields`; skipping the form still allows chat to proceed (V1's `is_required=false` default is respected).

## Phase 6 — Visitor chat: retrieval, grounding, streaming (depends on Phase 4's publication model + Phase 2's job/provider adapters)

**Scope:** migration 0004's remaining tables (`visitor_sessions, conversations, messages, feedback, usage_reservations, usage_daily, analytics_events`); visitor bootstrap; the full query pipeline (auth → scope validation → quota check → embed → optional cache → retrieve → validate → ground → stream); SSE contract with abort/interrupt semantics; owner draft preview using the same pipeline.

Write `analytics_events` rows for message-sent/feedback-given/conversation-started here — doc 18's point that this is nearly free to add now and expensive to retrofit applies directly at this phase.

**Test gate:** per 14-SPRINT-PLAN.md Sprint 4 gate (cache-hit/miss identical authorization, SSE fault injection, prompt-injection fixtures, quota-guard call-count assertion) plus a re-run of the Phase 4 tenant isolation suite against the new chat endpoints.

**Exit condition:** a grounded, cited, streamed answer works end-to-end for both a publication and an owner draft preview, with the quota guard provably blocking paid fallback under simulated exhaustion.

## Phase 7 — Conversation history, account lifecycle, distribution surface, webhook scaffolding

**Scope:** per original Sprint 5 (history/export/delete, account deletion, domain allowlist, embed endpoints, retention sweep) **plus** migration 0005's `webhook_endpoints`/`webhook_deliveries` tables built now, reusing the Phase 2 job-runner pattern for delivery retries — still dormant (no application code fires a webhook yet), but the delivery-worker code path can be smoke-tested with a fake endpoint (e.g., a local echo server) so it's proven before V2 turns it on for real.

**Test gate:** per 14-SPRINT-PLAN.md Sprint 5 gate, plus: a manually-inserted `webhook_deliveries` row against a local test HTTP server is correctly delivered, retried on simulated failure, and marked `dead` after max attempts — proving the dormant V2 feature actually works mechanically before it has a real caller.

## Phase 8 — Backend hardening, chaos testing, full regression (backend-complete gate)

**Scope:** unchanged from 14-SPRINT-PLAN.md Sprint 6 — Redis-outage recovery, Postgres failover handling, job replay idempotency, OpenAPI contract generation, logging/secret audit, Dockerfile finalization.

**Exit condition:** this is the explicit "frontend may now start" gate. Full regression across Phases 1–7 in one CI run, all chaos scenarios green.

## Dependency chain summary (what strictly blocks what)

```
Phase 0 (credentials)
   └─▶ Phase 1 (auth/identity)
          └─▶ Phase 2 (tenancy schema + job runner, parallelizable internally)
                 └─▶ Phase 3 (ingestion)
                        └─▶ Phase 4 (bot/publish/tenant isolation)
                               ├─▶ Phase 5 (lead capture)  — parallel with Phase 4 if resourced
                               └─▶ Phase 6 (chat/retrieval)
                                      └─▶ Phase 7 (history/lifecycle/webhook scaffolding)
                                             └─▶ Phase 8 (hardening gate → frontend starts)
```

Only Phase 2's internal split and Phase 4/5 are genuinely parallelizable with extra resourcing; everything else is a strict chain because each phase's tables or proven invariants are inputs to the next phase's tests, not just its features.
