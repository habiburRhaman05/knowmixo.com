import { proxyDelete } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function DELETE(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyDelete(request, `/api/v1/api-keys/${encodeURIComponent(id)}`);
}
