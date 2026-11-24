import { proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function POST(request: Request) {
  return proxyJson(request, "/api/v1/bot/publish", "POST", 201);
}
