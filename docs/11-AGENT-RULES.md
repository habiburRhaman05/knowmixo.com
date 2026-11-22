# Implementation rules for coding agents

Read docs/README.md, the relevant specification and the existing source before editing. Preserve Python/FastAPI as backend. Keep frontend in frontend and planning material in docs. Do not rebuild the backend in Node.

1. Treat the PRD and acceptance criteria as scope. Record unresolved choices before implementing divergent behavior.
2. Never replace real auth with a demo principal, trust client company IDs, or authorize through an LLM decision.
3. Use additive migrations and verify data ownership during backfill. Never reset a database without explicit authorization.
4. Parameterize SQL. Scope every query, vector operation, cache key and conversation to its authorized identity.
5. Keep provider secrets server-side and out of logs, fixtures, screenshots and commits. Use placeholders in examples.
6. No paid provider fallback. No default live external API calls in tests. Implement hard quota controls and test them.
7. Keep jobs durable and idempotent. Ready requires complete verified ingestion. Preserve retry/dead/quota states and fencing.
8. Validate response schema, dimensions and limits at provider boundaries. Reindex explicitly when changing embedding models, including same-dimension models.
9. Generate OpenAPI contracts and frontend types from a validated source. Do not maintain incompatible duplicate response shapes.
10. Keep instructions, source documents and public visitors untrusted. Chat remains read-only. Dashboard mutations require backend authorization.
11. Write meaningful tests for security boundaries, state transitions, provider failures and migration behavior. Avoid tests that merely restate implementation.
12. Pin tested dependencies, keep lockfiles and document any new service or recurring cost before enabling it.
13. Do not mark a feature complete while backed by mock responses. Explicitly label fixtures and development-only interfaces.
14. After each increment report behavior changed, checks run, limitations and remaining blockers. Do not claim market readiness without release evidence.
15. Read legacy docs as historical references. Current specifications take precedence where old AWS-only architecture conflicts.
