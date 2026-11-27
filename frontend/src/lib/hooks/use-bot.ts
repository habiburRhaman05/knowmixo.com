import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { BotResponse } from "@/lib/types";

export const BOT_QUERY_KEY = ["bot"] as const;

/** Shared across every page that reads the company's bot (Onboarding,
 * Chatbot, Chatbot publish, Actions) so it's fetched once per session
 * instead of once per page mount. */
export function useBot() {
  return useQuery({
    queryKey: BOT_QUERY_KEY,
    queryFn: () => apiFetch<BotResponse>("/api/bff/bot"),
  });
}

/** Call after any mutation that changes the bot (saving the draft,
 * publishing) so every other mounted page sees the fresh value instead
 * of a stale cached one. */
export function useInvalidateBot() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: BOT_QUERY_KEY });
}

/** Optimistically write a known-fresh bot response straight into the
 * cache (e.g. right after a successful PATCH) instead of waiting on a
 * refetch round trip. */
export function useSetBotData() {
  const queryClient = useQueryClient();
  return (bot: BotResponse) => queryClient.setQueryData(BOT_QUERY_KEY, bot);
}
