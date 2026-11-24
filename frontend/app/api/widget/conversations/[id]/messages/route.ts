/**
 * Visitor chat stream. Proxies SSE straight through -- we do NOT parse the
 * stream here so the browser sees the events as they're produced. Response
 * body is handed off as a stream to NextResponse.
 */
import { readParentOrigin, readVisitorToken, widgetBackend } from "@/lib/widget-backend";
import { ApiError } from "@/lib/errors";
import { fail } from "@/lib/bff-response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Ctx) {
  const { id } = await params;
  try {
    const text = await request.text();
    const body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
    const idempotencyKey = request.headers.get("idempotency-key");
    const parentOrigin = readParentOrigin(request);
    const visitorToken = readVisitorToken(request);
    const { response } = await widgetBackend(
      `/api/v1/public/conversations/${encodeURIComponent(id)}/messages`,
      { method: "POST", body, visitorToken, parentOrigin, idempotencyKey, accept: "text/event-stream" }
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "text/event-stream",
        "cache-control": "no-cache, no-transform",
        "x-accel-buffering": "no",
        connection: "keep-alive",
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return fail(error);
    return fail(new ApiError(500, { code: "internal_error", message: "Message failed." }));
  }
}
