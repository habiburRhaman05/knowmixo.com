# Knowmivo frontend (Next.js)

Premium-SaaS marketing + admin dashboard for Knowmivo, matching
`docs/07-UI-SPEC.md` and `docs/22-FRONTEND-BUILD-SPRINT-PLAN.md`.

## Quick start

```bash
cp .env.example .env.local
# fill BACKEND_INTERNAL_URL and NEXT_PUBLIC_GOOGLE_CLIENT_ID
npm install
npm run dev     # http://localhost:3000
```

The backend must be reachable at `BACKEND_INTERNAL_URL`. Every browser
request goes through the Next.js BFF at `/api/bff/*`, which adds the session
token from an httpOnly cookie before calling the FastAPI backend — browser
code never sees the token.

## What ships in Phase 0 and Phase 1

- Marketing landing page + premium two-panel auth layout.
- Full auth surface:
  - **Email/password sign up** (inline strength meter, 10-char rule).
  - **Email verification** page with resend cooldown.
  - **Sign in** with Google or password, open-redirect-safe `next=` handling.
  - **Forgot password** + **Reset password** (token flow).
  - **Change password** (settings).
  - **Logout** and **Logout of every session**.
  - **Google sign-in / link** via Google Identity Services.
- Dashboard shell (sidebar, top bar, account menu, verification banner).
- Overview page: KPIs, setup checklist, next actions.
- Usage page: daily company + platform allowance, next reset.
- Onboarding stepper, Settings (profile, company, password, security).
- Placeholder pages for Knowledge / Chatbot / Conversations that show what
  arrives in Sprint F2–F5 — never a dead link.
- 18 unit tests: SSE parser (meta/sources/delta/done/heartbeat), auth
  schemas, error mapper, password strength.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server on :3000 |
| `npm run build` | Production build |
| `npm run start` | Run the production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | Next.js lint |
| `npm test` | Vitest run |

## Project layout

```
app/
  (auth)/           login, signup, verify-email, forgot, reset
  (app)/            overview, onboarding, knowledge, chatbot,
                    conversations, usage, settings
  api/bff/          BFF proxy: keeps the bearer token server-side
  globals.css       design tokens (light + dark)
  layout.tsx        fonts, toast provider, skip-to-content
src/
  components/ui/    shadcn-style primitives (Button, Field, Alert…)
  components/auth/  Google sign-in, auth shell, error alert
  components/layout/ sidebar, topbar, page shell, coming-soon
  lib/              env, session, backend client, api client, errors,
                    auth schemas, sse parser
middleware.ts       session-cookie route protection
```
