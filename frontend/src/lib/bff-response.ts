/**
 * Shared helpers for BFF route handlers: one response shape, one error
 * mapper, request-id forwarding.
 */
import { NextResponse } from "next/server";
import { ApiError } from "./errors";

export function ok<T>(data: T, init: { status?: number; headers?: HeadersInit } = {}) {
  return NextResponse.json(data as object, { status: init.status ?? 200, headers: init.headers });
}

export function fail(error: unknown) {
  if (error instanceof ApiError) {
    return NextResponse.json(
      {
        code: error.code,
        message: error.message,
        request_id: error.requestId,
        retry_after_seconds: error.retryAfter,
        fields: error.fields,
      },
      { status: error.status }
    );
  }
  return NextResponse.json(
    {
      code: "internal_error",
      message: "Something went wrong on our side.",
    },
    { status: 500 }
  );
}

export async function readJson<T = unknown>(request: Request): Promise<T> {
  try {
    const text = await request.text();
    if (!text) return {} as T;
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(400, { code: "invalid_json", message: "Request body wasn't valid JSON." });
  }
}
