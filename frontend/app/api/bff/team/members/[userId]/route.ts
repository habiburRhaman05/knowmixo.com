import { proxyDelete, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ userId: string }> };

export async function PATCH(request: Request, { params }: Ctx) {
  const { userId } = await params;
  return proxyJson(request, `/api/v1/team/members/${encodeURIComponent(userId)}`, "PATCH");
}

export async function DELETE(request: Request, { params }: Ctx) {
  const { userId } = await params;
  return proxyDelete(request, `/api/v1/team/members/${encodeURIComponent(userId)}`);
}
