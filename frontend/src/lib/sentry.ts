/**
 * Day-1 (launch/13 D1.8) — lightweight Sentry hook.
 *
 * We don't bring in `@sentry/nextjs` as a hard dependency yet because the
 * package pulls a 450 kB runtime. Instead, we lazy-load it on the client
 * only when `NEXT_PUBLIC_SENTRY_DSN` is set. Server-side errors are captured
 * via the backend Sentry (app/observability.py) — frontend-only exceptions
 * (in-browser thrown errors) go through this path.
 *
 * Call `initSentryOnce()` once at the top of a client component (e.g.
 * `app/layout.tsx` wraps us in a `<SentryBoot>` client component).
 */
let booted = false;

export async function initSentryOnce(): Promise<void> {
  if (booted) return;
  booted = true;
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn || typeof window === "undefined") return;

  try {
    // Dynamic import keeps the bundle thin for installs that don't configure
    // Sentry. The package is `@sentry/browser`, added in Day 2's dependency
    // bump; until then the string is intentionally untyped so typecheck
    // still succeeds against the current lockfile.
    const Sentry = (await import(
      /* webpackChunkName: "sentry" */ /* webpackIgnore: true */
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore -- optional dependency, installed in D2.x
      "@sentry/browser"
    )) as {
      init: (opts: Record<string, unknown>) => void;
    };
    Sentry.init({
      dsn,
      environment: process.env.NODE_ENV,
      release: process.env.NEXT_PUBLIC_APP_RELEASE,
      tracesSampleRate: 0.05,
      beforeSend(event: { request?: { data?: unknown; cookies?: unknown; headers?: Record<string, string> } }) {
        if (event.request?.data) delete event.request.data;
        if (event.request?.cookies) delete event.request.cookies;
        if (event.request?.headers) {
          for (const k of Object.keys(event.request.headers)) {
            if (/^(authorization|cookie|set-cookie|x-api-key)$/i.test(k)) {
              event.request.headers[k] = "[filtered]";
            }
          }
        }
        return event;
      },
    });
  } catch {
    // Browser-side import failed (package not installed or network blocked).
    // Skip silently — the app keeps running without client telemetry.
  }
}
