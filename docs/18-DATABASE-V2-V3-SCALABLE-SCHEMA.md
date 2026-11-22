# Scalable database redesign — V1 build, V2/V3-aware

This refines [13-DB-ENGINEERING-GAP-ANALYSIS.md](13-DB-ENGINEERING-GAP-ANALYSIS.md) with the owner's stated V2/V3 direction factored in now, so V1 does not paint itself into a second destructive migration later. The rule applied throughout: **build the flexible shape in V1, populate it with simple V1 defaults, and let V2 light up new behavior with new rows/config — not new tables bolted on sideways.**

## V2/V3 vision captured (for traceability)

- **Mandatory lead-gate form**: widget can require name/phone/other fields *before* chat starts, not just the current skippable post-hoc capture.
- **Multiple, customizable forms**: different field sets, possibly different triggers (before start, after N messages, exit intent).
- **Webhooks**: on lead submission (and likely other events), push data to owner-configured third-party endpoints.
- **AI-shared links**: the bot can surface a configured link in its answer when relevant (e.g., "book a demo" → a specific URL), not just free-text citations.
- **Analytics**: beyond the V1 dashboard counts — event-level and rollup reporting.

## Design principle applied per table

| V2 requirement | Naive approach (rejected) | Scalable approach (adopted) |
| --- | --- | --- |
| Required vs. skippable lead form | A boolean flag on `bots` plus hardcoded `name`/`email` columns on `leads` | A `lead_forms` + `lead_form_fields` + `lead_submissions(values JSONB)` model — V1 ships exactly one default form with two optional fields, V2 just inserts more forms/fields, zero migration |
| Webhooks | Add later as an afterthought table once V2 starts | Model `webhook_endpoints` + `webhook_deliveries` in V1's migration set now, reusing the exact durable-delivery pattern already proven by `jobs`/`job_attempts` — disabled/unused in V1, instantly usable in V2 |
| AI-shared links | Stuff links into bot `draft_config` JSON with no structure | A real `bot_links` table with `keywords`/`label`/`url`, so V2's retrieval/prompt step can query structured candidates instead of parsing JSON blobs |
| Analytics | Compute dashboard counts with ad hoc `COUNT(*)` queries forever | A raw `analytics_events` stream (cheap to write, append-only) plus a `analytics_daily_rollup` summary table for fast dashboard reads — V1 can start by writing events for the handful of things that already happen (widget open, message sent, feedback) even before V2's dashboards consume them |

## New / revised tables (superseding the equivalent rows in 05-DATABASE.md and 13)

### `leads` → replaced by `lead_forms`, `lead_form_fields`, `lead_submissions`

```
lead_forms
  id uuid PK
  bot_id uuid FK -> bots(id)
  name text                          -- e.g. "Default", "Pricing page form" (V2: multiple per bot)
  trigger text NOT NULL DEFAULT 'post_hoc'
    CHECK (trigger IN ('post_hoc','before_chat_start','after_n_messages','exit_intent'))
  trigger_config jsonb DEFAULT '{}'  -- e.g. {"after_n_messages": 3} — empty in V1
  is_required boolean NOT NULL DEFAULT false   -- V1 default false (skippable); V2 can flip to true per bot
  is_active boolean NOT NULL DEFAULT true
  created_at, updated_at timestamptz

lead_form_fields
  id uuid PK
  lead_form_id uuid FK -> lead_forms(id)
  field_key text NOT NULL             -- 'name','email','phone','company', or a custom key
  label text NOT NULL
  field_type text NOT NULL CHECK (field_type IN ('text','email','phone','select','checkbox','textarea'))
  is_required boolean NOT NULL DEFAULT false
  options jsonb                        -- for 'select' type
  sort_order integer NOT NULL DEFAULT 0
  UNIQUE (lead_form_id, field_key)

lead_submissions
  id uuid PK
  conversation_id uuid FK -> conversations(id)
  lead_form_id uuid FK -> lead_forms(id)
  values jsonb NOT NULL                -- {"name": "...", "phone": "...", ...} keyed by field_key
  consent_at timestamptz
  created_at timestamptz NOT NULL DEFAULT now()
  UNIQUE (conversation_id, lead_form_id)   -- one submission per form per conversation
```

**V1 behavior on this shape**: at bot creation, seed exactly one `lead_forms` row (`trigger='post_hoc'`, `is_required=false`) with two `lead_form_fields` rows (`name`, `email`, both optional). This is *functionally identical* to the flat `leads(name, email, consent_at)` table the original spec described — but it costs nothing extra to build now and means V2's "required form before chat start" and "multiple custom forms" ship as **new rows and one new enum value usage**, not a migration that has to touch every existing lead record.

