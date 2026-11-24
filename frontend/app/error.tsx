"use client";
import * as React from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Top-level app error boundary. Keeps the page shell visible, never shows
 * a raw stack trace to the user. The digest is the only non-sensitive
 * identifier Next.js exposes; we show it so users can quote it in support.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // Give this one line of signal to the browser console so devs can find
    // the entry in their logs. No stack is printed by default.
    if (typeof console !== "undefined") console.error("[knowmivo]", error?.message);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md space-y-6 rounded-xl border border-border bg-card p-8 shadow-elevated">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
            <AlertTriangle aria-hidden className="h-5 w-5" />
          </span>
          <div className="space-y-1">
            <h1 className="font-display text-xl font-semibold">Something went wrong</h1>
            <p className="text-sm text-muted-foreground">
              We&apos;ve logged the error. Please try the page again, or go back to the overview.
            </p>
          </div>
        </div>
        {error?.digest && (
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            Reference: <code className="font-mono">{error.digest}</code>
          </p>
        )}
        <div className="flex gap-2">
          <Button onClick={reset} variant="primary" block>
            <RefreshCw className="h-4 w-4" /> Try again
          </Button>
          <Button asChild variant="secondary" block>
            <Link href="/overview">
              <Home className="h-4 w-4" /> Overview
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
