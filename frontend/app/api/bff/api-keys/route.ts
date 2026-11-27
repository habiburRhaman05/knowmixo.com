import { proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET() {
  return proxyGet("/api/v1/api-keys");
}

export async function POST(request: Request) {
  return proxyJson(request, "/api/v1/api-keys", "POST");
}
