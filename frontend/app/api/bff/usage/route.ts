import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function GET() {
  try {
    const { data } = await backend<unknown>("/api/v1/usage");
    return NextResponse.json(data as object);
  } catch (error) {
    return fail(error);
  }
}
