import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_: Request, { params }: Ctx) {
  const { id } = await params;
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const token = await readSession();
  const response = await fetch(
    `${base}/api/v1/conversations/${encodeURIComponent(id)}/export`,
    { headers: token ? { authorization: `Bearer ${token}` } : {}, cache: "no-store" },
  );
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      "content-disposition":
        response.headers.get("content-disposition") ||
        `attachment; filename="conversation-${id}.json"`,
    },
  });
}
