"use client";
import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Backend DB round trips run ~1-3s on this deployment (real network
 * distance to the database, not fixable client-side -- see launch notes).
 * Every page that independently re-fetched the same bot/company data on
 * every mount (Onboarding, Chatbot, Chatbot publish, Actions, Settings,
 * the sidebar) was paying that cost again on every navigation. A shared
 * query cache means that data is fetched once per session and reused,
 * only refetching when something actually invalidates it (a save,
 * publish, or an explicit refresh).
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
