import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getAnalytics, getConfig, getMeta } from "./api";
import { tokenFor } from "./session";

export function useMeta(datasetId: string) {
  return useQuery({
    queryKey: ["meta", datasetId],
    queryFn: ({ signal }) => getMeta(datasetId, { signal }),
    enabled: tokenFor(datasetId) !== null,
  });
}

export function useAnalytics(datasetId: string, start?: string, end?: string) {
  return useQuery({
    queryKey: ["analytics", datasetId, start, end],
    queryFn: ({ signal }) => getAnalytics(datasetId, { start, end }, { signal }),
    enabled: tokenFor(datasetId) !== null,
    // A range change keeps the old numbers on screen until the new ones arrive.
    placeholderData: keepPreviousData,
    // Analytics never change after the import, so a range seen once is final.
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
