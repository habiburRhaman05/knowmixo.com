import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Brand mark. Geometric K formed by two chevrons, meant to feel like a
 * conversation turning into an answer. SVG only -- no raster asset -- so it
 * renders perfectly at any size, light or dark.
 */
export function Logo({
  className,
  withWordmark = false,
}: {
  className?: string;
  withWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-display text-foreground", className)}>
      <span className="relative inline-flex h-8 w-8 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-primary to-[hsl(260_100%_60%)] text-primary-foreground shadow-glow">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden
          className="h-4 w-4"
        >
          <path
            d="M6 4v16"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M6 12l8-7"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M6 12l8 7"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <circle cx="18" cy="12" r="1.75" fill="currentColor" />
        </svg>
      </span>
      {withWordmark && <span className="text-base font-semibold tracking-tight">Knowmivo</span>}
    </span>
  );
}
