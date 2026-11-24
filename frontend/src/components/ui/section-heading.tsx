import * as React from "react";
import { cn } from "@/lib/utils";

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "left",
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "space-y-3",
        align === "center" ? "text-center mx-auto max-w-2xl" : "",
        className
      )}
    >
      {eyebrow && (
        <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-accent px-3 py-1 text-xs font-medium uppercase tracking-wide text-accent-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
          {eyebrow}
        </span>
      )}
      <h1 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      {description && <p className="text-base leading-relaxed text-muted-foreground">{description}</p>}
    </div>
  );
}
