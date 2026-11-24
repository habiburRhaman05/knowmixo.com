"use client";
import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Google sign-in button. Styled to match Google's human-interface guidance
 * (neutral surface, Google G mark, "Continue with Google" label) so users
 * recognize it instantly, but using our sizing and radius so it sits with
 * the rest of the form.
 */
type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean };

export const GoogleButton = React.forwardRef<HTMLButtonElement, Props>(
  ({ className, loading, disabled, children = "Continue with Google", ...props }, ref) => (
    <button
      type="button"
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "relative inline-flex h-10 w-full items-center justify-center gap-3 rounded-lg border border-border bg-card px-4 text-sm font-medium text-foreground shadow-sm transition-colors",
        "hover:bg-subtle hover:border-muted-foreground/30",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:opacity-60 disabled:cursor-not-allowed",
        className
      )}
      {...props}
    >
      {loading ? (
        <span
          aria-hidden
          className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      ) : (
        <GoogleG />
      )}
      <span>{children}</span>
    </button>
  )
);
GoogleButton.displayName = "GoogleButton";

function GoogleG() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.56c2.08-1.92 3.28-4.74 3.28-8.09Z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.76c-.99.66-2.25 1.06-3.72 1.06-2.86 0-5.28-1.93-6.15-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
        fill="#34A853"
      />
      <path
        d="M5.85 14.11A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.35-2.11V7.05H2.18A11 11 0 0 0 1 12c0 1.77.42 3.45 1.18 4.95l3.67-2.84Z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.07.56 4.21 1.65l3.15-3.15C17.46 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.05l3.67 2.84C6.72 7.3 9.14 5.38 12 5.38Z"
        fill="#EA4335"
      />
    </svg>
  );
}
