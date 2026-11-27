# 04 · Target architecture

One picture, four flows, nine decisions. Each ADR is a separate file under `launch/adr/`.

## Topology (production target, US-east)

```mermaid
flowchart LR
  subgraph Browser
    V[Visitor<br/>widget / hosted chat]
    O[Owner<br/>Next.js dashboard]
  end

  subgraph Edge[CDN / Nginx reverse proxy]
    EM[embed.js static]
    APPNX[Next.js /app, /api/bff/*, /api/widget/*]
  end

  subgraph Services
    API[FastAPI API<br/>stateless pod x N]
    WK[Worker<br/>ingestion + webhooks + escalation]
    EV[Eval runner<br/>nightly batch]
  end

  subgraph Data
    PG[(Neon Postgres<br/>pgvector + FTS + RLS)]
    RD[(Upstash Redis<br/>rate limits · pub/sub · semantic cache · grants)]
    PC[(Pinecone<br/>fallback vector store — see ADR 1)]
    S3[(Cloudflare R2<br/>source files)]
  end

  subgraph External
    CF[Cloudflare Workers AI<br/>bge-m3 + reranker]
    PR[Provider Router<br/>Groq → OpenRouter → Gemini]
    STR[Stripe Checkout + Portal + Tax]
    WA[Meta WhatsApp Cloud API]
    TW[Twilio SMS]
    SK[Slack / Telegram / email]
    SY[Sentry]
  end

  V -->|HTTPS| EM
  V -->|SSE / fetch| APPNX
  O --> APPNX
  APPNX -->|Bearer| API
  API --> PG
  API --> RD
  API --> CF
  API --> PR
  API --> STR
  API --> SY
  WK --> PG
  WK --> CF
  WK --> PR
  WK --> WA
  WK --> TW
  WK --> SK
  EV --> PG
  EV --> PR
  API --> PC
```

Three guarantees the topology encodes:
- **Stateless API pods**: everything mutable lives in Postgres or Redis. We can run 1 or 5 pods identically.
- **One durable queue**: ingestion, webhooks, escalation, re-crawl all use `jobs` + `job_attempts`. No Celery, no SQS.
- **One identity surface**: BFF → Bearer → backend. Visitor Bearer and owner Bearer are different scopes; backend accepts both but routes them to disjoint handlers.

## Chat data flow (RAG v2)

```mermaid
sequenceDiagram
  autonumber
  participant Vis as Visitor
  participant BFF as Next BFF
  participant API as FastAPI
  participant GD as Guard + Intent
  participant QR as Query rewriter
  participant RT as Retriever (dense+FTS+RRF)
  participant RR as Reranker
  participant SG as Sufficiency grader
  participant LLM as LLM (grounded)
  participant VF as Verifier
  participant PG as Postgres (+rag_traces)
  Vis->>BFF: POST /widget/.../messages (text)
  BFF->>API: POST /public/.../messages
  API->>GD: classify(text, history)
  GD-->>API: {intent, severity, language}
  alt severity in {critical, high}
    API-->>Escalation: fire async
  end
  API->>QR: rewrite(text, history)
  QR-->>API: queries[]
  loop up to 3
    API->>RT: hybrid search(queries[], filters)
    RT-->>API: candidates (RRF fused)
    API->>RR: rerank top ~30 → top 8
    RR-->>API: ranked[]
    API->>SG: sufficient?
    SG-->>API: ok | expand | abstain
  end
  API->>LLM: stream(prompt, evidence, config)
  LLM-->>API: tokens (SSE pass-through)
  API->>VF: faithfulness(claims, evidence)
  alt not faithful
    API->>LLM: regenerate once or abstain
  end
  API->>PG: write rag_traces + analytics_events
  API-->>BFF: SSE meta / sources / delta / done
  BFF-->>Vis: SSE pass-through
```

Latency budget: guard ≤ 60 ms · rewrite ≤ 400 ms · retrieve ≤ 200 ms · rerank ≤ 350 ms · grade ≤ 250 ms · TTFT p50 ≤ 2 s on free Groq.

## Ingestion flow

