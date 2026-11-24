import { NextResponse } from "next/server";
import { widgetBackend, readParentOrigin, readVisitorToken } from "@/lib/widget-backend";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const visitorToken = readVisitorToken(request);
    const parentOrigin = readParentOrigin(request);
    const { data, status } = await widgetBackend<{ conversation_id: string }>(
      "/api/v1/public/conversations",
      { method: "POST", visitorToken, parentOrigin, body: {} }
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    return fail(error);
  }
}
