import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { ApiError } from "@/lib/errors";
import { clearSession } from "@/lib/session";

export const runtime = "nodejs";

export async function POST() {
  const jar = await cookies();
  try {
    await backend<unknown>("/api/v1/auth/logout", { method: "POST" });
  } catch (error) {
    // 401 is expected if the token was already invalid; still clear locally.
    if (!(error instanceof ApiError) || error.status !== 401) {
      clearSession(jar);
      return NextResponse.json(
        {
          code: error instanceof ApiError ? error.code : "internal_error",
          message: error instanceof ApiError ? error.message : "Logout failed.",
        },
        { status: 500 }
      );
    }
  }
  clearSession(jar);
  return new NextResponse(null, { status: 204 });
}
