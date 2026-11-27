# 09 · Billing & payments (Stripe, USD)

Pairs with ADR 008. All amounts USD; all tests in Stripe test mode until the launch-day flip.

## 1 · Plan matrix (starting hypothesis — validate against real cost measured on Day 9)

| Plan | /mo | /yr | AI replies / mo | Sources | Storage | Bots | Members | Channels | Analytics | SLA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Free | $0 | — | 100 | 3 | 20 MB | 1 | 1 | Widget | 7 d | — |
| Starter | $29 | $290 | 2 000 | 20 | 200 MB | 1 | 2 | Widget + Slack | 30 d | — |
| Growth | $99 | $990 | 10 000 | 100 | 2 GB | 3 | 5 | + WhatsApp + SMS | 90 d | 48 h email |
| Scale | $299 | $2990 | 40 000 | unlimited | 20 GB | 10 | 15 | + Shopify + HubSpot + API | 1 y | 24 h email |
| Agency | $699 | $6990 | 120 000 | unlimited | 100 GB | 50 (multi-workspace) | 50 | all | 2 y | 8 h email |

Credit = 1 AI reply. Model tier is a flat feature on each plan until paid models land (then it becomes a dial).

## 2 · Stripe Products + Prices (lookup keys)

Create in Stripe dashboard (test mode first):

| Lookup key | Nickname | Interval | Recurring | Stripe Tax |
| --- | --- | --- | --- | --- |
| `free` | Free | — | — | no |
| `starter_monthly` | Starter · Monthly | month | yes | yes |
| `starter_yearly` | Starter · Yearly | year | yes | yes |
| `growth_monthly` | Growth · Monthly | month | yes | yes |
| `growth_yearly` | Growth · Yearly | year | yes | yes |
| `scale_monthly` | Scale · Monthly | month | yes | yes |
| `scale_yearly` | Scale · Yearly | year | yes | yes |
| `agency_monthly` | Agency · Monthly | month | yes | yes |
| `agency_yearly` | Agency · Yearly | year | yes | yes |
| `overage_reply` | Overage · 1 000 AI replies | metered | usage | yes |

`overage_reply` is Stripe metered billing — we report usage via the Stripe Billing Meter API.

## 3 · Schema (Alembic 0011)

```sql
CREATE TABLE plans (
  id text PRIMARY KEY,                       -- 'free'|'starter_monthly'|...
  name text NOT NULL,
  interval text NOT NULL,                    -- 'month'|'year'|'once'
  stripe_lookup_key text UNIQUE,
  limits jsonb NOT NULL,                     -- replies/month, sources, bots, members, storage_mb
  features jsonb NOT NULL,                   -- {whatsapp:true, hubspot:false, ...}
  sort_order int NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  stripe_customer_id text UNIQUE,
  stripe_subscription_id text UNIQUE,
  plan_id text NOT NULL REFERENCES plans(id),
  status text NOT NULL,                      -- trialing, active, past_due, canceled, paused
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean DEFAULT false,
  paused_at timestamptz,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE usage_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  kind text NOT NULL,                        -- 'ai_reply' | 'embed' | 'overage'
  quantity numeric(12,4) NOT NULL,
  period_start timestamptz,
  period_end timestamptz,
  reported_to_stripe_at timestamptz,
  stripe_meter_event_id text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX usage_events_company_period ON usage_events(company_id, period_start);

CREATE TABLE invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  stripe_invoice_id text UNIQUE,
  amount_cents int NOT NULL,
  currency text NOT NULL DEFAULT 'usd',
  status text NOT NULL,                      -- draft, open, paid, uncollectible, void
  hosted_url text,
  pdf_url text,
  period_start timestamptz,
  period_end timestamptz,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE stripe_events (
  event_id text PRIMARY KEY,                 -- idempotency
  type text NOT NULL,
  created_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL,
  processed_at timestamptz
);
```

## 4 · Webhook handling

Endpoint: `POST /api/v1/webhooks/stripe`.

