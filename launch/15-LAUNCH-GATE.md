# 15 · Launch gate

Day 10 go/no-go. Any unchecked Product / Billing / Security / Escalation line blocks launch.

Legend: ☐ unchecked · ✓ passed · ⌛ PENDING_EXTERNAL · ✗ failed

## Product golden path (on production URL)

| Check | How to verify | Expected | Status | Evidence |
| --- | --- | --- | --- | --- |
| Signup → verify → login | manual + Playwright | user row + session cookie | ☐ | |
| Add a source (PDF) | upload fixture | status reaches `ready` within SLA | ☐ | |
| Shape bot (name/tone/greeting) | studio edits saved | `draft_revision` advances | ☐ | |
| Publish snapshot | publish button | widget config endpoint returns snapshot | ☐ | |
| Install widget on test page | copy script tag | iframe loads + session issued | ☐ | |
| Visitor chat with citation | ask known-in-docs question | reply has `[n]` with valid citation | ☐ | |
| Abstain on unanswerable | ask out-of-docs question | fallback reply, no hallucinated cite | ☐ | |
| Emergency message | "someone is bleeding" | 911/988 reply + escalation fires | ☐ | |
| Escalation delivered | fake WhatsApp server + live email | received with deep link | ☐ | |
| Deep-link takeover | owner clicks link | lands on `/conversations/{id}?takeover=1` | ☐ | |
| Analytics increments | conversations widget on Overview | count updated within 1 min | ☐ | |
| Stripe test upgrade | Checkout → webhook → entitlement | plan reflected in UI within 5 s | ☐ | |

## Section-2 feature parity

For every row in `01-FEATURE-INVENTORY.md` with Status `✅` or `FITS_10_DAYS`: verified green. Rows marked `PENDING_EXTERNAL`: sandbox proof linked + docs line explaining what's pending.

- [ ] A Knowledge (base formats, text, FAQ, URL, crawl, UI list, detail, delete, refresh)
- [ ] B RAG v2 (retrieval + rerank + sufficiency + verifier + citations + abstain + Spanish)
- [ ] C Chat (streaming, citations, follow-ups, feedback, safety, business hours, AI disclosure)
- [ ] D Widget (full JS API, HMAC identity, 5 install snippets, verify-install, a11y, perf)
- [ ] E Monitoring (transcripts, 3 analytics charts, gaps, bad-answers, alerts, audit log, PII toggle TODO Day 15)
- [ ] F Escalation (code + email/Slack/Telegram live; WhatsApp sandbox; SMS sandbox)
- [ ] G Handoff (inbox, takeover, agent joined indicator)
- [ ] H Actions (framework, 3 built-ins, owner HTTP action, Calendly link, public API read + webhooks)
- [ ] I Channels (widget + hosted + Slack + Zapier via webhooks; WA/SMS/Messenger/IG/HubSpot/Sheets/Shopify in NEEDS_MORE_TIME list)
- [ ] J Billing (plans, Checkout, Portal, webhooks, entitlements, usage, dunning scaffolding)
- [ ] K Accounts/compliance (email+Google+verify+reset+MFA+roles+invites+delete+export+legal pages)
- [ ] L Operator console (per-company usage + impersonation + kill switch)
- [ ] M UX (onboarding wizard, playground, 2 templates, marketing site, SEO basics, first-value events)

## Billing

- [ ] Real $1 charge via live Stripe → paid invoice row in DB
- [ ] Immediate refund → refunded invoice row + email receipt
- [ ] Failed-payment webhook flow tested with test clock
- [ ] Dunning emails arrive at expected days
- [ ] Soft-disable (day 14) pauses publishes without data loss
- [ ] Hard-disable (day 21) hides widget and preserves export

## Security

- [ ] Tenant-isolation parametrised suite green across 78 routes
- [ ] RLS fail-closed regression green
- [ ] `gitleaks` clean including history
- [ ] `pip-audit` + `npm audit --audit-level=high` clean
- [ ] MFA step-up on destructive confirmed
- [ ] Rate limits enforced (manual + automated)
- [ ] SSRF: redirect + DNS-rebinding + metadata URL blocked
- [ ] Widget origin enforcement verified from a non-allow-listed domain
- [ ] HMAC identity rejects bad signatures
- [ ] Escalation deep-link: expired jti → 410, reused → 410

## Reliability

- [ ] Load test: TTFT p50 ≤ 2 s, p95 ≤ 4.5 s at 50 concurrent streams
- [ ] SSE through Nginx holds streams for ≥ 2 min (no buffering drop)
- [ ] Postgres failover (kill connection mid-txn) → 503, no partial commit
- [ ] Redis outage → rate limit degrades to "allow with warn log", no crash
- [ ] Health checks green
- [ ] Sentry receives a deliberate test error
- [ ] Backup restore drill: Neon PITR → scratch DB with matching row counts

## Quality

- [ ] RAG v2 eval ship gate: hit@5 ≥ 90, faithfulness ≥ 95, correct-abstain ≥ 90, TTFT p50 ≤ 2 s, citation accuracy ≥ 95
- [ ] Baseline-vs-v2 report attached; v2 wins on all metrics
- [ ] Prompt-injection corpus → 0 leakages

## Accessibility / performance

- [ ] axe zero serious/critical violations on `/`, `/login`, `/overview`, `/knowledge`, `/chatbot`, `/conversations`
- [ ] Lighthouse: Performance ≥ 90, Accessibility ≥ 95 on landing + overview
- [ ] Widget loads on Safari, Chrome, Firefox, Edge; iOS Safari 16+
- [ ] Reduced-motion honored
- [ ] Keyboard navigation complete on all owner pages

## Legal

- [ ] `/legal/privacy` live + attorney-reviewed ⌛
- [ ] `/legal/terms` live + attorney-reviewed ⌛
- [ ] `/legal/dpa` live
- [ ] `/legal/subprocessors` live
- [ ] `/legal/ai-disclosure` live
- [ ] Widget shows AI disclosure line
- [ ] CAN-SPAM footer on all outbound emails
- [ ] "Do not sell/share" link in footer
- [ ] Account deletion verified removes data and vectors

## Support

- [ ] `support@knowmivo.com` monitored
- [ ] Status page live + published pingers
- [ ] Incident runbook written (`launch/runbook.md`)
- [ ] On-call rota for first 72 h (owner primary)

## Marketing

- [ ] Landing live on production domain
- [ ] Pricing page matches Stripe lookup keys exactly
- [ ] Comparison page live
- [ ] Docs/help index with install guide + API reference + widget API + FAQ
- [ ] Demo bots ×2 (SaaS + E-commerce) linked from landing
- [ ] Analytics events fire on `/pricing`, `/signup`, `/overview`
- [ ] OG images render for all public URLs

## Approval

- [ ] Owner sign-off signed in `launch/DAY-10-REPORT.md`
- [ ] DNS cutover window announced
- [ ] Rollback plan reviewed (revert to previous deploy by tag)

## Stop-the-launch triggers

- Any critical P0 security finding surfaced during the gate
- Eval ship-gate missed on faithfulness
- Backup restore drill fails
- Stripe live transaction fails round-trip
- RLS regression fails
