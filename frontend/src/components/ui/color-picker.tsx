"use client";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

const PRESETS = [
  "#6366f1", "#8b5cf6", "#ec4899", "#ef4444", "#f59e0b",
  "#10b981", "#06b6d4", "#3b82f6", "#64748b", "#18181b",
];

export interface ColorPickerProps {
  value: string;
  onChange: (hex: string) => void;
  className?: string;
}

/** Bot branding color picker (D7.1 widget config). Native <input
 * type="color"> for the picker surface (no cross-browser canvas
 * reimplementation needed) plus a validated hex field and brand presets. */
export function ColorPicker({ value, onChange, className }: ColorPickerProps) {
  const [draft, setDraft] = React.useState(value);
  const valid = HEX_RE.test(draft);

  React.useEffect(() => setDraft(value), [value]);

  const commit = (hex: string) => {
    if (HEX_RE.test(hex)) onChange(hex);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex h-10 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm input-elevated",
            className
          )}
        >
          <span className="h-5 w-5 rounded-full border border-border" style={{ backgroundColor: HEX_RE.test(value) ? value : "transparent" }} />
          <span className="font-mono text-foreground">{value}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 space-y-3">
        <input
          type="color"
          value={HEX_RE.test(draft) ? draft : "#000000"}
          onChange={(e) => {
            setDraft(e.target.value);
            commit(e.target.value);
          }}
          className="h-10 w-full cursor-pointer rounded-md border border-border bg-transparent"
          aria-label="Pick a color"
        />
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => commit(draft)}
          placeholder="#6366f1"
          aria-invalid={!valid || undefined}
          className="font-mono"
        />
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((hex) => (
            <button
              key={hex}
              type="button"
              aria-label={hex}
              onClick={() => {
                setDraft(hex);
                commit(hex);
              }}
              className={cn(
                "h-6 w-6 rounded-full border border-border transition-transform hover:scale-110",
                value.toLowerCase() === hex && "ring-2 ring-ring ring-offset-2 ring-offset-popover"
              )}
              style={{ backgroundColor: hex }}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
