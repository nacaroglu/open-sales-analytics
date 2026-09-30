import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { useAnalytics, useMeta } from "./hooks";
import { saveSession } from "./session";

const fetchMock = vi.fn();
let client: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockImplementation(
    async () => new Response(JSON.stringify({ id: "d1" }), { status: 200 }),
  );
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

test("metadata hook fetches with the token of the stored dataset", async () => {
  saveSession({ id: "d1", token: "tok" });

  const { result } = renderHook(() => useMeta("d1"), { wrapper });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/datasets/d1");
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  expect(init.signal).toBeInstanceOf(AbortSignal);
});

test("analytics hook passes start and end and uses the documented key", async () => {
  saveSession({ id: "d1", token: "tok" });

  const { result } = renderHook(
    () => useAnalytics("d1", "2026-01-01", "2026-01-31"),
    { wrapper },
  );

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(fetchMock.mock.calls[0][0]).toBe(
    "/api/datasets/d1/analytics?start=2026-01-01&end=2026-01-31",
  );
  expect(
    client.getQueryCache().find({ queryKey: ["analytics", "d1", "2026-01-01", "2026-01-31"] }),
  ).toBeDefined();
});

test("analytics key has undefined start and end for the full range", async () => {
  saveSession({ id: "d1", token: "tok" });

  const { result } = renderHook(() => useAnalytics("d1"), { wrapper });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets/d1/analytics");
  const [query] = client.getQueryCache().getAll();
  expect(query.queryKey).toEqual(["analytics", "d1", undefined, undefined]);
});

test("hooks make no request when the session has no token for that dataset", async () => {
  const { result: noSession } = renderHook(() => useMeta("d1"), { wrapper });
  expect(noSession.current.fetchStatus).toBe("idle");

  saveSession({ id: "other", token: "tok" });
  const { result: otherSession } = renderHook(() => useAnalytics("d1"), { wrapper });
  expect(otherSession.current.fetchStatus).toBe("idle");

  expect(fetchMock).not.toHaveBeenCalled();
});
