import { proxyDelete } from "@/lib/bff-proxy";

export const runtime = "nodejs";

export async function DELETE(request: Request) {
  return proxyDelete(request, "/api/v1/integrations/slack");
}
