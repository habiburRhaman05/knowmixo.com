# Knowmivo SaaS implementation pack

Prepared 22 November 2026. These documents specify the intended V1. They do not claim that the implementation already exists.

Read in this order

1. [PRD and scope](01-PRD.md)
2. [Feature acceptance criteria](02-ACCEPTANCE.md)
3. [Technical design](03-TRD.md)
4. [Stack and free services](04-STACK-AND-SERVICES.md)
5. [Data model](05-DATABASE.md)
6. [API contracts](06-API.md)
7. [UI specification](07-UI-SPEC.md)
8. [Existing backend migration](08-BACKEND-GAP-MAP.md)
9. [Ten-day delivery plan](09-BUILD-PLAN.md)
10. [Tests and release gates](10-TEST-AND-LAUNCH.md)
11. [Agent implementation rules](11-AGENT-RULES.md)
12. [Environment and deployment](12-DEPLOYMENT.md)

Added 22 November 2026 — senior DB/backend engineering review before coding starts

13. [DB engineering gap analysis](13-DB-ENGINEERING-GAP-ANALYSIS.md)
14. [Sprint plan with per-sprint test gates](14-SPRINT-PLAN.md)
15. [User stories for the full product flow](15-USER-STORIES.md)
16. [Full API route specification](16-API-ROUTES.md)
17. [Backend architecture gap, module by module](17-BACKEND-ARCHITECTURE-GAP.md)

Added 22 November 2026 (update 2) — V2 vision captured, schema redesigned for it, sprint plan re-sequenced

18. [Scalable DB redesign, V2/V3-aware](18-DATABASE-V2-V3-SCALABLE-SCHEMA.md)
19. [Backend sprint plan, phase-ordered, supersedes 14's sequencing](19-BACKEND-SPRINT-PLAN-V2.md)
20. [Phase 0 credentials/environment checklist](20-CREDENTIALS-CHECKLIST.md)

The copied Python source is preserved in `../backend/`. `../frontend/` is intentionally empty. Original documentation is preserved in `legacy/`. The original Downloads project has not been modified because this session cannot write to that location.

The dates are a ten-working-day target from the first implementation day. Launch depends on passing the release gates. With this feature set, ten days is an aggressive target, not an assurance.

## Scope decisions

- One owner, one company and one chatbot per account in V1. Design the schema for future membership and multiple bots.
- Website widget and hosted chat page. Native mobile SDK, team invitations, billing and agent actions are deferred.
- Free cloud tiers and existing hosting. Quota exhaustion must stop requests or pause ingestion. Unlimited free operation is not promised.
- Complete backend and API verification before frontend implementation.
- Account, company, source and conversation deletion are authenticated dashboard operations. The LLM cannot execute them.
