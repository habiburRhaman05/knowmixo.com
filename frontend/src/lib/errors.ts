/**
 * Shared error contract. The backend returns `{code, message, request_id,
 * retry_after_seconds?, fields?}` (docs/16). Branch on `code`, never on
 * `message`. The frontend keeps the same shape so client code has one type
 * to handle whether the failure happened at the BFF boundary or upstream.
 */

export type ApiErrorShape = {
  code: string;
  message: string;
  request_id?: string;
  retry_after_seconds?: number;
  fields?: string[];
};

export class ApiError extends Error {
  code: string;
  status: number;
  requestId?: string;
  retryAfter?: number;
  fields?: string[];

  constructor(status: number, body: Partial<ApiErrorShape> & { code?: string; message?: string }) {
    super(body.message || "Something went wrong.");
    this.name = "ApiError";
    this.status = status;
    this.code = body.code || "unknown_error";
    this.requestId = body.request_id;
    this.retryAfter = body.retry_after_seconds;
    this.fields = body.fields;
  }
}

/**
 * User-facing copy for every error code we currently surface. Keep this one
 * list so a code only has one message (docs/16: "frontend branches on these
 * codes, never on free-text message").
 */
export const ERROR_COPY: Record<string, { title: string; message: string }> = {
  unauthenticated: {
    title: "Please sign in",
    message: "Your session has expired. Sign in again to continue.",
  },
  invalid_credentials: {
    title: "Incorrect email or password",
    message: "Double-check your email and password, or use the reset link below.",
  },
  account_disabled: {
    title: "Account disabled",
    message: "This account has been disabled. Contact support if you think this is a mistake.",
  },
  email_in_use: {
    title: "Email already registered",
    message: "An account with this email already exists. Try signing in instead.",
  },
  token_invalid: {
    title: "This link isn't valid anymore",
    message: "The link has expired or was already used. Request a new one and try again.",
  },
  reauth_required: {
    title: "Confirm your password",
    message: "For security, confirm your current password to continue.",
  },
  invalid_google_token: {
    title: "Google sign-in didn't complete",
    message: "We couldn't verify your Google account. Try again in a moment.",
  },
  google_already_linked: {
    title: "That Google account is already linked",
    message: "It's connected to another Knowmivo user. Sign in to that account first.",
  },
  rate_limited: {
    title: "Too many attempts",
    message: "Please wait a moment and try again.",
  },
  validation_error: {
    title: "Please check the highlighted fields",
    message: "A few details need fixing before we can continue.",
  },
  network_error: {
    title: "We couldn't reach the server",
    message: "Check your connection, then try again.",
  },
  internal_error: {
    title: "Something went wrong on our side",
    message: "We've logged the issue. Please try again in a moment.",
  },
};

export type DescribedError = { title: string; message: string; code: string; requestId?: string };

export function describeError(error: unknown): DescribedError {
  if (error instanceof ApiError) {
    const base = ERROR_COPY[error.code];
    return {
      title: base?.title ?? "Something went wrong",
      message: base?.message ?? error.message ?? "Please try again.",
      code: error.code,
      requestId: error.requestId,
    };
  }
  if (error instanceof Error) {
    return { title: "Something went wrong", message: error.message, code: "unknown_error" };
  }
  return { title: "Something went wrong", message: "Please try again.", code: "unknown_error" };
}
