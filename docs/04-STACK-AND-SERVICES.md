# Stack and free-service decisions

Checked 22 November 2026. Prices, free quotas and model availability can change. Provider dashboard limits and current terms must be verified before deployment.

| Layer | V1 choice | Cost and constraint |
| --- | --- | --- |
| Backend | Existing Python 3.12, FastAPI, Pydantic, psycopg | Open-source software on existing server |
| Migrations | Alembic with explicitly managed SQL migrations | No duplicate ORM ownership of identity tables |
| Worker | Python PostgreSQL-backed durable job runner | Existing server compute, no paid queue service |
| Frontend | Next.js App Router, TypeScript, shadcn/ui, Tailwind | Self-host on existing VPS |
| Forms/data | React Hook Form, Zod, TanStack Query | Open-source |
| Authentication | Auth.js cookie/OAuth transport plus FastAPI identity | Google OAuth and own email/password flows, verify current release compatibility |
| PostgreSQL | Neon Free | Cloud limits, sleeping/compute/storage restrictions apply |
| Redis | Upstash Redis Free | Finite command and storage allowance. Select Free explicitly |
| Vector database | Pinecone Starter | Free limits and index restrictions. Reuse current adapter with lifecycle fixes |
| Embeddings | Cloudflare Workers AI `@cf/baai/bge-m3` | Shares free Workers AI daily neuron allocation |
| Chat LLM | Explicitly allowlisted OpenRouter `:free` model | Availability and small account-wide request caps. No paid model fallback |
| File storage | cloudflare | s3 aws 
| Email | smtp gmail app password |
| Proxy/TLS | Nginx and Let's Encrypt | Existing server. Certificate renewal and HTTP streaming configured |
| Diagnostics | Structured logs, health probes, optional free monitoring | Disable paid Rius/Glassflow dependency for default deployment |
| Tests | pytest/httpx and Playwright | Run locally or within available CI allowance |

Cloudflare currently provides 10,000 neurons per day on the Free plan. Exceeding limits fails requests. It is not a fixed count of embeddings. Do not enable a paid plan to bypass this. [Official pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

Cloudflare setup requires an account ID and a scoped Workers AI API token, created through the dashboard's Workers AI API-token setup. Keep the token in backend/worker environment only. Call `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/baai/bge-m3` with bearer authorization and `{"text":["example"]}`. Validate the live response schema and embedding dimensions because model page schema and examples can differ. [Model documentation](https://developers.cloudflare.com/workers-ai/models/bge-m3/) · [REST setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)

Choose the exact OpenRouter free model during the day-1 live spike by testing English/Bangla, streaming, evidence grounding and provider privacy terms. Record model ID and test results in the deployment manifest. A `:free` suffix is necessary but not a sufficient budget control. Validate configured routes against current pricing and prohibit automatic paid routing. Account-wide limits must gate registrations and visitor usage. [Limits](https://openrouter.ai/docs/api-reference/limits) · [Pricing](https://openrouter.ai/pricing)

Supporting service references are [Neon pricing](https://neon.com/pricing), [Upstash pricing](https://upstash.com/pricing/redis), [Pinecone pricing](https://www.pinecone.io/pricing/), [Resend pricing](https://resend.com/pricing) and [Auth.js credentials](https://authjs.dev/getting-started/providers/credentials). Auth.js does not implement registration, password verification, reset and email delivery for this project. FastAPI must implement them.

## Budget enforcement

Set `FREE_ONLY=true`. Disable Bedrock and other paid-provider adapters in deployed configuration. Validate credentials and selected plan manually. Reserve a global generation budget atomically before starting each provider call and reconcile usage afterward. Set an initial product cap below the observed provider allowance, reserving requests for testing and retries. Fail closed when quota state is unknown. Embed jobs pause when the daily allowance is exhausted. Dashboard and visitor chat must explain temporary unavailability.

Free service use permits a small beta, not an unlimited commercial availability commitment. Review data handling terms before accepting confidential customer documents. Backup storage and bandwidth must also fit existing resources. Do not silently add paid S3, paid vector indexes or premium monitoring.

## Dependencies and pinning

Keep existing working dependencies during document-only restructuring. Implementation replaces boto3 model calls with httpx adapters, adds argon2-cffi, a maintained Google token verification library, Alembic, pytest and multipart upload support. Remove unused paid integrations only after imports are migrated. Pin exact tested versions in Python and JavaScript lockfiles. Resolve Auth.js and Next.js version compatibility in the day-1 spike rather than assuming an untested major version.
