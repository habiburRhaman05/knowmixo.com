import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ token?: string }>(request);
    const { data } = await backend<unknown>("/api/v1/me/email-change/confirm", {
      method: "POST",
      body: { token: body.token ?? "" },
    });
    return NextResponse.json(data as object);
  } catch (error) {
    return fail(error);
  }
}
