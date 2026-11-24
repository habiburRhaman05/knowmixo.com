import { proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET() {
  return proxyGet("/api/v1/bot/domains");
}
export async function PUT(request: Request) {
  return proxyJson(request, "/api/v1/bot/domains", "PUT");
}
