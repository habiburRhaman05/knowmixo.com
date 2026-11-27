# ADR 006 — Widget delivery, CSP, postMessage contract

**Status**: Decided 2026-11-25. Keep current approach; harden.

## Context

Current widget: `public/embed.js` loader + sandboxed `<iframe>` pointing at `/widget/{publicId}`. Has basic postMessage (`kmv:ready`, `kmv:open`, `kmv:close`). Section 2D demands a far richer API (`identify`, `setMetadata`, `on(event, cb)`, etc.) and 7 install snippets.

## Options

**A — Keep loader + iframe (chosen).**
**B — Shadow DOM inline, no iframe.** Faster first paint; worse CSS isolation; potential CSP issues on customer sites.
**C — Web Component.** Immature browser matrix for older Safari.

## Decision

**Option A.** Rationale: CSS/JS isolation from the host page is already the biggest selling point; one host CSP rule (`frame-src app.knowmivo.com`) is all the customer needs.

## Hardening

- **postMessage schema**: defined and validated on both sides. Reject messages whose `origin !== widgetOrigin` (already done); add schema check (`type in {kmv:ready, kmv:open, kmv:close, kmv:resize, kmv:event}`), reject unknown.
- **Versioned CDN URL**: ship `embed.js` as `embed.v1.js`, `embed.v2.js`. Existing installed snippets never break on a new release. `embed.js` itself redirects to the current major.
- **Sandbox attrs**: iframe ships `sandbox="allow-scripts allow-forms"` today — keep. Never add `allow-same-origin` (would break the isolation guarantee).
- **CSP on widget page**: `frame-ancestors *` (any host can embed; backend's `bot_domains` allow-list is the real gate) — already in `next.config.mjs`.
- **CSP on embed.js**: `Content-Type: application/javascript; charset=utf-8` + 5 min browser cache + 1 h CDN cache — already configured.
- **HMAC-signed identity** (D.3.2): owner creates a secret per bot; dashboard shows it once. Widget JS API `identify({userId, email, name, hmac})` sends it; backend verifies.

## Install snippets

- Script tag (`<script src=".../embed.js" data-bot-id="pub_..." async>`)
- React component (`@knowmivo/react`) — thin wrapper, Day 7
- Next.js (`<Script strategy="lazyOnload">`)
- Google Tag Manager — custom-HTML tag
- WordPress — plug-in or theme snippet
- Shopify — theme snippet
- Webflow / Wix / Squarespace — instructions page
- Raw iframe / hosted chat page link
- QR code for hosted chat URL

## Rollback

Old snippet continues to load `/embed.v1.js`; new snippet switches to `/embed.v2.js`; both coexist on CDN.
