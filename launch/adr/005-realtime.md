# ADR 005 — Realtime for live inbox and takeover

**Status**: Decided 2026-11-25. Implementation Day 6.

## Context

Live inbox (section 2G) and the "a team member joined" visitor notice require pushing events from server to both owner UI and the visitor widget in near-real time. Options are SSE or WebSocket.

## Options

**A — SSE + Redis pub/sub.** Server pushes; client receives. Simple. Reuses our existing SSE infra (chat pipeline already streams with SSE through Nginx). Visitors receive updates on their open conversation via the active SSE channel; owner receives updates by subscribing to a per-tenant `inbox:{company_id}` channel.

**B — WebSocket.** Bidirectional. More ops surface (sticky sessions, pings). Over-kill for our push-dominant usage.

**C — Long-polling.** Shelved — bad DX.

## Decision

**Option A.** SSE from `GET /inbox/stream?since=<cursor>`; backend subscribes to the Redis channel for the authed company, fans received events into the HTTP response. Visitor side: the existing `/public/conversations/.../messages` SSE already streams; we add a sidecar SSE `GET /public/conversations/.../stream` for state events (`handoff_started`, `agent_joined`).

## Trade-offs

- SSE is one-way (server→client); the owner "take over" action is a regular `POST`. Acceptable.
- Nginx must be configured `proxy_buffering off` + long timeouts for SSE; already in the deploy checklist.
- Redis pub/sub is fire-and-forget. If the API pod dies mid-event, the event is lost. Mitigation: all state changes also write to `event_outbox` (ADR 003); the stream endpoint seeds from the outbox on connect using the `since` cursor, then switches to live pub/sub.

## Rollback

Disable the stream endpoint; owner UI falls back to polling the list every 5 s. Degrades gracefully.
