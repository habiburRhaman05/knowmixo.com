# ADR 008 — Billing (Stripe as source of truth)

**Status**: Decided 2026-11-25. Implementation Day 2-4.

## Context

No billing code exists today. `free_only=true` gates all paid providers.

## Decision

- **Stripe as the source of truth for payment state.** Our DB caches entitlements and usage for low-latency reads.
- Use **Stripe Products + Prices with lookup_keys** so prices are environment-swappable (`free`, `starter_monthly`, `growth_monthly`, `scale_monthly`).
- **Stripe Checkout** for subscriptions; **Stripe Customer Portal** for self-service. **Stripe Tax ON** (US sales tax) with home-state registration on Day 1. Non-home-state registrations roll out over the first 30 days post-launch.
- **Webhooks**: single endpoint `POST /api/v1/webhooks/stripe`; HMAC verified with `webhook_secret`; idempotency via `stripe_events(event_id PK)`; out-of-order tolerance (apply only if `created_at > current subscription.updated_at`).
- **Entitlements** read from `plan_features` keyed by `subscription.plan_id`; cached in Redis with 60 s TTL; per-route deps enforce.
- **Usage meter**: reuse existing `usage_daily` + `usage_reservations`; add `usage_events` table (Stripe metered billing) for overage.
- **Dunning**: Stripe retries + email cadence 1/3/7/14 days; soft-disable on day 14; hard-disable on day 21 (publishes paused, widget shows "temporarily unavailable").
- **Refund policy**: clear in ToS; one-click refund from operator console (L).
- **Promo codes**: Stripe coupons. Free-tier abuse: `email_domain` check (disposable list) + device fingerprint on signup (Fingerprint OSS); throttle to one free bot per fingerprint per 24 h.

## Trade-offs

- Stripe Tax requires US state registration paperwork — the owner is on the hook for the first state; subsequent states can be remote-triggered when Stripe flags a threshold breach.
- Caching entitlements in Redis means a webhook delivery delay (seconds) is user-visible on upgrade. Mitigation: `/me/plan/sync` button that re-reads Stripe on demand.

## Rollback

Flip `settings.billing_enabled=false`; all entitlement checks fall through to Free-tier caps.
