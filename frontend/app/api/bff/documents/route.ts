import { backend } from "@/lib/backend";
import { fail, ok } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const qs = url.search; // forward state/type/q/cursor/limit verbatim
    const { data, status } = await backend<unknown>(`/api/v1/documents${qs}`);
    return ok(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}
