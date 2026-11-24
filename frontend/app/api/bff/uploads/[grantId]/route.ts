/**
 * Upload the raw file bytes to the backend via the one-shot grant URL. The
 * grant_id is opaque and unguessable, but we still forward it through the
 * BFF (rather than letting the browser hit the backend directly) so that
 * CORS is never needed and the backend-internal URL stays private.
 */
import { NextResponse } from "next/server";
import { readSession } from "@/lib/session";
import { serverEnv } from "@/lib/env";
import { ApiError } from "@/lib/errors";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ grantId: string }> };

export async function PUT(request: Request, { params }: Ctx) {
  // Upload needs raw bytes (not JSON) forwarded straight through to the
  // backend. backend.ts always JSON-encodes, so we do the fetch ourselves
  // here with the session cookie attached as a Bearer header.
  const { grantId } = await params;
  try {
    const token = await readSession();
    const body = await request.arrayBuffer();
    const headers: Record<string, string> = {
      "content-type": request.headers.get("content-type") || "application/octet-stream",
    };
    if (token) headers.authorization = `Bearer ${token}`;

    const base = serverEnv.backendUrl().replace(/\/$/, "");
    const response = await fetch(`${base}/api/v1/uploads/${encodeURIComponent(grantId)}`, {
      method: "PUT",
      body,
      headers,
      cache: "no-store",
    });
    const text = await response.text();
    const json = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new ApiError(response.status, (json?.detail ?? json) as Record<string, unknown>);
    }
    return NextResponse.json(json, { status: response.status });
  } catch (error) {
    if (error instanceof ApiError) return fail(error);
    return fail(new ApiError(500, { code: "internal_error", message: "Upload failed." }));
  }
}
