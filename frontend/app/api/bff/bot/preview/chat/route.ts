/**
 * Owner draft preview chat. Proxies an SSE stream from the backend straight
 * through to the browser so the UI sees the exact event shape the backend
 * produces (meta/sources/delta/done/error). Response.body is streamed via
 * ReadableStream so chunks arrive as they're produced -- not buffered.
 */
import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const token = await readSession();
  const body = await request.text();
  const headers: Record<string, string> = {
    "content-type": "application/json",
    accept: "text/event-stream",
  };
  if (token) headers.authorization = `Bearer ${token}`;
  const idemp = request.headers.get("idempotency-key");
  if (idemp) headers["idempotency-key"] = idemp;

  const response = await fetch(`${base}/api/v1/bot/preview/chat`, {
    method: "POST",
    headers,
    body,
    // @ts-expect-error -- Node 18+ fetch supports duplex but types differ
    duplex: "half",
    cache: "no-store",
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}