1. Verify `Stripe-Signature` with the webhook secret.
2. Parse event; **insert into `stripe_events` on primary-key conflict do nothing** → built-in idempotency.
3. Return `200` immediately. Processing happens on the dispatcher worker reading `stripe_events WHERE processed_at IS NULL`.
4. Processor handles these event types:
   - `customer.subscription.created / updated` → upsert `subscriptions`
   - `customer.subscription.deleted` → mark canceled
   - `invoice.paid` → insert `invoices(status='paid')`
   - `invoice.payment_failed` → enqueue dunning email
   - `checkout.session.completed` → activate subscription + redirect token
   - `customer.subscription.trial_will_end` → notification
5. Out-of-order handling: before applying, check `event.created > subscription.updated_at`. If not, skip.

## 5 · Entitlements

```python
# backend/app/billing/entitlements.py
def entitlements(company_id) -> dict:
    sub = cache.get(f"ent:{company_id}") or db_read(company_id)
    return sub.plan.features | sub.plan.limits   # merged dict
```

Per-route dependency `require_feature('whatsapp')` or `require_quota('ai_replies', n=1)`. Cache TTL 60 s. `/me/plan/sync` endpoint re-reads Stripe on demand.

## 6 · Usage meter

Reuse `usage_daily` + `usage_reservations` for the daily guard (already in schema). At each AI reply, additionally insert a `usage_events(kind='ai_reply')` row. Nightly cron rolls up the day → single Stripe meter event (batched to respect Stripe rate limits).

## 7 · Lifecycle

| Event | Our behavior |
| --- | --- |
| Upgrade | immediate — update plan, prorate via Stripe |
| Downgrade | immediate limits down; refund unused via credit note |
| Cancel at period end | `cancel_at_period_end=true`, keep features until period_end |
| Failed payment | day 0: in-app banner; day 3, 7, 14 emails; day 14 soft-disable (publishes paused); day 21 hard-disable |
| Refund | admin console button → Stripe refund + credit note |
| Reactivate | before period_end: unflag cancel; after: new checkout |
| Account deletion with active sub | cancel sub immediately + refund proration |

## 8 · Promo codes

Stripe coupons. Dashboard admin create + tie to lookup keys. Launch promo: `PILOT100` → 100 % off first 3 months Growth.

## 9 · Free-tier abuse protection

- Disposable email domains list (`disposable-email-domains` npm / python package)
- Browser fingerprint (optional; Fingerprint OSS)
- One free bot per `(ip_prefix, email_domain, fingerprint)` per 24 h
- Rate-limit signup to 5/hour/IP

## 10 · Local testing

- `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe`
- Stripe Test Clocks for subscription-lifecycle tests (`stripe test_helpers.test_clocks.advance`)
- Test cards: `4242 4242 4242 4242` (success), `4000 0000 0000 9995` (insufficient funds), `4000 0000 0000 0341` (dispute)
- Pytest fixtures mock the Stripe SDK; webhook handler tests assert idempotency with the same event_id delivered twice.

## 11 · Cost model (per reply, free stack)

Using today's providers:

- Embedding: 1 call to Cloudflare bge-m3 (cached per message), ~200 tokens → 0 cost (free tier)
- Retrieval: Postgres query, ~5 ms, effectively $0
- Rerank: Cloudflare bge-reranker, ~30 passages, free tier
- LLM: Groq gpt-oss-120b, ~1 500 in + 400 out tokens → free tier (quota permits)
- Infra: Neon + Upstash + R2 + Cloudflare ≈ $0.00005 / reply amortized

**Current cost per reply ≈ $0.00005** (dominated by storage amortisation). Gross margin at every plan is > 99 % on free stack.

Once paid LLM lands: assume Claude Haiku pricing tier (benchmark) → ~$0.004 / reply. At that price the Starter plan ($29 for 2 000 replies = $0.0145 / reply) has 72 % GM, Growth has 81 %, Scale has 92 %. Flag any plan under 75 % GM → Starter may need to be re-sized.

## 12 · Live-switch checklist (Day 10)

1. Switch Stripe account from test → live.
2. Re-create Products + Prices in live mode using same lookup keys.
3. Point `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` at live.
4. Register webhook endpoint in Stripe live; copy new `STRIPE_WEBHOOK_SECRET`.
5. Enable Stripe Tax; register in home state.
6. Make one $1 purchase on a real card + refund it → full lifecycle verified.
7. Set `settings.billing_mode = 'live'`.
