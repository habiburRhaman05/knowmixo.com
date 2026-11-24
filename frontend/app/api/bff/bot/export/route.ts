/**
 * Export streams a JSON download. We fetch it on the server and relay the
 * payload + Content-Disposition so the browser gets the download prompt.
 */
import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";

export async function GET() {
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const token = await readSession();
  const response = await fetch(`${base}/api/v1/bot/export`, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      "content-disposition":
        response.headers.get("content-disposition") || 'attachment; filename="bot-export.json"',
    },
  });
}
