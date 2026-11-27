import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";

/**
 * Raw SSE passthrough (ADR 005): EventSource in the browser can't send
 * custom headers, so auth has to ride the httpOnly session cookie this
 * route already reads server-side, same as every other BFF route --
 * the browser never needs (or gets) the bearer token. The response body
 * is streamed straight through unbuffered, matching the pattern the
 * live widget chat SSE already uses for its own stream.
 */
export async function GET(request: Request) {
  const qs = new URL(request.url).search;
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const token = await readSession();
  if (!token) {
    return new Response("unauthenticated", { status: 401 });
  }
  const response = await fetch(`${base}/api/v1/inbox/stream${qs}`, {
    headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" },
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
    },
  });
}
