"use client";
import * as React from "react";
import Link from "next/link";
import { Cookie } from "lucide-react";

const STORAGE_KEY = "knowmivo-cookie-consent";

/**
 * D.2.5 (launch requirement): a simple accept/reject cookie-consent
 * banner. We only set functional cookies (session auth, visitor chat
 * sessions) and no third-party ad-tracking cookies today, so "reject"
 * just dismisses the banner without disabling anything -- there is
 * nothing non-essential to turn off yet. Persisted in localStorage only
 * (never sent to the backend, never read by Claude); if storage is
 * unavailable (private browsing) the banner just reappears next visit,
 * which is an acceptable degradation, not a broken feature.
 */
export function CookieConsent() {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    try {
      if (!window.localStorage.getItem(STORAGE_KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  function dismiss() {
    setVisible(false);
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* private browsing or storage disabled -- banner just reappears next visit */
    }
  }

  if (!visible) return null;

  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-card/95 px-4 py-4 shadow-elevated backdrop-blur-sm sm:px-6"
    >
      <div className="mx-auto flex max-w-5xl flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-2.5 text-sm text-foreground">
          <Cookie aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <p>
            We use essential cookies to keep you signed in and to run chat sessions. We don&apos;t use
            advertising cookies.{" "}
            <Link href="/privacy" className="underline hover:text-primary">
              Learn more
            </Link>
            .
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={dismiss}
            className="inline-flex h-9 items-center rounded-lg border border-border bg-card px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted"
          >
            Dismiss
          </button>
          <button
            type="button"
            onClick={dismiss}
            className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm transition hover:brightness-110"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
