# 06 · Escalation / emergency engine

Concrete design for Appendix A of the master prompt. US-first. WhatsApp primary; SMS, email, Slack, Telegram as fallbacks.

## 1 · Data model

```sql
-- Alembic 0010
CREATE TABLE escalation_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  name text NOT NULL,
  match jsonb NOT NULL,          -- {keywords:[], intents:[], severity_min, page_patterns:[], vip_attrs:{}}
  severity text NOT NULL CHECK (severity IN ('critical','high','medium','low')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalation_contacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  channel text NOT NULL CHECK (channel IN ('whatsapp','sms','email','slack','telegram','push')),
  address text NOT NULL,         -- phone E.164, email, Slack webhook, Telegram chat_id
  verified_at timestamptz,       -- opt-in proof
  priority int NOT NULL,         -- 1=primary, 2=backup, ...
  quiet_hours_tz text,
  quiet_hours_start time,
  quiet_hours_end time,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE escalations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  rule_id uuid REFERENCES escalation_rules(id) ON DELETE SET NULL,
  severity text NOT NULL,
  reason_summary text NOT NULL,
  ai_summary text NOT NULL,
  key_details jsonb NOT NULL,     -- {name, email, order_id, amount, page_url}
  state text NOT NULL CHECK (state IN ('created','queued','sent','delivered','acknowledged','failed','dead')),
  acknowledged_at timestamptz,
  acknowledged_by uuid REFERENCES users(id),
  acknowledged_channel text,
  deep_link_jti uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalation_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  escalation_id uuid NOT NULL REFERENCES escalations(id) ON DELETE CASCADE,
  attempt int NOT NULL,
  channel text NOT NULL,
  address text NOT NULL,
  provider_message_id text,
  state text NOT NULL,           -- queued, sent, delivered, read, failed
  error_code text,
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz
);

CREATE UNIQUE INDEX escalations_dedupe
  ON escalations (conversation_id, severity, date_trunc('minute', created_at));
```

## 2 · Detection

Runs **in parallel** with answering (fire-and-forget via `event_outbox`).

1. **Visitor explicit** (regex in `rag_v2/stages/intent.py`): "urgent", "emergency", "I need a human", "lawyer", "chargeback", "refund now", "cancel".
2. **Classifier output** from intent stage returns `severity`.
3. **Owner rules**: evaluated on each turn in `escalation/rules.py` → first match wins.
4. **Behavioral**: 2 consecutive abstentions (read from `rag_traces`); 3 repeated thumbs-down within a session; visitor frustration keywords.

## 3 · Safety behavior for the visitor (US)

For `severity='critical'` AND intent='emergency', the chat pipeline overrides the LLM output and sends:

> "If you or someone else is in immediate danger, please call **911** right now. For mental-health crises, call or text **988** (US Suicide & Crisis Lifeline). I've also notified a human from the team."

This is hard-coded in `app/chat/rag_v2/safety.py` — owner cannot disable.

## 4 · Owner message content (WhatsApp)

Template categories we submit to Meta (initial set):

### 4.1 `escalation_critical_v1` (Utility category)

```
{{brand_name}} — URGENT

Reason: {{reason_summary_80}}
Summary: {{ai_summary_200}}
Contact: {{contact_or_dash_40}}
Page: {{page_url_60}}
Time: {{local_time_20}}

Acknowledge: {{deep_link_60}}
```

Variables: 1-6, all within length limits per WhatsApp template rules.

### 4.2 `escalation_high_v1` — same template, "URGENT" → "Important"

### 4.3 `escalation_resolved_v1` — ack confirmation reply (within 24-h customer-service window)

Full transcript is **not** pasted into WhatsApp by default (privacy). Owner setting can include a 300-char excerpt.

**Deep link** format: `https://app.knowmivo.com/t/{jti}` (short host). Backend `/t/{jti}` resolves the jti, checks jti exists and unused + not expired (15 min), creates a step-up magic link or redirects to `/conversations/{id}?takeover=1` if owner has an active session.

## 5 · Delivery state machine

```
created → queued → sent → delivered → acknowledged
                     ↓          ↓
                   failed    failed_delivery
                     ↓
              fallback_channel (same loop, priority+1 contact)
                     ↓
              escalated_to_backup
                     ↓
                    dead
```

