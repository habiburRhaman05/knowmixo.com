import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { ApiError } from "@/lib/errors";
import { clearSession } from "@/lib/session";

export const runtime = "nodejs";

export async function POST() {
  const jar = await cookies();
  try {
    await backend<unknown>("/api/v1/auth/logout-all", { method: "POST" });
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      clearSession(jar);
      return NextResponse.json(
        {
          code: error instanceof ApiError ? error.code : "internal_error",
          message: error instanceof ApiError ? error.message : "Sign-out failed.",
        },
        { status: 500 }
      );
    }
  }
  clearSession(jar);
  return new NextResponse(null, { status: 204 });
}
