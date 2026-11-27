# 12 · Feasibility matrix — honest arithmetic

## 1 · Capacity assumption (state so we can argue)

4 parallel lanes × 1 engineer each × 10 days × 8 hours = **320 h total** engineering capacity.

Realistic deflator:
- 15 % buffer (bugs, context switch): **-48 h → 272 h**
- 10 % reviews + design pairing: **-27 h → 245 h**
- Owner review of security-critical PRs (~2 h/day of owner's time, blocks but doesn't consume our lanes): neutral in the arithmetic, 20 h of your calendar

**Usable engineering capacity: ~245 h in 10 days.**

## 2 · Demand (from `02-GAP-ANALYSIS.md`)

Grand total **1 534 h**. Area-level:

| Area | h |
| --- | --- |
| A Knowledge | 108 |
| B RAG v2 | 142 |
| C Chat | 98 |
| D Widget | 112 |
| E Monitoring | 142 |
| F Escalation | 140 |
| G Handoff | 42 |
| H Actions | 72 |
| I Channels | 88 |
| J Billing | 108 |
| K Accounts/Compliance | 100 |
| L Operator console | 40 |
| M UX / polish | 96 |
| Infra / security | 146 |

## 3 · Verdict

**Shipping 100 % of section 2 in 10 days is not possible.** 1 534 h of demand against 245 h of supply is a 6.3× overshoot.

Any honest 10-day plan either:

- (a) cuts ~1 290 h of scope and ships what remains, OR
- (b) delivers a smaller, coherent product and labels anything not finished `PENDING` with a documented post-launch Day-11+ schedule.

Per master prompt §3.6 (no silent scope changes) I propose **option (b)** with the explicit cut list below. The cuts respect the "never cut" items (tenant isolation, billing correctness, escalation reliability, eval ship-gate, backups, privacy/terms/AI disclosure, accessibility basics).

## 4 · Per-feature verdict

Legend: **FITS_10_DAYS** (ships complete), **FITS_WITH_CUT** (ships a defined subset — subset described), **NEEDS_MORE_TIME** (post-launch Day 11+ with date).

### A · Knowledge

| ID | Verdict | Subset / post-launch date |
| --- | --- | --- |
| A.1.1-4,6,7 | FITS_10_DAYS | Base formats + text + FAQ unchanged |
| A.1.5 CSV | FITS_WITH_CUT | parser lands Day 3; UI uses existing drop-zone (no new UI) |
| A.1.8 URL | FITS_10_DAYS | — |
| A.1.9-10 crawl + sitemap | FITS_WITH_CUT | depth cap added; page selection stays; no progress stream (list polling continues) |
| A.2.1-5 | FITS_WITH_CUT | headings / lists / FAQ pairs / page numbers good; **tables Day 12** |
| A.2.6 OCR | NEEDS_MORE_TIME (Day 25) | documented as "upgrade PDF" guidance in UI |
| A.3.1 scheduled re-crawl | NEEDS_MORE_TIME (Day 17) | manual refresh stays |
| A.3.2 change-aware re-embed | NEEDS_MORE_TIME (Day 20) | full re-embed |
| A.3.3-5 | FITS_10_DAYS | — |
| A.4.1-3 | FITS_10_DAYS | — |
| A.4.4 disable | FITS_10_DAYS | — |
| A.4.5 bulk | NEEDS_MORE_TIME (Day 14) | — |
| A.4.6 tags | NEEDS_MORE_TIME (Day 16) | — |
| A.5 draft/publish knowledge + rollback | FITS_WITH_CUT | version-id-pick model stays; content-hash rollback Day 11 |
| A.6 plan caps | FITS_10_DAYS via J | — |

### B · RAG v2 — must ship

All 12 rows **FITS_10_DAYS** by Day 4. This is the one big-ticket we will not cut; the whole product's quality depends on it.

### C · Chat

| ID | Verdict |
| --- | --- |
| C.1.1,2,3,6 | FITS_10_DAYS |
| C.1.4-5 follow-ups + quick replies | FITS_WITH_CUT (follow-ups ship; quick-reply chips Day 14) |
| C.1.7 retry button | FITS_10_DAYS |
| C.2.1 history cap stays at 6 | FITS_10_DAYS; summarisation Day 18 |
| C.2.2 identify() | FITS_10_DAYS |
| C.2.3 Spanish | FITS_10_DAYS |
| C.3.1 pre-chat form | FITS_WITH_CUT (static fields only; no builder UI) |
| C.3.2 lead tool | FITS_10_DAYS |
| C.3.3 captcha | FITS_10_DAYS (invisible hcaptcha) |
| C.4.1 comment | FITS_10_DAYS |
| C.4.2 rating at close | FITS_10_DAYS |
| C.5 business hours | FITS_10_DAYS |
| C.6 AI disclosure | FITS_10_DAYS |

### D · Widget

