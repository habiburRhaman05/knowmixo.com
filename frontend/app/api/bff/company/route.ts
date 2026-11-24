import { NextResponse } from "next/server";
import { backend } from "@/lib/backend";
import { fail, readJson } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function GET() {
  try {
    const { data } = await backend<unknown>("/api/v1/company");
    return NextResponse.json(data as object);
  } catch (error) {
    return fail(error);
  }
}

export async function POST(request: Request) {
  try {
    const body = await readJson<Record<string, unknown>>(request);
    const { data } = await backend<unknown>("/api/v1/company", { method: "POST", body });
    return NextResponse.json(data as object, { status: 201 });
  } catch (error) {
    return fail(error);
  }
}

export async function PATCH(request: Request) {
  try {
    const body = await readJson<Record<string, unknown>>(request);
    const { data } = await backend<unknown>("/api/v1/company", { method: "PATCH", body });
    return NextResponse.json(data as object);
  } catch (error) {
    return fail(error);
  }
}