**Gating enforcement for V2** (not built in V1, but the column exists so V1 doesn't need another migration): `conversations` gains `lead_gate_satisfied_at timestamptz NULL`. V1 always treats this as satisfied implicitly (no gate). V2's chat-start endpoint checks: if the bot has any `lead_forms` row with `trigger='before_chat_start' AND is_required=true` and `lead_gate_satisfied_at IS NULL`, block message sending until a `lead_submissions` row exists for that form, then set the timestamp.

### New: `webhook_endpoints`, `webhook_deliveries` (modeled in V1 migrations, dormant until V2)

```
webhook_endpoints
  id uuid PK
  company_id uuid FK -> companies(id)
  url text NOT NULL
  secret_hash text NOT NULL            -- HMAC signing secret, hashed at rest; raw secret shown once on creation
  event_types text[] NOT NULL          -- e.g. ['lead.submitted','conversation.completed']
  is_active boolean NOT NULL DEFAULT true
  created_at timestamptz NOT NULL DEFAULT now()

webhook_deliveries
  id uuid PK
  webhook_endpoint_id uuid FK -> webhook_endpoints(id)
  event_type text NOT NULL
  payload jsonb NOT NULL
  state text NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending','delivered','failed','retrying','dead'))
  attempts integer NOT NULL DEFAULT 0
  max_attempts integer NOT NULL DEFAULT 4
  last_attempt_at timestamptz
  next_attempt_at timestamptz
  response_code integer
  idempotency_key text UNIQUE
  created_at timestamptz NOT NULL DEFAULT now()
```

This deliberately mirrors the `jobs`/`job_attempts` durable-delivery pattern already required for ingestion (lease-free here since delivery attempts are short HTTP calls, but same retry/backoff/dead-letter philosophy) — the Sprint 2 job runner code is directly reusable for webhook delivery in V2, not a new subsystem.

**Why build the tables now, even unused**: adding `company_id`-scoped, constraint-correct tables at the same time as the rest of the schema is nearly free. Adding them in V2 after real webhook-dependent customer workflows exist means a live migration under usage — strictly riskier. The V1 backend simply never calls the code path that writes to `webhook_deliveries`.

### New: `bot_links` (modeled in V1, not wired into the chat pipeline until V2)

```
bot_links
  id uuid PK
  bot_id uuid FK -> bots(id)
  document_id uuid FK -> documents(id) NULL   -- optional: tie a link to a specific source
  label text NOT NULL
  url text NOT NULL
  keywords text[] NOT NULL DEFAULT '{}'        -- naive trigger terms for V2's retrieval step to match against
  is_active boolean NOT NULL DEFAULT true
  created_at timestamptz NOT NULL DEFAULT now()
```

V2 wires this into the Sprint 4 retrieval pipeline as an additional candidate set alongside Pinecone chunks — the LangGraph state already carries "retrieved content is text plus metadata" per the TRD, so link candidates slot into the same evidence-filtering step rather than requiring a new orchestration path.

### New: `analytics_events`, `analytics_daily_rollup`

```
analytics_events
  id bigserial PK
  company_id uuid NOT NULL
  bot_id uuid NOT NULL
  event_type text NOT NULL            -- 'widget_open','message_sent','lead_submitted','link_clicked','feedback_given', ...
  conversation_id uuid NULL
  message_id uuid NULL
  metadata jsonb NOT NULL DEFAULT '{}'
  created_at timestamptz NOT NULL DEFAULT now()
  -- append-only, no updates. Index: (company_id, bot_id, event_type, created_at)

analytics_daily_rollup
  company_id uuid NOT NULL
  bot_id uuid NOT NULL
  day date NOT NULL
  metric_key text NOT NULL             -- 'messages_sent','leads_captured','unique_visitors', ...
  metric_value bigint NOT NULL DEFAULT 0
  UNIQUE (company_id, bot_id, day, metric_key)
```

**V1 scope**: start writing `analytics_events` rows for the handful of things V1 already does (message sent, feedback given, conversation started) — it's one `INSERT` per existing mutation, essentially free, and it means V2's dashboards have historical data from day one instead of starting at zero. The rollup job itself (nightly aggregation) is explicitly **not** a V1 deliverable — it's V2/V3 work — but the raw event table being populated from V1 onward is the actual expensive-to-retrofit part, so it's in scope now.

## Everything else from 13-DB-ENGINEERING-GAP-ANALYSIS.md still applies unchanged

The identity/tenancy/job/publication findings in doc 13 are not revised by this V2 lens — those are V1-blocking regardless of V2 plans. This document only adds the lead/webhook/link/analytics shape changes described above. Treat 13 + 18 together as the full target schema for the Sprint 1 migration work.

## Updated migration sequencing (supersedes the sequencing note in doc 13 section 5)

1. **Migration 0001** (Sprint 1): `users, oauth_accounts, sessions, auth_tokens, companies, memberships`.
2. **Migration 0002** (Sprint 2): `bots, documents, document_versions, chunks, jobs, job_attempts`.
3. **Migration 0003** (Sprint 3): `publications, publication_sources, bot_links` (link table added here since it's bot-scoped and bots exist by now — still unused by application code).
4. **Migration 0004** (Sprint 4): `visitor_sessions, conversations, messages, lead_forms, lead_form_fields, lead_submissions, feedback, usage_reservations, usage_daily, analytics_events`. Seed the default `lead_forms`/`lead_form_fields` row pair in the same migration that creates `bots`' first row logic (application-level seed on bot creation, not a SQL seed migration).
5. **Migration 0005** (Sprint 5): `audit_events` (rebuilt), `webhook_endpoints`, `webhook_deliveries`. Drop legacy `approvals`.
6. **V2 migrations** (future): no new tables required for the lead-gate-required toggle, multi-form, or webhook delivery activation — those are config/feature-flag changes plus turning on dormant code paths against tables that already exist. `analytics_daily_rollup` is the one genuinely new V2 table, added when the rollup job is actually built.

This is the concrete payoff of the redesign: **V2 launch requires roughly one new table (`analytics_daily_rollup`) instead of six**, and zero backfill of a flat `leads(name,email)` table into a JSONB shape under live traffic.
