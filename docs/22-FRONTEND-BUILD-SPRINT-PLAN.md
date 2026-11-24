# Frontend build sprint plan

Basis: [07-UI-SPEC](07-UI-SPEC.md), [09-BUILD-PLAN](09-BUILD-PLAN.md) days 4-10, [15-USER-STORIES](15-USER-STORIES.md), the real API in `backend/openapi.yaml` ([21-BACKEND-COMPLETION-STATUS](21-BACKEND-COMPLETION-STATUS.md)). Stack per [04](04-STACK-AND-SERVICES.md): Next.js App Router, TypeScript, Tailwind, shadcn/ui, React Hook Form + Zod, TanStack Query, Playwright. Location: `/frontend` (sibling of `/backend`).

## Architecture decisions (locked before Sprint F1)

| Topic | Decision | Why |
| --- | --- | --- |
| API types | Generated from `backend/openapi.yaml` with `openapi-typescript`; CI fails on drift | Backend contract is generated, so types cannot lie |
| Session | Next.js BFF route handlers (`/api/bff/*`) proxy to FastAPI. Login stores the backend `session_token` in an httpOnly, Secure, SameSite=Lax cookie; BFF adds `Authorization: Bearer`. Browser JS never sees the token | Backend is Bearer-based; no token in JS or localStorage |
| Auth.js | Use only if the F0 spike shows it adds value over the plain cookie bridge for Google; otherwise skip (stack doc says resolve in the spike) | Avoid an untested major-version dependency |
| Google sign-in | Google Identity Services in the browser yields an `id_token`, posted to `POST /auth/google`; backend verifies independently | Matches the backend contract |
| Streaming | `fetch` + `ReadableStream` SSE parser (POST, so no `EventSource`) with `AbortController` for Stop; handles `meta/sources/delta/done/error`, `seq`, heartbeat comments | Matches the SSE contract |
| Widget | `embed.js` injects one sandboxed iframe from our domain; chat UI is a Next.js page; postMessage with origin checks; no owner credentials anywhere | UI spec "Preview and widget" |
| Public calls | Iframe page calls the BFF (same-origin), so no CORS needed | Backend has no CORS middleware |
| Idempotency | Client generates a UUID `Idempotency-Key` per user action (publish, refresh, retry, import, chat send) and reuses it on retry | Required by the API |
| Errors | One mapper keyed on `code` (never on `message`); `request_id` shown in "copy diagnostics" | Error codes are a stable enum |

## Backend changes the frontend needs (small, done in the same sprint they block)

| ID | Change | Blocks |
| --- | --- | --- |
| B-F1 | Embedded-origin handling: the iframe is served from our domain, so the backend `Origin` check would see our domain, not the customer's site. BFF forwards the parent origin (from `document.referrer`/`ancestorOrigins`) in a header the backend trusts only when it carries a BFF shared secret | F4 |
| B-F2 | Validate `draft_config` keys and bounds (name, tone, language, fallback_message, greeting, suggestions, branding color/position, citations toggle, instructions). Today it accepts any JSON | F3 |
| B-F3 | Logo/avatar upload endpoint with image decode and dimension limits (today only a `*_key` string can be stored) | F3, F5 |
| B-F4 | `GET /me` to also return `has_password` and `google_linked` for the Settings screen | F5 |
| B-F5 | Verification and reset emails link to frontend routes (`/verify-email?token=`, `/reset-password?token=`); make base URL come from `PUBLIC_APP_URL` | F1 |

## Sprint F0 - Setup and spikes (0.5 day) - blocked on backend environment

- Backend runnable locally: **needs a `.env` and a disposable Postgres (none found in the repo).**
- Scaffold `/frontend`, pin versions, shadcn/ui init, design tokens from the UI spec (indigo accent, 16px base, 8px grid, 12px radius, 40px controls).
- Generate API types; build the BFF proxy and cookie session; SSE parser with unit tests.
- Spike: Auth.js yes/no; Google id_token round trip.
- **Gate:** sign up, verify, log in through the BFF, and `GET /me` renders; SSE parser passes fixtures from the backend's real event shapes.

## Sprint F1 - Foundation, auth, onboarding shell (build-plan day 4)

- App shell: public layout, owner layout with sidebar (Overview, Knowledge, Chatbot, Conversations, Usage, Settings). No company switcher, no dead links.
- Auth screens: login, signup, verify-email, resend (with cooldown), forgot/reset password, Google button, verification banner.
- Route protection (middleware) and logout / logout-all.
- Overview: setup checklist, source counts by state, conversations, usage summary (`GET /dashboard`, `/usage`).
- Onboarding stepper skeleton with saved progress (company -> source -> appearance -> preview -> publish).
- Shared states kit: loading, empty, error, unavailable; status badges always with text.
- **APIs:** `/auth/*`, `/me`, `/company`, `/dashboard`, `/usage`. **Backend:** B-F5.
- **Gate (Playwright):** full signup-verify-login-logout; unauthenticated access redirects; unverified user sees the banner and gets the right 403 handling; cross-user data never shown after account switch; axe checks clean; 360px layout.

## Sprint F2 - Knowledge (build-plan day 5, part 1)

