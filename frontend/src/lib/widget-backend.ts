/**
 * Server-only helpers for widget (visitor) routes. Differs from the owner
 * BFF in two ways:
 *   1. The auth token is a visitor_token, carried by the browser in a
 *      Bearer header (not an httpOnly cookie) because an iframe on a
 *      third-party site cannot set cookies for our domain.
 *   2. Origin validation at the backend will reject the iframe's own
 *      origin (always our domain). We forward the parent page origin via a
 *      header the backend trusts when it carries a shared secret (B-F1 in
 *      docs/22) -- or, if no secret is configured, we fall through and let
 *      the backend's normal domain allowlist apply.
 */
import { ApiError, type ApiErrorShape } from "./errors";
import { serverEnv } from "./env";

type Opts = {
  body?: unknown;
  method?: string;
  visitorToken?: string | null;
  idempotencyKey?: string | null;
  parentOrigin?: string | null;
  accept?: string;
};

export async function widgetBackend<T = unknown>(path: string, opts: Opts = {}): Promise<{ status: number; data: T; response: Response }> {
  const base = serverEnv.backendUrl().replace(/\/$/, "");
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: Record<string, string> = { accept: opts.accept || "application/json" };
  if (opts.visitorToken) headers.authorization = `Bearer ${opts.visitorToken}`;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  if (opts.parentOrigin) headers.origin = opts.parentOrigin;
  const secret = serverEnv.trustedOriginSecret();
  if (secret && opts.parentOrigin) {
    // Both the parent-origin header AND the shared secret must be present
    // for the backend to prefer this over the raw Origin. See docs/22 B-F1.
    headers["x-bff-parent-origin"] = opts.parentOrigin;
    headers["x-bff-trust"] = secret;
  }
  const hasBody = opts.body !== undefined;
  if (hasBody) headers["content-type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(url, {
      method: opts.method ?? (hasBody ? "POST" : "GET"),
      headers,
      body: hasBody ? JSON.stringify(opts.body) : undefined,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(502, { code: "network_error", message: "We couldn't reach the server." });
  }

  // For SSE / stream responses the caller handles the body themselves.
  if ((opts.accept || "").startsWith("text/event-stream")) {
    return { status: response.status, data: undefined as T, response };
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
  return { status: response.status, data: data as T, response };
}

/** Headers browser callers send to widget routes. The visitor_token is in
 * `authorization`, parent origin (where the iframe is embedded) in
 * `x-parent-origin`. We never trust `x-parent-origin` without the paired
 * `Referer`/`Origin` sanity check further up. */
export function readVisitorToken(request: Request): string | null {
  const auth = request.headers.get("authorization") ?? "";
  if (!auth.toLowerCase().startsWith("bearer ")) return null;
  const token = auth.slice(7).trim();
  return token || null;
}

export function readParentOrigin(request: Request): string | null {
  return request.headers.get("x-parent-origin") || request.headers.get("referer") || null;
}
