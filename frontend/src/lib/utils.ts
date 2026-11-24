import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Standard shadcn-style class merge helper. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Short, user-safe time delta strings ("2m ago", "in 3h"). Locale-neutral. */
export function fromNow(input: string | Date | number): string {
  const date = input instanceof Date ? input : new Date(input);
  const diff = date.getTime() - Date.now();
  const abs = Math.abs(diff);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60 * 1000, "second"],
    [60 * 60 * 1000, "minute"],
    [24 * 60 * 60 * 1000, "hour"],
    [7 * 24 * 60 * 60 * 1000, "day"],
    [30 * 24 * 60 * 60 * 1000, "week"],
    [365 * 24 * 60 * 60 * 1000, "month"],
    [Number.POSITIVE_INFINITY, "year"],
  ];
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (let i = 0; i < units.length; i++) {
    if (abs < units[i][0]) {
      const divisor = i === 0 ? 1000 : units[i - 1][0];
      return fmt.format(Math.round(diff / divisor), units[i][1]);
    }
  }
  return fmt.format(0, "second");
}

/** Keep a short, safe identifier for aria-describedby / data-* props. */
export function slug(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 48);
}
