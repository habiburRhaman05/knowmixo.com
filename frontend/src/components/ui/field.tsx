"use client";
import * as React from "react";
import { cn } from "@/lib/utils";
import { Label } from "./label";
import { AlertCircle } from "lucide-react";
import { slug } from "@/lib/utils";

/**
 * Field pairs a label, control, optional hint and inline error. Keeps the
 * aria-wiring correct (label htmlFor, aria-describedby for hint/error,
 * aria-invalid on error) so every form has the same accessible shape.
 */
export type FieldProps = {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  required?: boolean;
  optional?: boolean;
  children: (props: {
    id: string;
    "aria-describedby": string | undefined;
    "aria-invalid": boolean | undefined;
  }) => React.ReactNode;
  className?: string;
};

export function Field({ label, hint, error, required, optional, children, className }: FieldProps) {
  const base = React.useId();
  const id = `${slug(label)}-${base}`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>
          {label}
          {required && (
            <span aria-hidden className="ml-0.5 text-destructive">
              *
            </span>
          )}
        </Label>
        {optional && !required && (
          <span className="text-xs text-muted-foreground">Optional</span>
        )}
      </div>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && !error && (
        <div id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </div>
      )}
      {error && (
        <p id={errorId} className="flex items-center gap-1 text-xs text-destructive" role="alert">
          <AlertCircle aria-hidden className="h-3 w-3 shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
