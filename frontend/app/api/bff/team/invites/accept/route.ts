import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";
import { writeSession } from "@/lib/session";

export const runtime = "nodejs";

type AcceptBody = { token?: string; name?: string; password?: string };
type AcceptResponse = { session_token: string };

/**
 * Same shape as the login route: the backend returns a raw bearer
 * token, which must never reach browser JS, so this writes it straight
 * into the httpOnly session cookie and returns only {ok:true}.
 */
export async function POST(request: Request) {
  try {
    const body = await readJson<AcceptBody>(request);
    const { data } = await backend<AcceptResponse>("/api/v1/team/invites/accept", {
      method: "POST",
      body: { token: body.token ?? "", name: body.name, password: body.password },
    });
    const jar = await cookies();
    writeSession(jar, data.session_token);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return fail(error);
  }
}
