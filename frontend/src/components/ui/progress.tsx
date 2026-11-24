import * as React from "react";
import { cn } from "@/lib/utils";

export function Progress({
  value,
  className,
  indeterminate,
}: {
  value?: number;
  className?: string;
  indeterminate?: boolean;
}) {
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : value}
      className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      {indeterminate ? (
        <div className="absolute inset-y-0 left-0 w-1/3 animate-shimmer bg-primary/70" />
      ) : (
        <div
          className="h-full bg-primary transition-[width] duration-500"
          style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }}
        />
      )}
    </div>
  );
}
