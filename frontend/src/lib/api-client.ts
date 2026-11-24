/**
 * Browser-side client for the BFF. Keeps one fetch wrapper so every screen
 * handles errors, abort signals and content types the same way.
 */
import { ApiError } from "./errors";

type ClientInit = RequestInit & { json?: unknown };

export async function apiFetch<T = unknown>(path: string, init: ClientInit = {}): Promise<T> {
  const headers = new Headers(init.headers as HeadersInit | undefined);
  headers.set("Accept", "application/json");
  let body: BodyInit | undefined = init.body as BodyInit | undefined;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, body, cache: "no-store" });
  } catch (err) {
    if ((err as DOMException)?.name === "AbortError") throw err;
    throw new ApiError(0, { code: "network_error", message: "We couldn't reach the server." });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      /* non-JSON body is treated as empty */
    }
  }

  if (!response.ok) {
    const shape = (data ?? {}) as Record<string, unknown>;
    throw new ApiError(response.status, shape);
  }

  return data as T;
}
