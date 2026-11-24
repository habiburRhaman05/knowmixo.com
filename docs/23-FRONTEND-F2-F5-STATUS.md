# Frontend status after Sprints F2–F5

Finished without a running backend or `.env`. Every feature is wired to the real BFF proxy and the real backend contract from `backend/openapi.yaml`, but nothing has been exercised against a live server. First-run against a real backend will likely surface a handful of small mismatches.

## What's new (versus 21-STATUS)

### Sprint F2 — Knowledge ([app/(app)/knowledge/](../frontend/app/(app)/knowledge))

- **Add source dialog** with five tabs:
  - **Upload file** — drop zone, extension and size pre-checks, three-stage upload (grant → PUT bytes with XHR progress → complete with idempotency key).
  - **Text** — title + content with live character count and the real 1,000,000-character backend cap.
  - **FAQ** — repeater editor backed by `useFieldArray`, with Zod bounds that mirror the backend (up to 200 Q&A, 500 / 5,000 chars).
  - **URL** — one-page import with SSRF explanation.
  - **Crawl** — start discovery, poll `crawl-jobs/{id}` every 2s, pick pages with select-all / clear, idempotent import.
- **Knowledge list** with search (debounced), status filter (All / Ready / Processing / Failed), type filter, cursor pagination, 3-second polling while any row is in a non-terminal state.
- **Source row** shows the type icon, status badge with stage suffix (`Processing · Embedding`), human error copy keyed on backend `error_code`, actions menu with refresh and delete.
- **Source detail drawer** with extracted-text preview, document outline (pages/headings), source URL, refresh and delete.
- **Status badges** use the ten real status/stage names from the UI spec — never fake progress bars.
- **Idempotency keys** are generated and sent for upload-complete, refresh and crawl-import.

### Sprint F3 — Bot Studio ([app/(app)/chatbot/](../frontend/app/(app)/chatbot))

- Two-column layout: editor on the left, sticky live preview on the right (stacks on mobile).
- **Behavior** editor: name, tone, language, templates (customer support, sales, internal), instructions with character count, fallback message, citations toggle.
- **Appearance** editor: greeting, up to 4 suggested questions, brand color picker + hex input, widget position chooser.
- **Lead form** panel: load `/bot/lead-form`, flip required toggles per field via `/bot/lead-form/fields/{key}`.
- **Draft saving** uses a shallow diff → PATCH only changed keys with the current `draft_revision`. On `draft_revision_conflict` we reload the server copy and tell the user — the user's local edits stay in the form.
- **Live preview chat** uses the real `/bot/preview/chat` SSE pipeline through our shared `ChatWindow`:
  - Creates the preview conversation lazily on first send.
  - Streams `meta` / `sources` / `delta` / `done` / `error` events.
  - Supports Stop (AbortController), scroll preservation, no duplicate sends, retry-after surfaced for quota errors.
  - Shows the fallback message when there are no sources, and a typing-dot bubble while the stream is empty.
- **Unsaved changes** / **Revert** / **Save draft** controls, with the "Live / Draft only" badge up top.

### Sprint F4 — Publish & embed ([app/(app)/chatbot/publish/](../frontend/app/(app)/chatbot/publish))

- Pick ready source versions with a checkbox list; the "Publish snapshot" button is disabled until at least one is selected.
- Publish with deterministic `Idempotency-Key = publish:<sorted ids>`.
- Unpublish with a confirm dialog.
- Allowed domains editor (one per line, supports `*.example.com`).
- Install snippets (script tag, React, Next.js) + hosted chat URL from `/bot/embed`, with one-click Copy-to-clipboard.

### Sprint F5 — Conversations ([app/(app)/conversations/](../frontend/app/(app)/conversations))

- **List** with status filter, feedback filter, cursor pagination, badges for lead/feedback.
- **Detail** with the full transcript, per-message feedback badges, cited sources inline (indexed, with excerpts), a Lead sidebar panel and a unique-sources sidebar.
- **Export** downloads the backend's JSON file directly through the BFF.
- **Delete** confirms, then removes.

### Shared primitives added this round
- `Dialog` (Radix), `Textarea`, `Progress`, `EmptyState`.
- `ChatWindow` — the one chat widget used by Studio preview and (later) the public widget. Handles SSE, Stop, scroll sticking, feedback stubs, "no evidence" fallback.
- `SourceStatusBadge`, `SourceRow`, `SourceDetail`, `AddSourceDialog` — everything for Knowledge.
- Shared `bff-proxy.ts` helper so every new BFF route is three lines of code.
- `usePoll` hook — polls on interval, pauses while the tab is hidden.

### BFF routes added (30 of them)
All under `/api/bff/*`. The session cookie stays in httpOnly; `Idempotency-Key` and `X-Request-ID` are forwarded. Upload and SSE routes bypass the JSON helper so raw bytes / streams aren't buffered. See [frontend/app/api/bff/](../frontend/app/api/bff/) for the tree.

## Verification run here

```
cd frontend
npm run typecheck   # tsc --noEmit — clean
npm test            # 4 files, 18 tests pass (SSE parser, schemas, errors, password score)
npm run build       # 60 routes compile, 100 kB shared first-load JS
```

## Not verified (needs running backend + `.env`)

1. Grant-token PUT upload (XHR progress + the three-step choreography) has never been end-to-end against a real file.
2. The SSE preview chat is parse-tested but hasn't streamed real tokens from the backend.
3. Publish / unpublish round-trip and `draft_revision_conflict` recovery haven't been exercised live.
4. `.env` is still missing — Google sign-in will show a "not configured" toast until `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is set.

## Deliberate gaps

- The widget embed script (`embed.js`) and the public hosted-chat page are still Sprint F4 bottom half / Sprint F7; the UI/BFF are ready for them.
- Conversation detail cites sources by title but doesn't deep-link to the source page yet — that lands with Sprint F6 polish.
- Account deletion in Settings is still the "Coming in Sprint F5" badge; the account-lifecycle flow is paired with the backend DELETE /me behaviour that still needs a live test.
- The widget message feedback thumbs in `ChatWindow` are visual only (not POSTed to `/public/messages/{id}/feedback`) — the preview has no public message id, and the hosted-chat variant will pass the right endpoint.

## Totals so far

- **Pages:** 15 (landing, 5 auth, 9 app).
- **BFF routes:** 44.
- **Test files:** 4 with 18 tests.
- **Shared first-load JS:** 100 kB.
- **Heaviest page:** Knowledge at 15.2 kB (190 kB first-load), because of the five-tab Add Source dialog and status machinery.
