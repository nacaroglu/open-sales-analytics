import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getAnalytics, getConfig, getCustomers, getMeta, getOverview, getProductDetail, getProducts } from "./api";
import { tokenFor } from "./session";

export function useMeta(datasetId: string) {
  return useQuery({
    queryKey: ["meta", datasetId],
    queryFn: ({ signal }) => getMeta(datasetId, { signal }),
    enabled: tokenFor(datasetId) !== null,
  });
}

export function useAnalytics(datasetId: string, start?: string, end?: string, enabled = true) {
  return useQuery({
    queryKey: ["analytics", datasetId, start, end],
    queryFn: ({ signal }) => getAnalytics(datasetId, { start, end }, { signal }),
    enabled: enabled && tokenFor(datasetId) !== null,
    // A range change keeps the old numbers on screen until the new ones arrive.
    placeholderData: keepPreviousData,
    // Analytics never change after the import, so a range seen once is final.
    staleTime: Infinity,
  });
}

export function useOverview(datasetId: string, start?: string, end?: string, comparison = "previous_period", enabled = true) {
  const active = enabled && tokenFor(datasetId) !== null;
  return useQuery({ queryKey: active ? ["overview", datasetId, start, end, comparison] : ["meta", datasetId], queryFn: ({ signal }) => getOverview(datasetId, { start, end, comparison }, { signal }), enabled: active, placeholderData: keepPreviousData, staleTime: Infinity });
}

export function useCustomers(datasetId: string, start?: string, end?: string, comparison = "previous_period", enabled = true) {
  const active = enabled && tokenFor(datasetId) !== null;
  return useQuery({
    queryKey: ["customers", datasetId, start, end, comparison],
    queryFn: ({ signal }) => getCustomers(datasetId, { start, end, comparison }, { signal }),
    enabled: active,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: ({ signal }) => getConfig({ signal }),
    // The mode and limits change only when the operator restarts the server:
    // ask once per page load, not on focus or when coming back to "/".
    staleTime: Infinity,
    // A dead server shows the full form at once (the app default retries twice),
    // and a failure is not asked again when the page remounts.
    retry: false,
    retryOnMount: false,
  });
}

export function useProducts(datasetId: string, start?: string, end?: string, dormancyDays = "60", comparison = "previous_period") {
  return useQuery({ queryKey: ["products", datasetId, start, end, comparison, dormancyDays], queryFn: ({ signal }) => getProducts(datasetId, { start, end, comparison, dormancy_days: dormancyDays }, { signal }), enabled: tokenFor(datasetId) !== null, placeholderData: keepPreviousData, staleTime: Infinity });
}

export function useProductDetail(datasetId: string, productId: string | undefined, start?: string, end?: string, comparison = "previous_period") {
  return useQuery({ queryKey: ["product-detail", datasetId, productId, start, end, comparison], queryFn: ({ signal }) => getProductDetail(datasetId, productId ?? "", { start, end, comparison }, { signal }), enabled: tokenFor(datasetId) !== null && productId !== undefined, placeholderData: keepPreviousData, staleTime: Infinity });
}
