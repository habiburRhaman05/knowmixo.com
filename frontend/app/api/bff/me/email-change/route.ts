import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ new_email?: string; current_password?: string }>(request);
    const { data } = await backend<unknown>("/api/v1/me/email-change", {
      method: "POST",
      body: {
        new_email: body.new_email ?? "",
        current_password: body.current_password ?? "",
      },
    });
    return NextResponse.json(data as object, { status: 202 });
  } catch (error) {
    return fail(error);
  }
}
