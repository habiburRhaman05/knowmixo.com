# 08 · UX specification

Pairs with the master prompt §M and the UX audit in `01-FEATURE-INVENTORY.md`.

## 1 · Information architecture

```
Public
├── /              Landing (hero + feature grid + pricing teaser)
├── /pricing       Pricing grid (matches Stripe lookup_keys)
├── /compare       vs. competitors
├── /docs          Markdown docs — install / API / widget / FAQ
├── /blog          Markdown blog (SEO)
├── /legal
│   ├── /privacy
│   ├── /terms
│   ├── /dpa
│   ├── /subprocessors
│   └── /ai-disclosure
├── /chat/{publicId}      Hosted chat page
├── /widget/{publicId}    Iframe content
├── /embed.js             Loader
└── /status               Link out to Instatus/statuspal

Auth (public)
├── /login
├── /signup
├── /verify-email
├── /forgot-password
└── /reset-password

Owner dashboard
├── /overview             ← first screen after login
├── /onboarding           Wizard (3-min target)
├── /knowledge
│   ├── /                 Sources list
│   └── /{id}             Source detail (drawer today; promote to page in F6)
├── /chatbot
│   ├── /                 Studio
│   ├── /publish          Publish + install
│   └── /playground       Retrieval inspector (NEW — section M.2)
├── /conversations
│   ├── /                 List
│   ├── /inbox            Live inbox (NEW — section G)
│   └── /{id}             Transcript
├── /analytics            Trend charts (NEW — section E.3)
├── /gaps                 Knowledge gaps (NEW — section E.4)
├── /quality              Bad-answers queue (NEW — section E.5)
├── /alerts               Alert rules + delivery log (NEW)
├── /team                 Members + invites + roles (NEW — K)
├── /api-keys             Public API keys (NEW — H.4)
├── /actions              Owner HTTP tools (NEW — H)
├── /integrations         Slack/Shopify/HubSpot/Sheets/Zapier (NEW)
├── /escalation           Rules + contacts + log (NEW — F)
├── /billing              Plan + usage + invoices (NEW — J)
└── /settings             Profile / Company / Password / MFA (NEW) / Danger zone
```

## 2 · User flows

### 2.1 Onboarding (target: working bot in under 3 minutes)

```
Signup (email or Google)
  → verify (deep link in email)
  → wizard start
    step 1: Workspace name + website URL
    step 2: Paste URL → auto-crawl discovery → user picks pages → import (fire & forget)
    step 3: Pick tone + greeting + brand color (preset chips, not open-ended)
    step 4: Test chat against the still-processing bot (uses whatever is ready)
    step 5: Copy install snippet + "verify installation" live indicator
  → overview
```

Each step is one card, full-page, with a back button. Progress meter at top. Save on every blur.

### 2.2 First widget install verification

Owner pastes snippet on their site → first visitor loads the iframe → backend writes a `widget_install_pinged` event → owner dashboard shows green check + the URL where it was detected within 5 s via SSE.

### 2.3 Live handoff

Visitor says "I need a human" → intent stage flags `escalate` → event_outbox fires → WhatsApp/Slack delivered to owner with deep link → owner clicks → lands on `/conversations/{id}?takeover=1` → clicks Take over → `conversations.handoff_status='human'`, `conversations.agent_user_id=owner.id` → visitor's widget receives `agent_joined` SSE event → "A team member has joined" shown in transcript → human types → arrives at visitor via existing SSE delta channel.

### 2.4 Knowledge gap resolution

`/gaps` shows clusters of low-confidence questions → owner picks one → "Write the answer" opens FAQ editor prefilled with the question → save → source re-embeds → mark gap resolved.

## 3 · Design tokens (unchanged from recent polish)

| Token | Value |
| --- | --- |
| Primary | indigo `243 75% 59%` light / `243 85% 68%` dark |
| Font body | Inter |
| Font display | Plus Jakarta Sans |
| Base size | 16 px |
| Scale | 1.25 modular |
| Radius | 12 px |
| Grid | 8 px |
| Controls | 40 px h |
| Motion | 150 ms ease-out |
| Shadow card | `0 1px 2px / 0 1px 3px` light softly tinted |

