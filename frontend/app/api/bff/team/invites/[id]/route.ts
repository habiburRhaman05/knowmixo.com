import { proxyDelete, proxyGet } from "@/lib/bff-proxy";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

/**
 * Dual-purpose by coincidence of URL shape, not by design: the owner-
 * authenticated revoke-by-id flow and the backend's public preview-by-
 * token flow both live at /api/v1/team/invites/{id_or_token}, just on
 * different backend routers (one needs a session, one doesn't).
 * proxyGet forwards the session cookie only if one exists, so this GET
 * works correctly for a logged-out visitor previewing their invite link.
 */
export async function GET(_: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyGet(`/api/v1/team/invites/${encodeURIComponent(id)}`);
}

export async function DELETE(request: Request, { params }: Ctx) {
  const { id } = await params;
  return proxyDelete(request, `/api/v1/team/invites/${encodeURIComponent(id)}`);
}
