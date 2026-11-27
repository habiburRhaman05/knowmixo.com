import { proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyJson(request, `/api/v1/escalations/contacts/${encodeURIComponent(id)}/send-code`, "POST");
}
