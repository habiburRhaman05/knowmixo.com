# Product requirements

## Outcome

A company owner signs up, supplies documents or public website content, configures a chatbot, previews it, and installs one script on their website. Website visitors receive grounded answers from that company's published knowledge base.

## Actors

Owner manages their company, sources, bot and conversations. Visitor uses a published bot without an owner account. Operator maintains infrastructure and investigates failed jobs through authenticated tooling.

## Owner journey

Register or use Google → verify email where required → create company → upload files or import website pages → monitor processing → customize instructions and branding → test draft preview → publish → copy widget code → inspect conversations and feedback.

## V1 functional scope

| ID | Capability | Included behavior |
| --- | --- | --- |
| A | Authentication | Email/password registration and login, Google login, email verification and resend, forgot/reset/change password, logout and logout all sessions, safe account linking |
| B | Profile and company | Name, avatar, company name, industry, website, logo, contact details, verified email changes, account deletion and data export |
| C | Dashboard | Setup checklist, source counts and processing states, conversations, message usage and quota warnings |
| D | Sources | Multiple PDF/DOCX/TXT/MD uploads, pasted text, manual FAQs, public URL import, capped same-domain crawl and sitemap page selection |
| E | Source management | Extracted text preview, title changes, replacement, manual refresh, removal, per-stage progress, error details and manual retry |
| F | Bot behavior | Owner instructions, templates, tone, English/Bangla or visitor-language response, fallback answer, bounded chat history and citation toggle |
| G | Branding | Name, subtitle, icon/logo, theme color, left/right placement, custom greeting, suggested questions, optional skippable name/email lead capture |
| H | Preview and publishing | Owner-only draft preview, explicit publish/republish, unpublish, published configuration snapshot and selected ready sources |
| I | Distribution | Copyable script, HTML/React/Next.js instructions, responsive iframe widget, hosted chat link and allowed website domains |
| J | Visitor chat | Streamed answers, stop generation, reset conversation, source citations, feedback, unavailable and no-evidence states |
| K | Conversations | List/filter, transcript, completion/error/interruption states, lead details, source references, export and deletion |
| L | Reliability and security | Tenant isolation, durable job state, bounded retries, dead jobs, safe replay, quotas, rate limits, audit logs and backup/restore |

Greeting templates are deterministic editable presets. Automatic AI copywriting is optional only if it uses the same explicit free quota and does not delay core delivery.

## Limits and exclusions

Initial product limits are configurable defaults rather than provider entitlements. Start with 10 MiB per file, 10 sources per company, 20 pages per crawl, 1 MiB extracted HTML text per page and 100 MiB stored files per company. Measure and revise before public launch. Global model quotas override all product quotas.

No subscriptions, checkout, invoices or payment integration. No authenticated/private-site crawling, image OCR, audio/video ingestion, automatic scheduled recrawl, human support inbox, native mobile SDK or LLM-driven destructive actions. Scanned PDFs show a clear unsupported-file message rather than becoming an empty ready source.

## Success and launch

An owner can complete onboarding and embed a working bot without operator intervention. No cross-company or unpublished-source disclosure is acceptable. English and Bangla evaluation questions must pass the test corpus. Quota exhaustion must never silently trigger a paid provider. Measure setup completion, source success rate, answer feedback, no-evidence frequency and time to first streamed text without promising a latency SLA on free tiers.

Public commercial use depends on current provider terms and available account quotas. Initially launch as a capacity-limited beta with a registration cap. No payment collection does not remove provider capacity limits.
