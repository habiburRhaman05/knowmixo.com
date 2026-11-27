import { proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const qs = new URL(request.url).search;
  return proxyGet(`/api/v1/actions${qs}`);
}

export async function POST(request: Request) {
  return proxyJson(request, "/api/v1/actions", "POST");
}
