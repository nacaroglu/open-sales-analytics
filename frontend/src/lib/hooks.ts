import { useQuery } from "@tanstack/react-query";
import { getAnalytics, getMeta } from "./api";
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
  });
}
