import { proxyJson } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function POST(request: Request) {
  return proxyJson(request, "/api/v1/sources/faqs", "POST", 202);
}