```mermaid
sequenceDiagram
  participant Owner
  participant API
  participant Jobs
  participant WK as Worker
  participant Parser
  participant Chunker
  participant CF as Cloudflare embed
  participant PG
  participant S3
  Owner->>API: POST /sources/text|url|file-complete
  API->>PG: INSERT documents + document_versions(status=pending)
  API->>Jobs: enqueue_job(kind=ingest_document, idempotent)
  API-->>Owner: 202 {job_id}
  WK->>Jobs: claim
  WK->>Parser: parse(file|html|text)
  Parser-->>WK: blocks
  WK->>Chunker: contextual_chunk(blocks)
  Chunker-->>WK: chunks
  WK->>CF: embed_batch(chunks)
  CF-->>WK: vectors
  WK->>PG: INSERT chunks(text, embedding, tsvector), UPDATE document_versions(ready)
  WK->>S3: store raw file (if file)
```

## Escalation flow

```mermaid
sequenceDiagram
  participant API
  participant Cls as Severity Classifier
  participant Esc as Escalation Engine
  participant WA
  participant SMS
  participant Slack
  participant Owner
  API->>Cls: on each message (parallel to answering)
  Cls-->>API: severity
  alt severity >= high
    API->>Esc: create(escalation)
    Esc->>Esc: persist state=created
    Esc->>Esc: pick channel from owner config
    Esc->>WA: send template(variables, deep_link)
    WA-->>Esc: message_id
    Esc->>Esc: state=sent
    WA->>Esc: delivery/read webhook
    Esc->>Esc: state=delivered
    alt no ACK within SLA
      Esc->>SMS: fallback
    end
    Owner->>Esc: click deep_link
    Esc->>Esc: state=acknowledged
  end
```

## Deployment

- Target host: owner's existing VPS, 4 vCPU / 8 GB.
- Docker Compose: `api`, `worker`, `nginx` (TLS + SSE buffering off), optional `node_exporter`.
- CDN: Cloudflare in front of `app.knowmivo.com` (dashboard + widget iframe + embed.js).
- DNS layout: `app.knowmivo.com` (Next.js), `api.knowmivo.com` (FastAPI, ingress through same Nginx), `cdn.knowmivo.com` (Cloudflare pages mirror for `embed.js`, optional).
- Email: Postmark or Resend (reputation-safe, cheap). SPF/DKIM/DMARC at DNS.
- Secrets: single `.env` per env (`.env.staging`, `.env.production`); loaded by systemd `EnvironmentFile=` or docker-compose `env_file`.
- Health probes: `/api/v1/health/ready` for the API + `/api/health` for the frontend.

## Observability

- **Logs**: JSON to stdout → Loki (if the VPS runs it) or Cloudflare Logpush. Fields: `ts`, `level`, `msg`, `request_id`, `company_id`, `conversation_id`, `user_id`, `path`.
- **Traces**: `sentry-sdk[fastapi]` (free tier) + OTel SDK optional, 10 % sample on chat.
- **Metrics**: `/metrics` Prometheus endpoint from `prometheus-fastapi-instrumentator`.
- **Alerts**: Sentry → Slack; UptimeRobot for /health.
- **SLOs**: availability 99.5 % monthly · chat TTFT p50 ≤ 2 s · ingest ready p95 ≤ 180 s per MB.

## Nine architecture decisions (full ADRs linked)

| ADR | Topic | Decision | File |
| --- | --- | --- | --- |
| 001 | Vector store | **pgvector + FTS in Postgres** (Pinecone becomes a compat shim, deprecated after Day 3) | `adr/001-vector-store.md` |
| 002 | Tenant isolation | **App filter + Postgres RLS + fail-closed regression** | `adr/002-rls.md` |
| 003 | Async / queueing | Keep existing `jobs` runner; add outbox pattern on event emit | `adr/003-queue-outbox.md` |
| 004 | LLM provider router | Interface + Groq primary + OpenRouter fallback + per-tenant RL + semantic cache | `adr/004-provider-router.md` |
| 005 | Realtime | **SSE + Redis pub/sub** for inbox (WebSocket only if P1 blocker emerges) | `adr/005-realtime.md` |
| 006 | Widget delivery | Loader + iframe (keep) + versioned CDN URL + strict postMessage schema | `adr/006-widget-delivery.md` |
| 007 | API versioning | Lock `/api/v1`, generate OpenAPI → TS client in CI, RFC 9457 problem-details | `adr/007-api-conventions.md` |
| 008 | Billing | Stripe as source of truth, our DB as cache; Stripe Tax on, reconciliation cron | `adr/008-billing.md` |
| 009 | Data retention | `retention_days` per plan + nightly hard-delete worker + export pre-delete | `adr/009-data-lifecycle.md` |

Everything else in section 6 of the master prompt folds into one of these nine. Config/secrets/flags (12) live inside 004+008+009; deployment (12) is captured in the topology above; frontend architecture (13) is in `08-UX-SPEC.md`.
