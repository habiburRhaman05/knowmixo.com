import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ token?: string }>(request);
    const { data } = await backend<{ status: string }>("/api/v1/auth/verify-email", {
      method: "POST",
      body: { token: body.token ?? "" },
    });
    return NextResponse.json(data);
  } catch (error) {
    return fail(error);
  }
}
