import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";

/**
 * D8.1: CSV export, same raw-passthrough shape as
 * app/api/bff/conversations/[id]/export/route.ts's JSON export -- the
 * backend's response is already a CSV body with its own
 * Content-Disposition header, so this forwards it unwrapped rather than
 * going through the JSON-only ok()/fail() helpers in lib/bff-response.ts.
 */
export async function GET(request: Request) {
  const qs = new URL(request.url).search;
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const token = await readSession();
  const response = await fetch(`${base}/api/v1/conversations/export.csv${qs}`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "text/csv",
      "content-disposition":
        response.headers.get("content-disposition") || 'attachment; filename="conversations.csv"',
    },
  });
}