SLAs by severity (configurable):
- `critical`: retry after 60 s, escalate to next contact at 180 s, dead at 900 s
- `high`: retry after 120 s, next at 600 s, dead at 1800 s
- `medium`: retry after 300 s, next at 1800 s, dead at 3600 s
- `low`: retry after 600 s, next at 3600 s, dead at 7200 s

Dead: writes to `event_outbox('escalation.dead')` → email the owner + Slack ops channel.

## 6 · Acknowledgement

- **Link open** (deep link resolves): writes `acknowledged_channel='link'`.
- **Reply** `ACK` or `TAKE` on WhatsApp (two-way messaging if owner has an open session): webhook handler marks ack.
- **Button click** on Slack message: webhook.

Debounce: an escalation already ack'd within the dedupe window merges new context into the existing row instead of firing a new message.

## 7 · Quiet hours

Owner sets per-contact TZ + start/end. Non-critical messages during quiet hours are queued until end-of-window. **`critical` severity always overrides quiet hours** — contractual requirement in the UX.

## 8 · Storm protection

Per-company rate limit of 5 WhatsApp sends / minute (soft) → 10 / minute (hard). Beyond hard: switch to "digest mode" — fold additional escalations into a single `escalation_digest` message with counts and links.

## 9 · Opt-in verification

Owner adds a number → backend sends an SMS/WhatsApp with a 6-digit code → owner enters code → row `verified_at` set. Without `verified_at` the engine refuses to send to that address.

## 10 · Test-alert button

`POST /escalations/test` with `{contact_id, severity}` — runs the real path but marks the resulting row `test=true`. UI shows delivery status live.

## 11 · Tests (all automated with fake providers)

- Every trigger type fires exactly one escalation per dedupe window.
- Severity mapping (classifier + rules) correctly cascades.
- Safety response text sent for `critical`+emergency intent.
- Template variable rendering within length limits.
- Retry/backoff respects SLA table.
- Fallback channel used in correct priority order.
- ACK handling marks state.
- Re-escalation timing (freezegun fake clock).
- Quiet hours honoured for non-critical, bypassed for critical.
- Dedupe/merge appends context without re-sending.
- Storm protection flips to digest mode.
- Deep link signing/expiry/replay prevention:
  - Expired jti → 410.
  - Reused jti → 410.
  - Wrong signature → 401.
- Opt-in enforcement: send to `verified_at IS NULL` address → immediate `failed`.
- Tenant isolation: Company B's rules cannot fire on Company A's conversations.

## 12 · Code layout

```
backend/app/escalation/
  __init__.py
  detector.py            # evaluates rules + behavioral triggers
  rules.py               # CRUD + matcher
  state_machine.py
  deep_link.py           # jti + jwt sign/verify + single-use via Redis
  channels/
    whatsapp.py          # Meta Cloud API
    sms_twilio.py
    email_ses.py         # or postmark
    slack_webhook.py
    telegram.py
    push.py              # Web push + VAPID keys
  templates/
    whatsapp_escalation_critical.json
    whatsapp_escalation_high.json
    whatsapp_escalation_digest.json
  worker.py              # dispatch loop reusing jobs runner (kind='escalation_dispatch')
```

## 13 · WhatsApp Cloud API constraints (verify before Day 6)

Must verify against the current Meta docs (flagged as PENDING_EXTERNAL in `03-RISKS-AND-BLOCKERS.md`):

- Business verification, phone number, WABA.
- Templates have a category (Utility vs Marketing) and approval delay ~24-72 h.
- Variable count/length limits.
- Opt-in requirements (Meta requires recorded opt-in with timestamp and language of consent).
- The 24-h customer-service window (free-form messages allowed only after a user-initiated contact in the last 24 h).
- Delivery / read webhooks and their shapes.
- Rate limits (tiered by account quality).
- Pricing (per-message after the free-conversation threshold).

Each of these informs a code choice; capture the result in `launch/adr/010-whatsapp.md` on Day 1.

## 14 · Rollback

Toggle `settings.escalation.enabled = false`. Rules keep evaluating but no messages fire; events still go into `escalations` with state `created` so nothing is lost. Flip back when ready.
