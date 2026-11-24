# Frontend status after Sprints F6–F7

Finished without a running backend or `.env`. Every feature wires to the real BFF proxy and the real backend contract. Nothing has been exercised against a live server — first run will surface small mismatches.

## What's new (versus 23-STATUS)

### Sprint F6 — Public widget + distribution

- **`embed.js`** — dependency-free launcher script ([public/embed.js](../frontend/public/embed.js)).
  - Finds its own `<script>` tag, reads `data-bot-id`, `data-api`, `data-position`.
  - Injects a floating launcher button (bottom-right by default, bottom-left supported).
  - On click, lazily mounts a sandboxed `<iframe>` pointing at `/widget/<publicId>`.
  - Listens for `kmv:ready` and `kmv:close` postMessage events, exposes `window.Knowmivo.open/close/toggle`.
  - Honours `prefers-reduced-motion`. No owner credentials ever appear in the script or its config.

- **Hosted chat page** `/chat/[publicId]` ([app/chat/[publicId]/](../frontend/app/chat/[publicId])) — standalone full-page chat for the hosted URL from `/bot/embed`.

- **Widget iframe page** `/widget/[publicId]` ([app/widget/[publicId]/](../frontend/app/widget/[publicId])) — stripped-down layout (no Toast provider, no app chrome), sends `kmv:ready` on mount, responds to `kmv:open`/`kmv:close` from the host.

- **`PublicChatWindow`** — the real visitor-side chat component ([src/components/chat/public-chat-window.tsx](../frontend/src/components/chat/public-chat-window.tsx)). Handles:
  - Bootstrap: `/widget/config/{publicId}` + `/widget/sessions/{publicId}` with full error mapping (`bot_not_found`, `bot_unpublished`, `origin_not_allowed`).
  - SSE streaming with `meta`/`sources`/`delta`/`done`/`error` events.
  - Stop (AbortController), scroll sticking, typing bubble.
  - **Real** thumbs-up / thumbs-down feedback → `POST /public/messages/{id}/feedback` via `/api/widget/messages/{id}/feedback`.
  - **Real** lead capture: slide-up form, checkbox consent gate, `POST /public/conversations/{id}/lead` via `/api/widget/conversations/{id}/lead`. Triggered after two assistant replies, skippable.
  - Brand color flows through header, user bubble, citation markers and send button.

- **6 widget BFF routes** under `/api/widget/*`. Visitor-token is a Bearer header (not a cookie, because iframes can't set cookies cross-origin). Each route forwards the parent-page origin via `X-Parent-Origin` so the backend's domain allowlist can be checked properly (docs/22 B-F1).

- **CSP for the widget** in [next.config.mjs](../frontend/next.config.mjs):
  - `/widget/*` ships `Content-Security-Policy: frame-ancestors *` and drops the global `X-Frame-Options: DENY`.
  - `/embed.js` is served with the right `Content-Type` and a sensible cache (5 min browser / 1 h shared).
  - All other routes keep the strict baseline.

### Sprint F6 — Account deletion flow

- **`DeleteAccountCard`** ([src/components/settings/delete-account-card.tsx](../frontend/src/components/settings/delete-account-card.tsx)) replaces the placeholder in Settings.
- Two-gate confirm: current-password **re-auth** AND the typed phrase `"delete my account"`.
- `/api/bff/me/delete` proxies `DELETE /me`, clears the session cookie on success.
- Redirects to `/login?deleted=1` where a success banner reads "Your account has been deleted."

### Sprint F7 — Resilience, polish, deploy

- **Error / loading boundaries**:
  - `app/error.tsx` — top-level app error with a tasteful card and the error digest.
  - `app/not-found.tsx` — branded 404 that links back to Overview and the landing page.
  - `app/(app)/error.tsx` — section-level error that keeps the sidebar visible so the user can navigate out of a broken page.
  - `app/(app)/loading.tsx` — skeleton for every owner screen while the chunk loads.
  - `app/(auth)/loading.tsx` — subdued skeleton for auth pages.

- **Production build target**: `next.config.mjs` now sets `output: "standalone"` so the Dockerfile can ship a minimal server.

- **Dockerfile** ([frontend/Dockerfile](../frontend/Dockerfile)):
  - 3-stage build: deps → build → run.
  - Final image runs as non-root (`knowmivo` user), uses Node 22-alpine, no npm wrapper (`node server.js`).
  - `HEALTHCHECK` hits `/api/health` (new local-only probe).
  - Build args `NEXT_PUBLIC_APP_URL` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` are baked into the client bundle at build time.

- **GitHub Actions workflow** [.github/workflows/frontend-ci.yaml](../.github/workflows/frontend-ci.yaml): typecheck → tests → production build on every push and PR touching `frontend/**`. Uses Node 22 and a stub `BACKEND_INTERNAL_URL`.

- **Middleware now correctly skips** `/chat/*`, `/widget/*` and `/embed.js`, so visitor traffic never hits the session check.

- **More tests**: `types.test.ts` (status/stage/error-code map coverage), `studio-config.test.ts` (diff helper), `widget-backend.test.ts` (bearer token + parent-origin header parsing).

## Verified here

```
cd frontend
npm run typecheck   # clean
npm test            # 7 files, 29 tests pass
npm run build       # 66 routes build, 100 kB shared first-load JS
```

## Totals

| Metric | Value |
| --- | --- |
| App pages | 18 (landing, 5 auth, 9 app, 1 publish, 1 hosted chat, 1 widget iframe) |
| BFF routes | 51 (44 owner + 6 widget + 1 health) |
| Test files | 7 with 29 tests |
| Shared first-load JS | 100 kB |
| Heaviest page | Settings 12.8 kB (187 kB first-load) — because of the delete flow + Google linking |

## Not verified (needs live backend + `.env`)

1. Widget flow end-to-end on a real third-party page — embed.js has only been read, not run.
2. SSE visitor chat.
3. Account deletion actually clearing cookies + hitting backend `DELETE /me`.
4. `/api/health` probe inside Docker.
5. Google sign-in — still shows "not configured" toast until `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is set.

## What's left before launch (not in F6/F7)

1. Playwright end-to-end suite (docs/22 F7 gate "Playwright regression") — not written yet, because it needs a real backend to run against.
2. Backend B-F1 trust-header handling — our widget BFF already sends `x-parent-origin` and `x-bff-trust`, but the backend doesn't parse them yet.
3. Backend B-F2 draft-config validation — still accepts any JSON.
4. Backend B-F3 avatar/logo upload — we store opaque keys but have no upload endpoint.
5. Nginx config (streaming SSE, security headers for the real host) — pending real deploy target.
