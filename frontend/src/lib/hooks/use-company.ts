import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { CompanyResponse } from "@/lib/types";

export const COMPANY_QUERY_KEY = ["company"] as const;

/** Shared across every page that reads company details (sidebar,
 * Settings, Onboarding) so it's fetched once per session instead of
 * once per page mount. */
export function useCompany() {
  return useQuery({
    queryKey: COMPANY_QUERY_KEY,
    queryFn: () => apiFetch<CompanyResponse>("/api/bff/company"),
  });
}

export function useInvalidateCompany() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: COMPANY_QUERY_KEY });
}

export function useSetCompanyData() {
  const queryClient = useQueryClient();
  return (company: CompanyResponse) => queryClient.setQueryData(COMPANY_QUERY_KEY, company);
}
