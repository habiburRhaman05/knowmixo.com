import { backend } from "@/lib/backend";
import { fail, ok } from "@/lib/bff-response";

export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const qs = new URL(request.url).search;
    const { data, status } = await backend<unknown>(`/api/v1/conversations${qs}`);
    return ok(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}
