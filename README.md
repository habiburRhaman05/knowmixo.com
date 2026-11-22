# Knowmivo chatbot SaaS

This reorganized working copy preserves the existing Python/FastAPI project and adds a complete V1 engineering plan.

- [Planning index](docs/README.md)
- [Existing backend migration map](docs/08-BACKEND-GAP-MAP.md)
- [Ten-day backend-first build plan](docs/09-BUILD-PLAN.md)
- [Original backend README](backend/README.md)

The root contains docs, backend and an intentionally empty frontend directory. Existing documentation is archived under docs/legacy. Existing source code is unchanged. Auth, free providers, async workers and the Next.js frontend described in the plan still require implementation.

Run legacy backend commands from backend. Its archived GitHub workflow is preserved inside backend/.github and is not active at the new root. Establish a new tested root CI workflow during implementation.

This copy was created because the original Downloads directory is read-only to this session. Review and use this root for implementation without overwriting local secret environment files.

Brand name: Knowmivo. See [brand and domain check](docs/00-BRAND.md).
