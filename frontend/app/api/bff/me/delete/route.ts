/**
 * Account deletion. The backend returns 202 and a cleanup job id. After the
 * request succeeds we clear our session cookie so the browser can no longer
 * reach anything owner-scoped.
 */
import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";
import { clearSession } from "@/lib/session";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ confirm?: boolean; current_password?: string }>(request);
    const { data, status } = await backend<{ cleanup_job_id?: string }>("/api/v1/me", {
      method: "DELETE",
      body: {
        confirm: body.confirm === true,
        current_password: body.current_password ?? "",
      },
    });
    const jar = await cookies();
    clearSession(jar);
    return NextResponse.json(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}
