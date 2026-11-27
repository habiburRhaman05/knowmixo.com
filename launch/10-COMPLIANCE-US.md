# 10 · US compliance — work product (not legal advice; attorney review required)

All paragraphs here are drafting guidance; every page gets the stamp "Draft — pending counsel review" until sign-off.

## 1 · Pages to ship

| Path | Short outline |
| --- | --- |
| `/legal/privacy` | What we collect (account email, company/bot content, visitor messages, cookies), why, lawful bases (contract, legitimate interest), retention per plan, third parties (`subprocessors`), CA+VA+CO rights, children (>13), contact |
| `/legal/terms` | Acceptable use, SLA, indemnity for customer data, AI-generated output disclaimer, warranty disclaimer, governing law (home-state), arbitration opt-out, termination |
| `/legal/dpa` | Our role is Processor; the business is Controller; subprocessor list; SCCs for EU transfers (not primary market but add); cross-border; security measures |
| `/legal/subprocessors` | Table of vendors + purpose + region: Neon (DB, US), Upstash (Redis, US), Pinecone (vector, US — will be removed per ADR 001), Cloudflare (CDN, embeddings, R2 — US/global), Groq (LLM, US), OpenRouter (fallback, US), Stripe (billing, US), Meta (WA, US/EU), Twilio (SMS, US), Slack, Postmark/Resend (email) |
| `/legal/ai-disclosure` | We use AI to generate replies. We ground them in your sources. We are not a substitute for professional advice. For medical or safety, call a licensed professional / 911 / 988 |
| `/legal/cookies` | Essential (session), analytics (opt-in per CCPA/CPRA), no marketing cookies on landing |

## 2 · CCPA / CPRA — DSR flow

- "Do not sell/share my info" link on every page footer (even though we don't sell).
- `/legal/dsr` with form: Export, Delete, Correct, Opt-out of profiling.
- Backend: queue job, 45-day legal max; email receipt. Reuse `GET /me/export` + `DELETE /me` under the hood.
- Operator console shows open requests + due dates.

## 3 · AI disclosure (K.14)

- Widget header subtitle default: "Replies are AI-generated and cite our docs."
- Owner can edit text but not disable the disclosure.
- Marketing copy explicitly says "AI assistant" — never "virtual agent" without the AI qualifier.

## 4 · CAN-SPAM

- Every transactional + marketing email has:
  - Physical mailing address in the footer
  - "Unsubscribe" link for non-essential emails (digest, marketing)
  - No deceptive subject lines
- Transactional emails (verification, reset, receipts) exempt from unsubscribe but still show the physical address.

## 5 · TCPA (US SMS)

- We only send SMS to verified, opted-in owners (escalation). Never to visitors unless the owner forwards an SMS channel.
- `STOP` keyword unsubscribes; recorded in `escalation_contacts.active=false`.
- Carrier content guidelines: no SHAFT content (sex, hate, alcohol, firearms, tobacco) in any default template.
- 10DLC campaign registration required before go-live (PENDING_EXTERNAL).

## 6 · COPPA

- Not for children under 13. Terms say so plainly.
- Signup page: self-attestation checkbox "I am 18 years of age or older".

## 7 · HIPAA

- We are **not** HIPAA-compliant.
- Terms: "Do not submit PHI (patient health information) through Knowmivo."
- Healthcare template includes a warning banner before any chat starts.
- No signed BAA offered.

## 8 · Data residency

- All data in US-East (Neon, Pinecone/pgvector, Upstash, R2, Cloudflare).
- Terms: "Data stored in the US. EU users accept transfer under SCCs."
- Workload migration to EU region is an Agency-plan upgrade conversation; not launching with it.

## 9 · Retention (ADR 009 summary)

| Plan | Conversation retention | Audit log | Invoices |
| --- | --- | --- | --- |
| Free | 30 d | 30 d | 1 y |
| Starter | 30 d | 1 y | 7 y |
| Growth | 90 d | 1 y | 7 y |
| Scale | 1 y | 2 y | 7 y |
| Agency | 2 y | 2 y | 7 y |

Owner can set shorter retention than their plan's maximum.

## 10 · Subprocessor change notice

30-day email notice to affected customers before adding a new subprocessor. Easy because subprocessors page is markdown; CI commit triggers an email cron task.

## 11 · Incident response

- Breach notice within 72 h to affected customers (contractual, not necessarily statutory).
- Status page updated at `/status` within 15 min of a P0.
- Incident runbook in `launch/13-SPRINT-10-DAYS.md` — Day 10 writes it.
