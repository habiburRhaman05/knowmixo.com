"use client";
import * as React from "react";

/**
 * Lightweight polling hook. Only polls while `enabled` is true, stops when
 * the tab is hidden, pauses on visibility loss, and uses a steady interval
 * (no exponential backoff -- short-lived ingestion jobs usually finish in
 * 10-60 s, so burning one request every 3 s for a minute is cheap).
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true
): { data: T | null; error: unknown; refresh: () => void } {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [tick, setTick] = React.useState(0);
  const fetcherRef = React.useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = React.useCallback(() => setTick((t) => t + 1), []);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let hidden = typeof document !== "undefined" ? document.hidden : false;

    async function run() {
      try {
        const next = await fetcherRef.current();
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    void run();

    const id = window.setInterval(() => {
      if (!hidden) void run();
    }, intervalMs);
    const onVisibility = () => {
      hidden = document.hidden;
      if (!hidden) void run();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, intervalMs, tick]);

  return { data, error, refresh };
}
