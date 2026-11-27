import { proxyGet, proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function GET() {
  return proxyGet("/api/v1/team/invites");
}

export async function POST(request: Request) {
  return proxyJson(request, "/api/v1/team/invites", "POST");
}
