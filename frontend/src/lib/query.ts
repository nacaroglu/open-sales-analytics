import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api";

// Three requests in all (the first and two retries) for a failure that may pass:
// 5xx, network, unreadable answer. A request the server answered with a 4xx
// will not change on retry.
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export const queryDefaults = {
  queries: {
    retry: shouldRetry,
    // The metadata is fetched once per visit, not again on tab focus.
    refetchOnWindowFocus: false,
  },
};

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: queryDefaults });
}
