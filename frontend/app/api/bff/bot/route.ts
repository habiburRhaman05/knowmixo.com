import { proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET() {
  return proxyGet("/api/v1/bot");
}
export async function PATCH(request: Request) {
  return proxyJson(request, "/api/v1/bot", "PATCH");
}
