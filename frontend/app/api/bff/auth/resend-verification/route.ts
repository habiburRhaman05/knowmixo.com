import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ email?: string }>(request);
    const { data } = await backend<{ status: string }>("/api/v1/auth/resend-verification", {
      method: "POST",
      body: { email: body.email ?? "" },
    });
    return NextResponse.json(data, { status: 202 });
  } catch (error) {
    return fail(error);
  }
}