## 4 · Component inventory (ownership)

Reused primitives already in the codebase:
- `Button`, `Input`, `Textarea`, `Field`, `Label`, `Card`, `Badge`, `Alert`, `Separator`, `Dialog`, `Dropdown`, `Toast`, `Tooltip`, `Avatar`, `Kbd`, `Progress`, `EmptyState`.

New primitives to add in PART 2:
- `Select` (styled select — current one is a bare `<select>`)
- `Combobox` (for template + tag + language pickers)
- `Switch` (currently inline)
- `Tabs` (currently ad-hoc)
- `Pagination` (cursor + prev/next)
- `DataTable` with filters/sort — reused in Conversations/Leads/Analytics
- `DateRangePicker` for analytics
- `ColorPicker` with contrast warning
- `ChartLine`, `ChartBar`, `ChartSparkArea` (Recharts under the hood)
- `CodeBlock` with copy button

Count: 10 new primitives, ~14 h total.

## 5 · Copy guidelines

- Second person ("your assistant") never "the bot".
- US English, short sentences; avoid "please" / "sorry" in nav labels.
- Errors: title (what happened) + message (what to do) + optional request_id link. No stack traces.
- Empty states always suggest the next best action.
- AI disclosure: "Replies are AI-generated and cite our docs."

## 6 · State rules (apply to every screen)

- **Loading**: skeleton only when data takes > 300 ms; spinners only for <300 ms background actions.
- **Empty**: illustration + headline + "Add first…" CTA; never a blank page.
- **Error**: `Alert tone=danger` with retry button and `request_id` in small text.
- **Unavailable** (e.g., bot unpublished): friendly banner with reason + fix link.
- **Success**: toast + optimistic UI; never a full-page refresh on save.

## 7 · Accessibility targets

- WCAG 2.1 AA.
- axe-core run on every page in CI; zero serious/critical violations required to merge.
- Lighthouse ≥ 90 performance + ≥ 95 accessibility on `/` and `/overview` shell.

## 8 · i18n

- Launch: US English (default), Spanish (strings tested in all public pages + widget).
- Framework: `next-intl` with JSON message files at `frontend/messages/{en,es}.json`.
- Day 9 audit: run the UI in Spanish; fix wrapping/truncation.

## 9 · Bundle budgets

- Each owner page ≤ 200 KB first-load JS.
- Shared chunks ≤ 110 KB (currently 100 KB — enforce ceiling in `next.config.mjs` via `webpack` plugin or check-only CI).
- Widget iframe page ≤ 150 KB.
- `embed.v1.js` ≤ 10 KB gz.

## 10 · First-value tracking (for M.7)

Fire `analytics_events` rows:
- `account.created`
- `source.first_added`
- `source.first_ready`
- `bot.first_configured`
- `bot.first_published`
- `widget.first_install_detected`
- `widget.first_visitor_message`

Dashboard / Overview surfaces time-to-first-value for the owner ("Your assistant was live in 4 min 12 s").

## 11 · Concrete fixes for the UX audit items in `01-FEATURE-INVENTORY.md`

| # | Fix |
| --- | --- |
| 1 | Add `app/(app)/loading.tsx` per-section (already added at root — extend to `/chatbot`, `/conversations`, `/knowledge`). Done. |
| 2 | Mobile sidebar slide-in via Radix Sheet; done Day 6 polish. |
| 3 | Toast viewport respects widget launcher position — add 80 px bottom offset when a widget is detected on the page. |
| 4 | Replace raw `error_code` text with `describeError(error).message`. |
| 5 | axe check + fix contrast on KPI value changes. |
| 6 | Title size scales via `text-[clamp(1.5rem,5vw,2rem)]`. |
| 7 | Studio preview: pin scroll bottom only when the user wasn't scrolled up at delta time. |
| 8 | Add "Publishing stops immediately" note in delete-account dialog. |
| 9 | Fade the verify-email banner for 1 s after `email_verified_at` flips. |
| 10 | Focus trap on command bar (use Radix Dialog underneath). |
