import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Inline keyboard-key chip. Small, monospace, border-inset so it reads as
 * a physical key. Collapses `Mod` into `⌘` on Mac and `Ctrl` elsewhere so
 * copy stays the same cross-platform.
 */
export function Kbd({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-md border border-border bg-subtle px-1.5 text-[10px] font-medium text-muted-foreground shadow-[0_1px_0_0_hsl(var(--border))]",
        className
      )}
    >
      {children}
    </kbd>
  );
}

export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform);
}

export function modKey(): string {
  return isMac() ? "⌘" : "Ctrl";
}
