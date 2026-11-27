import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Standard width and padding for every screen inside the authenticated
 * shell, so Overview, Knowledge, Settings etc. all align the same way.
 */
export function PageShell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("w-full px-4 py-8 sm:px-6 lg:px-8", className)}>
      {children}
    </div>
  );
}
