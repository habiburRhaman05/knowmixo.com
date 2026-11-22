# Ten-day backend-first build plan

Days are working days starting after plan approval and credentials are available. Every day ends with a runnable increment, test evidence and an updated issue list. Do not force launch if security or data-loss gates fail.

| Day | Focus | Deliverables and exit gate |
| --- | --- | --- |
| 1 | Backend foundation and identity | Confirm provider accounts/free limits, pin dependencies, Cloudflare embedding shape/dimension spike, free LLM streaming spike, Auth.js-to-FastAPI compatibility spike, migrations, real users/sessions/company, Google/password auth, verification/reset email. Exit only after auth isolation and email delivery tests pass. |
| 2 | Backend knowledge ingestion | Private upload grants, parsers, tokenizer chunks, text/FAQ/URL/crawl, SSRF controls, durable jobs, leases, retries/dead jobs, checkpoints, quotas and Pinecone version metadata. Verify duplicate delivery, crash recovery and failed upsert fixtures. |
| 3 | Backend chatbot and contracts | Bot draft/publish snapshot, public visitor sessions, authorized retrieval, bounded history, optional semantic cache, free LLM SSE/abort, conversations/leads/feedback/export/delete, account cleanup and API contract tests. Gate on end-to-end ingestion-to-chat and cross-tenant denial. |
| 4 | Frontend foundation/auth/company | Create Next.js app and shadcn design primitives, BFF/session bridge, all auth forms, profile/company/onboarding, dashboard and usage states. Backend remains authoritative. |
| 5 | Frontend knowledge and bot studio | Upload/import/crawl selection, processing status, extracted preview, retry/delete/replace, instructions and branding editors, draft live preview. Verify all nonhappy states. |
| 6 | Frontend distribution and history | Publish/republish/unpublish, standalone chat, iframe loader script, copy embed examples, domain settings, streaming/cancel, leads/feedback and conversations/export/delete. Test on HTML/React/Next.js host pages. |
| 7 | Integration and UX polish | Fix workflow seams, responsive/accessibility review, safe Markdown, empty/error/loading states, instruction quality and English/Bangla corpus. Audit secret exposure and ownership boundaries. |
| 8 | Reliability and deployment rehearsal | Redis/provider/database outage tests, request budgets, queue replay, deletion/version races, proxy SSE/abort tests, backup/restore rehearsal, build and migration in staging. |
| 9 | Final acceptance and capacity | Full regression, security negative tests, capped load test within free allowance, browser/mobile checks, beta signup limits, privacy/terms/retention review and operations runbook walkthrough. |
| 10 | Finalize and gated beta launch | Fix remaining launch blockers, clean seeded/demo data, verify DNS/TLS/email, production backup, controlled migrations, smoke tests and invited beta. Enable wider registration only after capacity evidence. |

## Schedule pressure

The first three days combine many backend features. If estimates slip, keep all requested features tracked and extend implementation rather than declaring them complete or weakening authentication. A reduced public beta scope requires explicit owner agreement. OCR, billing and native mobile are already out of V1 and are not hidden tasks.

## Dependency order

Identity precedes company-scoped uploads. Source versioning precedes publication. Durable jobs precede retries. Retrieval authorization precedes semantic cache. Backend streaming precedes widget streaming. Domain/email verification and free provider credentials should be prepared before day 1. Frontend code starts on day 4, with only a throwaway auth integration spike earlier if needed to validate the contract.
