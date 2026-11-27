import { proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyJson(request, `/api/v1/quality/gaps/${encodeURIComponent(id)}/resolve`, "POST");
}
