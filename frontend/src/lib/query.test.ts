import { QueryClient } from "@tanstack/react-query";
import { expect, test } from "vitest";
import { ApiError } from "./api";
import { createQueryClient, queryDefaults, shouldRetry } from "./query";

const errors: [string, unknown, boolean][] = [
  ["status 0 (network_error)", new ApiError(0, "network_error", "x"), true],
  ["400", new ApiError(400, "invalid_range", "x"), false],
  ["401", new ApiError(401, "unauthorized", "x"), false],
  ["404", new ApiError(404, "not_found", "x"), false],
  ["422", new ApiError(422, "validation_failed", "x"), false],
  ["500", new ApiError(500, "internal_error", "x"), true],
  ["503", new ApiError(503, "unavailable", "x"), true],
  ["502 unknown_error", new ApiError(502, "unknown_error", "x"), true],
  ["a non-ApiError", new Error("boom"), true],
];

for (const [name, error, retried] of errors) {
  test(`${name} is ${retried ? "retried twice" : "never retried"}`, () => {
    // failureCount is the number of failures so far: 0 after the first request
    expect(shouldRetry(0, error)).toBe(retried);
    expect(shouldRetry(1, error)).toBe(retried);
    expect(shouldRetry(2, error)).toBe(false);
  });
}

test("the client defaults use shouldRetry and do not refetch on focus", () => {
  expect(queryDefaults.queries.retry).toBe(shouldRetry);
  expect(queryDefaults.queries.refetchOnWindowFocus).toBe(false);
  const defaults = createQueryClient().getDefaultOptions().queries;
  expect(defaults?.retry).toBe(shouldRetry);
  expect(defaults?.refetchOnWindowFocus).toBe(false);
});

async function requestsMade(error: unknown): Promise<number> {
  const client = new QueryClient({
    defaultOptions: { queries: { ...queryDefaults.queries, retryDelay: 0 } },
  });
  let calls = 0;
  await client
    .fetchQuery({
      queryKey: ["x"],
      queryFn: () => {
        calls += 1;
        return Promise.reject(error);
      },
    })
    .catch(() => undefined);
  return calls;
}

test("a failing 5xx query makes three requests in all, a 404 and a 401 make one", async () => {
  expect(await requestsMade(new ApiError(503, "unavailable", "x"))).toBe(3);
  expect(await requestsMade(new ApiError(0, "network_error", "x"))).toBe(3);
  expect(await requestsMade(new ApiError(404, "not_found", "x"))).toBe(1);
  expect(await requestsMade(new ApiError(401, "unauthorized", "x"))).toBe(1);
});
