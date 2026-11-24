import { NextResponse } from "next/server";
import { readParentOrigin, readVisitorToken, widgetBackend } from "@/lib/widget-backend";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Ctx) {
  const { id } = await params;
  try {
    const body = await request.json().catch(() => ({}));
    const { data, status } = await widgetBackend<unknown>(
      `/api/v1/public/conversations/${encodeURIComponent(id)}/lead`,
      {
        method: "POST",
        body: body as Record<string, unknown>,
        visitorToken: readVisitorToken(request),
        parentOrigin: readParentOrigin(request),
      }
    );
    return NextResponse.json(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}