- Knowledge list: drop zone, Add website / Text / FAQ, search, type/state filters, cursor pagination, status badges with the real stage names (Uploading, Queued, Extracting, Chunking, Embedding, Indexing, Ready, Retrying, Quota paused, Failed), retry and delete with confirm.
- Upload flow: grant -> `PUT /uploads/{grant}` with size/type pre-checks -> `complete` (idempotent).
- Text and FAQ editors (FAQ repeater with Zod limits matching the backend).
- Website import: single URL, crawl discover -> poll `crawl-jobs/{id}` -> select pages -> import. SSRF and failure codes shown in plain language.
- Source details: extracted-text preview with pages/headings, current vs pending version, refresh, rename, delete.
- Job polling hook with backoff; honest states only (no fake percentages).
- **APIs:** `/documents*`, `/sources/*`, `/crawl-jobs/*`, `/jobs/*`.
- **Gate:** each failure fixture (unsupported file, too large, scanned PDF, SSRF-blocked URL, quota paused) renders its own message from `error_code`; retry is idempotent on double click; deleting a source updates every view.

## Sprint F3 - Bot studio and draft preview (build-plan day 5, part 2)

- Behavior: instructions editor, template selector, tone, language, fallback message, citation toggle, suggested questions.
- Appearance: name, subtitle, logo, color, position, greeting, lead-form field toggles (`/bot/lead-form`).
- Two-column layout with sticky live preview (stacks on mobile), clearly labelled Draft.
- Draft saving with `draft_revision` optimistic concurrency: on 409, show "changed elsewhere" with reload and keep the user's edits.
- Preview chat uses the real pipeline (`/bot/preview/conversations`, `/bot/preview/chat`) via the shared chat component.
- **APIs:** `/bot`, `/bot/lead-form*`, `/bot/preview/*`. **Backend:** B-F2, B-F3.
- **Gate:** concurrent-edit conflict test; preview answers cite only ready sources; no hardcoded mock answers.

## Sprint F4 - Publish, install, widget, hosted chat (build-plan day 6, part 1)

- Publish page: pick ready source versions, unpublished-changes indicator, publish (idempotent), unpublish, domain allowlist editor with validation.
- Install page: copy script / React / Next.js snippets and hosted link from `/bot/embed`.
- Shared chat component: streaming, typing indicator, Stop, no duplicate sends, retry, sources panel, safe Markdown (sanitized, no model HTML), scroll preservation, skippable lead capture, thumbs feedback.
- `embed.js` + iframe page + postMessage protocol (open, close, resize) with origin validation; hosted full-page chat.
- States: unpublished, quota exhausted (no provider details), origin not allowed.
- **APIs:** `/bot/publish|unpublish|domains|embed`, `/public/*`. **Backend:** B-F1.
- **Gate:** HTML, React and Next.js fixture host pages load the widget; network inspection asserts no owner token or secret in any request; allowed and disallowed origins behave correctly; abort mid-stream leaves a coherent transcript.

## Sprint F5 - Conversations, usage, settings (build-plan day 6, part 2)

- Conversations: filters (date, status, feedback), cursor list, transcript with citations and lead panel, export, delete.
- Usage: allowance warning, today's use, next reset, quota-wait explanation. No billing or upgrade UI.
- Settings: profile, company, password change, email verification, Google link, sign out all sessions, company export, delete account (explicit confirm plus re-auth).
- **APIs:** `/conversations*`, `/usage`, `/me*`, `/company*`, `DELETE /me`. **Backend:** B-F3, B-F4.
- **Gate:** export file opens and contains no secrets; delete-account flow ends with sessions revoked and the public widget showing unavailable.

## Sprint F6 - Integration and UX polish (build-plan day 7)

- Fix seams between flows; empty/error/loading audit on every screen.
- Accessibility pass: focus order, labels, live-region announcements for status changes, reduced motion, contrast.
- English and Bangla rendering (fonts, wrapping, RTL not required), 20-question bilingual chat check against a seeded bot.
- Secret-exposure audit: bundle and network review.
- **Gate:** zero critical axe violations; Lighthouse a11y >= 95 on core screens; no console errors in the golden path.

## Sprint F7 - Reliability, deploy, acceptance (build-plan days 8-10)

- Failure drills in the UI: backend 503, Redis/Postgres outage, quota exhausted, SSE proxy buffering and abort behind Nginx.
- Production build, env manifest, Nginx config for streaming, security headers and CSP for the iframe.
- Full Playwright regression (auth, upload/processing states, publish/embed, visitor chat on three host pages), mobile and keyboard checks.
- **Gate:** [10-TEST-AND-LAUNCH](10-TEST-AND-LAUNCH.md) release checklist for the frontend half; no open launch blockers.

## Timeline and dependencies

```
F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7
              \----- F2 and F3 can overlap once F1 lands (separate screens, shared kit)
```
Backend items B-F1..B-F5 are scheduled inside the sprint that needs them, not before.

## Entry conditions and risks

1. **Backend gate not yet green.** [19](19-BACKEND-SPRINT-PLAN-V2.md) and [14](14-SPRINT-PLAN.md) say frontend starts after Phase 8 (chaos suite). Status doc 21: DB-backed tests, smoke script and chaos runs are still unexecuted. Starting now is an explicit owner decision; the risk is UI built on behavior that has never run against a real database.
2. **No `.env` / database available yet.** F0 cannot finish without a disposable Postgres and the provider credentials.
3. Free-tier limits (Cloudflare neurons, Groq) will make end-to-end demos flaky; the UI must treat quota states as normal.
4. Upload grants are in process memory in the backend: the frontend must not assume uploads survive an API restart.