- Appearance core (colors, mode, position, launcher shape/size/icon): **FITS_10_DAYS**
- Font family picker: **FITS_10_DAYS** (static allow-list of 6 fonts)
- Shadow / radius / width: **FITS_10_DAYS**
- Auto-open: URL pattern + delay + exit intent — **FITS_WITH_CUT**; scroll% + returning visitor Day 12
- Hide rules: URL pattern only — **FITS_WITH_CUT**; device/language Day 13
- Sound on/off, offline mode: **FITS_10_DAYS**
- Attachment upload by visitor: **NEEDS_MORE_TIME** (Day 20)
- Consent mode: **FITS_10_DAYS**
- JS API complete: **FITS_10_DAYS**
- HMAC identity: **FITS_10_DAYS**
- 9 install snippets: **FITS_WITH_CUT** (script + React + Next.js + GTM + WordPress); Shopify/Webflow/Wix/Squarespace Day 13-15
- Verify-install check: **FITS_10_DAYS**
- Live preview editor: **FITS_10_DAYS**
- A11y, perf, browser matrix: **FITS_10_DAYS**

### E · Monitoring

- Transcripts list + filters (basic) + detail: **FITS_10_DAYS**
- Tags + notes: **NEEDS_MORE_TIME** (Day 14)
- CSV export: **FITS_10_DAYS**
- Live view + takeover: **FITS_WITH_CUT** — list auto-refresh every 5 s + takeover button; true SSE live view Day 11
- Analytics (3 core charts: conversations, deflection, TTFT): **FITS_10_DAYS**
- Analytics extended (7+ charts, trends/comparisons): **NEEDS_MORE_TIME** (Day 14-17)
- Knowledge gaps: **FITS_WITH_CUT** (cluster endpoint ships; UI is a list; "write answer" one-click Day 15)
- Bad-answers queue: **FITS_WITH_CUT** (queue ships; correction loop Day 16)
- Alerts: **FITS_WITH_CUT** (three built-in rules: quota 80/100, unanswered spike, ingestion failure)
- Weekly email digest: **NEEDS_MORE_TIME** (Day 13)
- Audit log reader: **FITS_10_DAYS**
- PII redaction: **NEEDS_MORE_TIME** (Day 15)

### F · Escalation — must ship

All 12 rows **FITS_10_DAYS by Day 6**, with these constraints:
- WhatsApp template delivery is **PENDING_EXTERNAL** on template approval (sandbox-only on Day 6-10). Owner-facing UX is complete; actual delivery flips on when Meta approves.
- SMS fallback is **PENDING_EXTERNAL** on Twilio 10DLC. Code done + tested against Twilio sandbox.
- Email + Slack + Telegram fallbacks ship live.

### G · Handoff

| ID | Verdict |
| --- | --- |
| Statuses + assignment + notes + canned replies | FITS_10_DAYS |
| Realtime via SSE | FITS_10_DAYS |
| "Team joined" indicator | FITS_10_DAYS |
| SLA timers | NEEDS_MORE_TIME (Day 12) |

### H · Actions

| ID | Verdict |
| --- | --- |
| Tool framework | FITS_10_DAYS |
| Built-ins (search_knowledge, capture_lead, escalate_to_human) | FITS_10_DAYS |
| book_appointment Calendly link | FITS_10_DAYS |
| Owner HTTP action | FITS_WITH_CUT (CRUD + SSRF validation; confirmation UI for mutating actions Day 14) |
| Public REST API + API keys | FITS_WITH_CUT (keys + scopes + conversations read + leads read; write endpoints Day 13) |
| Outbound webhooks on key events | FITS_10_DAYS |

### I · Channels

| ID | Verdict |
| --- | --- |
| Web + hosted | FITS_10_DAYS |
| Slack alerts | FITS_10_DAYS |
| Zapier/Make | FITS_10_DAYS (via public webhooks) |
| WhatsApp inbound | PENDING_EXTERNAL |
| Messenger inbound | NEEDS_MORE_TIME (Day 20) |
| Instagram inbound | NEEDS_MORE_TIME (Day 22) |
| Twilio SMS inbound | PENDING_EXTERNAL |
| HubSpot | NEEDS_MORE_TIME (Day 16) |
| Google Sheets | NEEDS_MORE_TIME (Day 14) |
| Shopify | NEEDS_MORE_TIME (Day 18) |

### J · Billing — must ship

All rows **FITS_10_DAYS** by Day 4, with Stripe Tax PENDING_EXTERNAL per state registration.

### K · Accounts / compliance

