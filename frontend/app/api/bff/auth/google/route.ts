import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";
import { writeSession } from "@/lib/session";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ id_token?: string }>(request);
    const { data } = await backend<{ session_token: string }>("/api/v1/auth/google", {
      method: "POST",
      body: { id_token: body.id_token ?? "" },
    });
    const jar = await cookies();
    writeSession(jar, data.session_token);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return fail(error);
  }
}
