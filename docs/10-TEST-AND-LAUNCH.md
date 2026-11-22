# Testing and release gates

## Test layers

Unit tests cover authorization helpers, token consumption, chunk boundaries, source version selection, job state transitions, retry classification, budgets and URL validation. API tests use isolated PostgreSQL fixtures and provider fakes. Integration tests target real Redis/Pinecone and provider APIs only when explicitly enabled with a small hard budget. Browser tests exercise owner and visitor journeys on staging. Never use paid Bedrock tests by default.

## Required scenarios

- Owner A cannot read, change, delete, preview, retry or chat with Owner B's records by substituting IDs.
- Visitor cannot retrieve other visitor history or use owner preview tokens. Unpublished bots deny requests.
- Signup/login/Google, verify/resend, expired and replayed tokens, reset/change password, email change and logout-all work end to end.
- PDF/DOCX/TXT/MD, pasted text, FAQ and URL/crawl each ingest. Empty/scanned/malformed/oversized inputs fail clearly.
- Worker crashes during extract, embedding and partial upsert recover without duplicate publication. Stale workers cannot finalize newer source versions.
- Redis outage preserves jobs. PostgreSQL failure does not falsely acknowledge committed state. Provider timeout retries. Provider quota pauses. Maximum retry enters dead state. Manual replay is safe.
- Publication selects ready immutable versions. Replacement, deletion and unpublish never leak stale cached content. Physical cleanup is eventually verified.
- SSRF cases cover internal IPv4/IPv6, cloud metadata, credentials in URLs, redirect chains and changing DNS answers.
- SSE handles Unicode, partial frames, provider errors, browser abort, proxy timeout and disconnected clients. Aborted generation is not charged twice by app retries or marked complete.
- HTML/React/Next.js embeds work and duplicate script insertion is harmless. CORS, iframe and postMessage policies reject unauthorized operations.
- Prompt-injection fixtures do not reveal other tenants, secrets or owner data. Absence of evidence returns fallback. Citation IDs correspond to actual authorized source passages.
- Quota guard prevents paid fallback and concurrent oversubscription. No provider key appears in bundled frontend, network responses or redacted logs.

## Evaluation corpus

Create at least two synthetic companies with conflicting company names and policy facts. Use at least 20 questions spanning English, Bangla, paraphrases, no-evidence questions and multi-turn references. Mark expected source passages. Record retrieval correctness, citation validity and grounded answer behavior. Any cross-company leak is a blocker regardless of aggregate score. Fix false semantic cache hits or keep semantic caching disabled for launch.

## Release checklist

All critical acceptance criteria pass. No unresolved authorization, destructive-data-loss or secret-exposure issue remains. Fresh database migration and upgrade migration both pass. Restore a real encrypted backup in staging and verify source files and manifests. All services stay within observed free plan budgets. Terms/data-processing suitability for intended documents is reviewed. Domain TLS, renewal, Google OAuth redirects and email DNS/delivery are verified. Monitoring alerts, queue visibility and quota pause UX work. Document rollback image/config/schema compatibility and assign an operator.

Launch is a capacity-limited beta without payments. Announce actual limits and availability. A production-grade design does not create a free-tier SLA.
