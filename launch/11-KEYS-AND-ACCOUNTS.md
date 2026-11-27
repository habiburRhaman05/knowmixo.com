# 11 · Keys and accounts

Everything we need to buy, provision, or get approved. Grouped by when it unblocks work. **Long-lead items at the top of §1 — start today.**

## 0 · Already provisioned (confirmed in this session)

- Neon Postgres (`DATABASE_URL` set, 150 chars, SSL, head = 0008)
- Upstash Redis (`REDIS_URL` set, 105 chars, `rediss://`)
- Pinecone (`PINECONE_API_KEY`, `PINECONE_HOST`, index `knowmixo-rag-sa`)
- Cloudflare Workers AI (`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `@cf/baai/bge-m3`)
- Groq (`GROQ_API_KEY`, `gpt-oss-120b`)
- Google OAuth (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`)
- SMTP Gmail (`SMTP_USER`, `SMTP_APP_PASSWORD`, `EMAIL_FROM`) — but `SMTP_HOST="gmail"` must be `smtp.gmail.com`
- Encryption key (`ENCRYPTION_KEY`, 64 hex / 32 bytes)

## 1 · Long-lead (start Day 1 or earlier)

| ID | Service | Why | Expected wait | Env vars | Dashboard path | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| LL1 | Meta Business Verification | WhatsApp Cloud API | 1-4 weeks | n/a | business.facebook.com → Business Settings → Security Center | Need articles of incorporation + utility bill |
| LL2 | WhatsApp Cloud API (WABA, phone number ID, permanent system-user token) | Escalation + inbound | 2-5 days after LL1 | `WA_PHONE_NUMBER_ID`, `WA_BUSINESS_ACCOUNT_ID`, `WA_ACCESS_TOKEN`, `WA_WEBHOOK_VERIFY_TOKEN` | developers.facebook.com → My Apps → WhatsApp | Add the number to the app, generate permanent token (system user) |
| LL3 | WhatsApp template approval (`escalation_critical_v1`, `escalation_high_v1`, `escalation_digest_v1`) | Required to initiate messages outside the 24-h window | 24-72 h per template | n/a | WhatsApp Manager → Message Templates | Submit drafts from `06-ESCALATION-DESIGN.md` §4 |
| LL4 | Twilio 10DLC (A2P brand + campaign) or Toll-free verification | SMS fallback | 2-8 weeks | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_MESSAGING_SERVICE_SID` | console.twilio.com → Messaging → Regulatory Compliance | Required for US A2P SMS |
| LL5 | Stripe Tax registration (home state) | US sales tax | 1-7 days per state | n/a | dashboard.stripe.com → Settings → Tax | Register additional states post-launch as revenue triggers |
| LL6 | Email domain + SPF/DKIM/DMARC | Transactional email reputation | 1-2 days | `POSTMARK_SERVER_TOKEN` or `RESEND_API_KEY` | postmarkapp.com or resend.com | Switch off Gmail SMTP for transactional at launch — Gmail is fine for dev but has low daily caps |
| LL7 | Domain + DNS | app/api/cdn hostnames | hours | n/a | Registrar | `knowmivo.com` per docs/00; verify ownership |
| LL8 | TLS certs (Let's Encrypt) | TLS | minutes | n/a | certbot on the VPS | Wildcard recommended |
| LL9 | Attorney review of privacy/terms/DPA | Legal cover | 3-7 business days | n/a | n/a | Submit markdown drafts after Day 2 |

## 2 · Day-1 code dependencies (fast)

| ID | Service | Env vars | Dashboard | Notes |
| --- | --- | --- | --- | --- |
| D1 | Stripe test mode | `STRIPE_SECRET_KEY` (sk_test_…), `STRIPE_PUBLISHABLE_KEY` (pk_test_…), `STRIPE_WEBHOOK_SECRET` (whsec_…), `STRIPE_PRICE_*` lookup keys | dashboard.stripe.com | Products + Prices + Tax ON |
| D2 | Sentry | `SENTRY_DSN_BACKEND`, `SENTRY_DSN_FRONTEND` | sentry.io → New project | Free tier fine |
| D3 | UptimeRobot | n/a (external only) | uptimerobot.com | 50 free monitors |
| D4 | Status page | n/a | instatus.com or statuspal.io | Free tier |
| D5 | OpenRouter (fallback) | `OPENROUTER_API_KEY` | openrouter.ai | Allow-list specific free models only |
| D6 | Cloudflare R2 | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ACCOUNT_ID` | dash.cloudflare.com → R2 | 10 GB free |
| D7 | Fingerprint OSS (free) | n/a | fingerprintjs OSS | Free client lib; self-hosted optional |

