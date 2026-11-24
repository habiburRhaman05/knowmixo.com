import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await readJson<{ id_token?: string }>(request);
    const { data } = await backend<unknown>("/api/v1/me/oauth/google/link", {
      method: "POST",
      body: { id_token: body.id_token ?? "" },
    });
    return NextResponse.json(data as object);
  } catch (error) {
    return fail(error);
  }
}
