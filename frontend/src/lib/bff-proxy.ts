/**
 * Thin BFF proxy helpers. Most of our proxy routes do nothing clever: they
 * read a session cookie, forward to the backend, and return the result. Any
 * owner-mutation route that supports an Idempotency-Key must also forward
 * that header so a client replay reaches the backend intact.
 */
import { backend } from "./backend";
import { fail, ok, readJson } from "./bff-response";

const PASSED_HEADERS = ["idempotency-key", "x-request-id"];

function forwardHeaders(request: Request): HeadersInit | undefined {
  const headers: Record<string, string> = {};
  for (const name of PASSED_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  return Object.keys(headers).length ? headers : undefined;
}

export async function proxyGet(path: string) {
  try {
    const { data, status } = await backend<unknown>(path);
    return ok(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}

export async function proxyJson(
  request: Request,
  path: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  defaultStatus = 200,
) {
  try {
    const body = method === "DELETE" ? undefined : await readJson<Record<string, unknown>>(request);
    const { data, status } = await backend<unknown>(path, {
      method,
      body,
      headers: forwardHeaders(request),
    });
    return ok(data as object, { status: status || defaultStatus });
  } catch (error) {
    return fail(error);
  }
}

export async function proxyDelete(request: Request, path: string) {
  try {
    const { data, status } = await backend<unknown>(path, {
      method: "DELETE",
      headers: forwardHeaders(request),
    });
    if (status === 204) return new Response(null, { status: 204 });
    return ok(data as object, { status });
  } catch (error) {
    return fail(error);
  }
}
