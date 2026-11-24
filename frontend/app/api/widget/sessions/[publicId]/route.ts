import { NextResponse } from "next/server";
import { widgetBackend, readParentOrigin } from "@/lib/widget-backend";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ publicId: string }> };

export async function POST(request: Request, { params }: Ctx) {
  const { publicId } = await params;
  try {
    const parentOrigin = readParentOrigin(request);
    const { data, status } = await widgetBackend<{ visitor_token: string; expires_at: string }>(
      `/api/v1/public/bots/${encodeURIComponent(publicId)}/sessions`,
      { method: "POST", parentOrigin, body: {} }
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    return fail(error);
  }
}
