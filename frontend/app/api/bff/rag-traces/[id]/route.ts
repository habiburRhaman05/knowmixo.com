import { proxyGet } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyGet(`/api/v1/rag-traces/${encodeURIComponent(id)}`);
}
