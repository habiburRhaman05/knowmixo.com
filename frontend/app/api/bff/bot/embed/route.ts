import { proxyGet } from "@/lib/bff-proxy";
export const runtime = "nodejs";
export async function GET() {
  return proxyGet("/api/v1/bot/embed");
}
