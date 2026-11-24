import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";
import { writeSession } from "@/lib/session";

export const runtime = "nodejs";

type LoginBody = { email?: string; password?: string };
type LoginResponse = { session_token: string };

export async function POST(request: Request) {
  try {
    const body = await readJson<LoginBody>(request);
    const { data } = await backend<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email: body.email ?? "", password: body.password ?? "" },
    });
    const jar = await cookies();
    writeSession(jar, data.session_token);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return fail(error);
  }
}
