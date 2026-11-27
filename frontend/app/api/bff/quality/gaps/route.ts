import { proxyGet } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const qs = new URL(request.url).search;
  return proxyGet(`/api/v1/quality/gaps${qs}`);
}
