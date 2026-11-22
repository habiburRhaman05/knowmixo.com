# Existing backend gap map

Assessment is based on the supplied ATLAS source. Existing files are preserved in `backend/`. This document lists implementation work, not completed fixes.

| Existing location | Reuse | Required change |
| --- | --- | --- |
| app/main.py | FastAPI routing, document/chat concepts, health routes | Split auth/company/source/bot/public routes, real principal dependency, asynchronous completion, SSE, consistent errors and lifecycle endpoints |
| app/demo_context.py | Principal shape only | Remove fixed demo operator/admin principal from production. Resolve real sessions and company membership |
| app/config.py | Pydantic configuration | Add provider selection/free-only validation, Cloudflare/OpenRouter/local storage, auth/email/quotas. Fail startup on unsafe production defaults |
| app/aws.py | Provider interface concepts | Introduce embedding/chat/storage protocols. Cloudflare embeddings and free OpenRouter streaming become defaults. Disable AWS paid model path in free deployment |
| app/vector.py | Pinecone client, namespace and upsert approach | Validate model/dimensions, source version metadata, published scope, readiness, reliable cleanup and tenant authorization. Do not silently recreate mismatched indexes |
| app/graph.py | LangGraph orchestration skeleton | Typed scope and publication state, evidence validation, streaming output. Replace unconditional last-question concatenation with controlled history handling |
| worker/ingest.py | PDF/DOCX parsers and stable vector ID idea | Token-aware structure-preserving chunks, DOCX tables, checkpoints, durable jobs, lease/retries, quota waiting, partial-index safety and deletion fencing |
| app/db.py | Parameterized SQL | Managed connection pool, transactions, migrations, budget reservation, tenant-safe repository methods |
| app/memory.py | Message persistence | Conversation ownership and bot scope, pending/streaming/interrupted states, generation IDs and bounded history |
| infra/schema.sql | Existing source/chat/audit tables | Add canonical auth/company/bot/version/job/publication model through migrations, migrate old tenant IDs deliberately |
| app/static and templates | Reference behavior | Keep as legacy demo. New owner UI and widget live in frontend, not a second production dashboard |
| app/observability.py | Optional logging hooks | Structured redacted logs by default. Optional Rius integration must not be required or paid by default |
| approvals/guardrails routes | Audit concepts | V1 chatbot stays read-only. Do not present approval records as actual executed admin actions |
| requirements.txt | Working Python base | Add tested auth/migrations/tests/upload dependencies, pin versions, remove unused AWS/Rius dependencies after migration |
| test.py and test/bedrock_test.py | Historical smoke checks | Add real isolated tests. Existing Bedrock tests make external calls and must not run in default free CI |
| Dockerfile | Python container and non-root user | Add worker startup command, writable private storage mount, healthcheck and separate process definitions |
| backend/.github/workflows/cicd.yaml | Archived deployment reference | It is no longer an active root workflow in this reorganized copy. Replace AWS/ECR/Rius assumptions with tested root CI before enabling deployment |

## Priority failures

Current demo identity grants admin privileges and is not production authentication. Upload completion processes synchronously. A worker crash can leave processing stuck. Partial vectors can become searchable before successful completion. Conversation lookup is insufficiently actor-scoped. Model calls are AWS dependent. There is no complete public bot publishing, visitor authorization, account lifecycle or streaming system. These block a real public SaaS release.

## Preservation and relocation

All original non-doc files were copied unchanged into backend, including LICENSE, README, environment example and old workflow. Original docs are under docs/legacy. There was no source rewrite during this planning task. Existing Python imports continue to assume backend is the working directory. Run commands from backend. Docker build context is backend.

Because Downloads write access is unavailable, this reorganized working copy is a sibling artifact in the writable workspace. Once reviewed, replace or move the original project manually, or open this new project as the development root. Do not overwrite local environment files or credentials when merging.
