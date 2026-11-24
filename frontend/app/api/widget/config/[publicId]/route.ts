import { NextResponse } from "next/server";
import { widgetBackend, readParentOrigin } from "@/lib/widget-backend";
import { ApiError } from "@/lib/errors";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";

type Ctx = { params: Promise<{ publicId: string }> };

export async function GET(request: Request, { params }: Ctx) {
  const { publicId } = await params;
  try {
    const parentOrigin = readParentOrigin(request);
    const { data } = await widgetBackend<unknown>(
      `/api/v1/public/bots/${encodeURIComponent(publicId)}/config`,
      { parentOrigin }
    );
    return NextResponse.json(data as object, {
      headers: { "Cache-Control": "public, max-age=30, stale-while-revalidate=300" },
    });
  } catch (error) {
    if (error instanceof ApiError) return fail(error);
    return fail(new ApiError(500, { code: "internal_error", message: "Widget config failed." }));
  }
}
