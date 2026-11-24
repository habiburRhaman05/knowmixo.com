import * as React from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ElementType;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-subtle/60 p-10 text-center",
        className
      )}
    >
      {Icon && (
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
          <Icon aria-hidden className="h-5 w-5" />
        </span>
      )}
      <div className="space-y-1">
        <p className="font-display text-base font-semibold">{title}</p>
        {description && (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
