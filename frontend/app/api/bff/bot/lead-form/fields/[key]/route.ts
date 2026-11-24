import { proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ key: string }> };

export async function PATCH(request: Request, { params }: Ctx) {
  const { key } = await params;
  return proxyJson(
    request,
    `/api/v1/bot/lead-form/fields/${encodeURIComponent(key)}`,
    "PATCH",
  );
}
