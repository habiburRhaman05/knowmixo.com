import { proxyDelete, proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyGet(`/api/v1/actions/${encodeURIComponent(id)}`);
}

export async function PATCH(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyJson(request, `/api/v1/actions/${encodeURIComponent(id)}`, "PATCH");
}

export async function DELETE(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyDelete(request, `/api/v1/actions/${encodeURIComponent(id)}`);
}