## 3 · Post-launch (Day 5-7)

| ID | Service | Env vars | Notes |
| --- | --- | --- | --- |
| P1 | Slack app | `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` | OAuth app with `chat:write`, `incoming-webhook`, `commands` |
| P2 | Telegram bot | `TG_BOT_TOKEN` | @BotFather |
| P3 | HubSpot private app | `HUBSPOT_PRIVATE_APP_TOKEN` | per-customer |
| P4 | Google Sheets API | per-customer OAuth scope | — |
| P5 | Calendly | per-customer link only (no API first) | — |
| P6 | Shopify partner / dev store | `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET` | OAuth app, `read_products` scope |

## 4 · Developer-only / nice-to-have

| ID | Service | Notes |
| --- | --- | --- |
| N1 | GitHub Actions secrets for CI | all the above in `settings → Secrets → Actions` |
| N2 | Vercel OR owner's VPS | For prod deploy — VPS per docs/04 |
| N3 | Docker Hub / GHCR | Container registry |
| N4 | GlassFlow / Rius | Disabled per master prompt free-tier policy — do not enable |

## 5 · Complete `.env.example` (backend) — placeholder only

Already present at `backend/.env.example`. Add the following new lines (to be filled in PART 2):

```
# RAG v2
RERANKER_PROVIDER=cloudflare
RERANKER_MODEL=@cf/baai/bge-reranker-base
JINA_API_KEY=                # fallback reranker

# Provider router
OPENROUTER_API_KEY=

# Storage (Cloudflare R2)
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=knowmivo-prod-sources
R2_ACCOUNT_ID=

# Billing
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_TAX_ENABLED=true
STRIPE_PRICE_FREE=free
STRIPE_PRICE_STARTER_MONTHLY=starter_monthly
STRIPE_PRICE_STARTER_YEARLY=starter_yearly
STRIPE_PRICE_GROWTH_MONTHLY=growth_monthly
STRIPE_PRICE_GROWTH_YEARLY=growth_yearly
STRIPE_PRICE_SCALE_MONTHLY=scale_monthly
STRIPE_PRICE_SCALE_YEARLY=scale_yearly
STRIPE_PRICE_AGENCY_MONTHLY=agency_monthly
STRIPE_PRICE_AGENCY_YEARLY=agency_yearly
STRIPE_PRICE_OVERAGE_REPLY=overage_reply

# WhatsApp Cloud API
WA_BUSINESS_ACCOUNT_ID=
WA_PHONE_NUMBER_ID=
WA_ACCESS_TOKEN=
WA_WEBHOOK_VERIFY_TOKEN=

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_MESSAGING_SERVICE_SID=

# Slack app
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=

# Telegram
TG_BOT_TOKEN=

# Email (Postmark)
POSTMARK_SERVER_TOKEN=

# Observability
SENTRY_DSN_BACKEND=
SENTRY_DSN_FRONTEND=

# Transactional email
TRANSACTIONAL_FROM="Knowmivo <no-reply@knowmivo.com>"
LEGAL_COMPANY_ADDRESS=
```

## 6 · First 60 minutes checklist (what unblocks the most work)

1. Register `knowmivo.com` + point DNS to the VPS (LL7, LL8). ← enables TLS, enables SPF/DKIM/DMARC chain.
2. Start Meta Business Verification (LL1). Submit docs. Cannot code around this wait.
3. Start Twilio 10DLC (LL4). Same reason.
4. Open Stripe Tax registration in home state (LL5).
5. Create Postmark account + verify domain (LL6). Transactional email is used from Day 1 (verification + reset) — swap SMTP Gmail out for Postmark DKIM immediately.
6. Create Sentry projects (D2) and paste DSNs into the env files.
7. Create Cloudflare R2 bucket (D6) + access key.
8. Create OpenRouter account (D5) + API key, allow-list two free models in dashboard.
9. Fix the three env issues from `00-BUILD-HEALTH.md` §2 (SMTP_HOST, AUTH_SECRET, remove GOOGLE_CLIENT_SECRET from frontend).
10. Commit `.env.example` updates from §5 above.
