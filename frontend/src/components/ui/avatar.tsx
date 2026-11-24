import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Avatar with a gradient fill derived deterministically from the name or
 * email, so the same user always lands on the same tile across sessions
 * and devices. Falls back to initials; if an image URL is passed in, it
 * decorates the gradient surface rather than replacing it, so a transparent
 * PNG never shows a jarring white rectangle on a dark backdrop.
 */
const PALETTES: Array<[string, string]> = [
  ["#6366f1", "#8b5cf6"], // indigo → violet
  ["#8b5cf6", "#ec4899"], // violet → pink
  ["#ec4899", "#f43f5e"], // pink → rose
  ["#f43f5e", "#f97316"], // rose → orange
  ["#f97316", "#eab308"], // orange → amber
  ["#06b6d4", "#3b82f6"], // cyan → blue
  ["#10b981", "#06b6d4"], // emerald → cyan
  ["#14b8a6", "#6366f1"], // teal → indigo
];

function hash(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = (h * 16777619) >>> 0;
  }
  return h;
}

export function paletteFor(seed: string): [string, string] {
  if (!seed) return PALETTES[0];
  return PALETTES[hash(seed) % PALETTES.length];
}

export function initialsFor(name: string | null | undefined, email?: string | null): string {
  const source = (name && name.trim()) || email || "?";
  return source
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

const sizeClass = {
  xs: "h-6 w-6 text-[10px]",
  sm: "h-8 w-8 text-xs",
  md: "h-9 w-9 text-sm",
  lg: "h-11 w-11 text-base",
  xl: "h-14 w-14 text-lg",
} as const;

export function Avatar({
  name,
  email,
  src,
  size = "md",
  className,
  ring = false,
  status,
}: {
  name?: string | null;
  email?: string | null;
  src?: string | null;
  size?: keyof typeof sizeClass;
  className?: string;
  ring?: boolean;
  status?: "online" | "away" | "offline";
}) {
  const seed = (name || email || "unknown").toLowerCase();
  const [a, b] = paletteFor(seed);
  const initials = initialsFor(name, email);
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold text-white",
        sizeClass[size],
        ring && "ring-2 ring-background ring-offset-1 ring-offset-primary/30",
        className
      )}
      style={{ background: `linear-gradient(135deg, ${a}, ${b})` }}
      aria-hidden={!name && !email ? undefined : true}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className="leading-none">{initials || "?"}</span>
      )}
      {status && (
        <span
          aria-hidden
          className={cn(
            "absolute bottom-0 right-0 h-2 w-2 rounded-full border-2 border-card",
            status === "online" && "bg-success",
            status === "away" && "bg-warning",
            status === "offline" && "bg-muted-foreground"
          )}
        />
      )}
    </span>
  );
}
