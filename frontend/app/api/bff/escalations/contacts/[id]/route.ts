import { proxyDelete, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyJson(request, `/api/v1/escalations/contacts/${encodeURIComponent(id)}`, "PATCH");
}

export async function DELETE(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyDelete(request, `/api/v1/escalations/contacts/${encodeURIComponent(id)}`);
}
