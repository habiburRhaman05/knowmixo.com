"use client";
import * as React from "react";
import { Check, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Passive password strength / rule display. Mirrors the backend rule (10+
 * characters) and adds advice (not required by the backend) so people pick
 * something stronger without the UI telling the server a false "weak".
 */
const RULES: Array<{ label: string; test: (value: string) => boolean }> = [
  { label: "At least 10 characters", test: (v) => v.length >= 10 },
  { label: "Mix letters, numbers and symbols", test: (v) => /[a-zA-Z]/.test(v) && /[0-9]/.test(v) && /[^A-Za-z0-9]/.test(v) },
  { label: "Not an obvious phrase", test: (v) => !/(password|qwerty|12345)/i.test(v) },
];

export function passwordScore(value: string): number {
  return RULES.filter((r) => r.test(value)).length;
}

export function PasswordStrength({ value, className }: { value: string; className?: string }) {
  const score = passwordScore(value);
  const steps = RULES.length;
  const labels = ["Too short", "Weak", "Okay", "Strong"];
  const label = labels[score];
  const tone =
    score === 0
      ? "bg-destructive"
      : score === 1
      ? "bg-destructive"
      : score === 2
      ? "bg-warning"
      : "bg-success";

  return (
    <div className={cn("space-y-2", className)} aria-live="polite">
      <div className="flex items-center gap-1" aria-hidden>
        {Array.from({ length: steps }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-full bg-muted transition-colors",
              i < score && tone
            )}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Password strength: <span className="font-medium text-foreground">{label}</span>
      </p>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {RULES.map((r) => {
          const passed = r.test(value);
          return (
            <li key={r.label} className="flex items-center gap-1.5">
              {passed ? (
                <Check aria-hidden className="h-3 w-3 text-success" />
              ) : (
                <Minus aria-hidden className="h-3 w-3 text-muted-foreground" />
              )}
              <span className={passed ? "text-foreground" : ""}>{r.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