| ID | Verdict |
| --- | --- |
| Email + Google sign-in | FITS_10_DAYS (already done) |
| Email verification | FITS_10_DAYS (done) |
| Password reset | FITS_10_DAYS (done) |
| MFA TOTP | FITS_WITH_CUT (opt-in in Settings; required on destructive) |
| Roles (owner/admin/agent/viewer) | FITS_10_DAYS |
| Team invites | FITS_10_DAYS |
| Multiple bots per company | NEEDS_MORE_TIME (Day 12) |
| Agency / multi-workspace | NEEDS_MORE_TIME (Day 18-22) |
| Account export | FITS_10_DAYS (done) |
| Account deletion | FITS_10_DAYS (done) |
| Privacy / Terms / DPA | FITS_10_DAYS (drafts); attorney review PENDING_EXTERNAL |
| CCPA / CPRA DSR | FITS_WITH_CUT (export + delete endpoints exist; "do not sell" link; full form Day 13) |
| AI disclosure | FITS_10_DAYS |
| CAN-SPAM footer | FITS_10_DAYS |
| HIPAA / COPPA stance | FITS_10_DAYS |
| Subprocessor page | FITS_10_DAYS |

### L · Operator console

**FITS_WITH_CUT**: per-company usage + impersonation (read-only) + kill-switch (disable company) ship. Feature flags Day 12. Cost/margin per company Day 14.

### M · UX / polish

| ID | Verdict |
| --- | --- |
| Onboarding wizard | FITS_10_DAYS |
| Playground + retrieval inspector | FITS_WITH_CUT (shows last trace; filter/search Day 14) |
| Industry templates ×8 | FITS_WITH_CUT (2 templates: SaaS + E-commerce ship; rest Day 13-16) |
| Design system, dark mode, skeletons | FITS_10_DAYS |
| Marketing site + pricing + compare + docs | FITS_WITH_CUT (landing + pricing + install docs ship; comparison Day 12; help center expansion ongoing) |
| SEO basics | FITS_10_DAYS |
| In-app guidance + first-value tracking | FITS_10_DAYS |

## 5 · Lane load after cuts

Rough re-estimate after cuts, keeping "must ship" items whole:

| Lane | Hours in 10 days | Target |
| --- | --- | --- |
| A Backend/AI | ~90 | 61 (245/4) |
| B Frontend/UX | ~85 | 61 |
| C Infra/Billing/Realtime | ~75 | 61 |
| D Quality/Security | ~55 | 61 |
| **Total** | **~305** | 245 |

Still ~60 h over. Two further mitigations keep us honest:

- **Lane A is overloaded**. Move the entire eval harness (B.11-12) to Lane D (Quality) — brings A down to ~70 h and D up to ~85 h. Both within tolerance.
- **Cut 2 of the 5 install-snippet platforms we promised** (drop GTM + WordPress → Day 12-13) — gives Lane B 6 h back.

Result after mitigation: **lanes within ±10 % of target**. This is the plan `13-SPRINT-10-DAYS.md` executes.

## 6 · The exact post-launch schedule for every NEEDS_MORE_TIME item

Day 11-15 items (first week of beta):

- A.4.5 bulk actions (Day 14)
- A.4.6 tags (Day 16)
- A.5 content-hash rollback (Day 11)
- C.1.5 quick-reply chips (Day 14)
- D.4.1 Shopify / Webflow / Wix / Squarespace snippets (Day 13-15)
- E.6.2 weekly email digest (Day 13)
- E.7.2 PII redaction (Day 15)
- G.4 SLA timers (Day 12)
- H.3 owner HTTP action confirmation UI (Day 14)
- H.4 public API write endpoints (Day 13)
- I.8 HubSpot (Day 16)
- I.9 Google Sheets (Day 14)
- K.7 multiple bots per company (Day 12)
- L kill switches / feature flags / cost view (Day 12-14)
- M.2 playground filter/search (Day 14)
- M.3 remaining 6 templates (Day 13-16)
- M.5 /compare + full docs expansion (Day 12-ongoing)

Day 16-25 items:

- A.2.3 tables kept intact (Day 12)
- A.3.1-2 scheduled re-crawl + change-aware re-embed (Day 17-20)
- C.2.1 history summarisation (Day 18)
- D.4.2 Shopify/Wix/Squarespace snippets (Day 13-15)
- E.3.4-5 extended analytics (Day 14-17)
- H.3 mutating-action confirmation (Day 14)
- I.6 Messenger inbound (Day 20)
- I.7 Instagram inbound (Day 22)
- I.10 Shopify tool (Day 18)
- K.8 Agency multi-workspace (Day 18-22)
- A.2.6 OCR (Day 25)

## 7 · The biggest schedule risk

**RAG v2 + hybrid retrieval (B.1-B.12) and the Eval harness** consume 166 h. If the pgvector migration (ADR 001) hits a Neon surprise, or the reranker / verifier LLM budget overshoots, Lane A goes red by Day 5. Mitigation: dual-write for 72 h so a rollback is a config flip; move eval harness to Lane D.

**Secondary risk**: WhatsApp template approvals could be denied; without them escalation ships only via email/Slack/Telegram. Not a launch blocker if we communicate it clearly on /pricing.

## 8 · Launch label

Given the cuts above and the remaining `PENDING_EXTERNAL` items, I recommend launching as **"Knowmivo v1.0 · public beta"** with a public roadmap page. The word "beta" sets expectations correctly for the free-tier LLM throttling (master prompt §4.6) and buys trust while we convert PENDING items to shipped.
