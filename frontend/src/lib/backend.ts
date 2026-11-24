/**
 * Server-only backend client used by BFF route handlers. Never import this
 * from a client component -- it reads env secrets and the session cookie.
 */
import { readSession } from "./session";
import { serverEnv } from "./env";
import { ApiError, type ApiErrorShape } from "./errors";

type FetchInit = Omit<RequestInit, "body"> & { body?: unknown };

/**
 * Call the backend. The session cookie (if any) is forwarded as a Bearer
 * token so the backend never sees our cookie and vice versa.
 */
export async function backend<T = unknown>(
  path: string,
  init: FetchInit = {}
): Promise<{ status: number; data: T; headers: Headers }> {
  const token = await readSession();
  const headers = new Headers(init.headers as HeadersInit | undefined);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(502, {
      code: "network_error",
      message: "We couldn't reach the server.",
    });
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { code: "internal_error", message: "Upstream returned an unexpected response." };
    }
  }

  if (!response.ok) {
    const shape = (data ?? {}) as Partial<ApiErrorShape> & { detail?: Partial<ApiErrorShape> };
    const merged = { ...(shape.detail ?? {}), ...shape };
    throw new ApiError(response.status, merged);
  }

  return { status: response.status, data: data as T, headers: response.headers };
}
