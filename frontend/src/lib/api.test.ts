import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
  ApiError,
  createDatasetFromUpload,
  createSampleDataset,
  deleteDataset,
  getAnalytics,
  getConfig,
  getHealth,
  getMeta,
} from "./api";
import { saveSession } from "./session";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastCall(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url, init };
}

function headersOf(init: RequestInit): Headers {
  return new Headers(init.headers);
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected a rejection");
}

test("health requests a relative URL and returns the body", async () => {
  fetchMock.mockResolvedValue(json({ status: "ok" }));

  await expect(getHealth()).resolves.toEqual({ status: "ok" });
  expect(lastCall().url).toBe("/api/health");
});

test("upload sends multipart with currency before file and no Content-Type", async () => {
  fetchMock.mockResolvedValue(json({ dataset_id: "d1" }, 201));
  const file = new File(["a,b\n1,2\n"], "sales.csv", { type: "text/csv" });

  await createDatasetFromUpload(file, "EUR");

  const { url, init } = lastCall();
  expect(url).toBe("/api/datasets");
  expect(init.method).toBe("POST");
  expect(headersOf(init).has("Content-Type")).toBe(false);
  const form = init.body as FormData;
  expect(form).toBeInstanceOf(FormData);
  expect([...form.keys()]).toEqual(["currency", "file"]);
  expect(form.get("currency")).toBe("EUR");
  expect((form.get("file") as File).name).toBe("sales.csv");
});

test("sample sends no body", async () => {
  fetchMock.mockResolvedValue(json({ dataset_id: "d1" }, 201));

  await createSampleDataset();

  const { url, init } = lastCall();
  expect(url).toBe("/api/datasets/sample");
  expect(init.method).toBe("POST");
  expect(init.body ?? null).toBeNull();
});

test("creation requests never send Authorization, even with a stored token", async () => {
  saveSession({ id: "old", token: "old-token" });
  fetchMock.mockImplementation(async () => json({ dataset_id: "d1" }, 201));

  await createSampleDataset();
  expect(headersOf(lastCall().init).has("Authorization")).toBe(false);

  await createDatasetFromUpload(new File(["x"], "a.csv"), "USD");
  expect(headersOf(lastCall().init).has("Authorization")).toBe(false);
});

test("dataset requests carry the bearer token for the stored ID", async () => {
  saveSession({ id: "d1", token: "tok" });
  fetchMock.mockImplementation(async () => json({}));

  await getMeta("d1");
  expect(lastCall().url).toBe("/api/datasets/d1");
  expect(headersOf(lastCall().init).get("Authorization")).toBe("Bearer tok");

  await getAnalytics("d1");
  expect(headersOf(lastCall().init).get("Authorization")).toBe("Bearer tok");

  fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
  await deleteDataset("d1");
  expect(lastCall().init.method).toBe("DELETE");
  expect(headersOf(lastCall().init).get("Authorization")).toBe("Bearer tok");
});

test("no Authorization when nothing is stored or the stored ID differs", async () => {
  fetchMock.mockImplementation(async () => json({}));

  await getMeta("d1");
  expect(headersOf(lastCall().init).has("Authorization")).toBe(false);

  saveSession({ id: "other", token: "tok" });
  await getMeta("d1");
  await getAnalytics("d1");
  expect(headersOf(lastCall().init).has("Authorization")).toBe(false);
  fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
  await deleteDataset("d1");
  expect(headersOf(lastCall().init).has("Authorization")).toBe(false);
});

test("the token never appears in a request URL", async () => {
  saveSession({ id: "d1", token: "tok-secret" });
  fetchMock.mockImplementation(async () => json({}));

  await getMeta("d1");
  await getAnalytics("d1", { start: "2026-01-01", end: "2026-01-31" });

  for (const [url] of fetchMock.mock.calls) {
    expect(url).not.toContain("tok-secret");
  }
});

test("analytics sends start and end only when given", async () => {
  fetchMock.mockImplementation(async () => json({}));

  await getAnalytics("d1");
  expect(lastCall().url).toBe("/api/datasets/d1/analytics");

  await getAnalytics("d1", { start: "2026-01-01" });
  expect(lastCall().url).toBe("/api/datasets/d1/analytics?start=2026-01-01");

  await getAnalytics("d1", { end: "2026-01-31" });
  expect(lastCall().url).toBe("/api/datasets/d1/analytics?end=2026-01-31");

  await getAnalytics("d1", { start: "2026-01-01", end: "2026-01-31" });
  expect(lastCall().url).toBe(
    "/api/datasets/d1/analytics?start=2026-01-01&end=2026-01-31",
  );
});

test("delete resolves on an empty 204 without parsing", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

  await expect(deleteDataset("d1")).resolves.toBeUndefined();
});

test("a non-2xx response rejects with status, code and message", async () => {
  fetchMock.mockResolvedValue(
    json({ error: { code: "not_found", message: "The dataset was not found." } }, 404),
  );

  const error = await rejection(getMeta("d1"));

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({
    status: 404,
    code: "not_found",
    message: "The dataset was not found.",
  });
});

test("a 422 also carries errors, errorCount and warnings", async () => {
  const issue = { code: "bad", reason: "Bad value", row_number: 2, field: "qty" };
  const warning = { code: "warn", reason: "Odd", row_number: null, field: null };
  fetchMock.mockResolvedValue(
    json(
      {
        error: {
          code: "validation_failed",
          message: "Fix the file.",
          errors: [issue],
          error_count: 250,
          warnings: [warning],
        },
      },
      422,
    ),
  );

  const error = (await rejection(
    createDatasetFromUpload(new File(["x"], "a.csv"), "USD"),
  )) as ApiError;

  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(422);
  expect(error.code).toBe("validation_failed");
  expect(error.errors).toEqual([issue]);
  expect(error.errorCount).toBe(250);
  expect(error.warnings).toEqual([warning]);
});

test("an HTML error response becomes unknown_error", async () => {
  fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));

  const error = await rejection(getHealth());

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 502, code: "unknown_error" });
  expect((error as ApiError).message).not.toBe("");
});

test("JSON without an error object becomes unknown_error", async () => {
  fetchMock.mockResolvedValue(json({ detail: "nope" }, 500));

  await expect(getHealth()).rejects.toMatchObject({
    status: 500,
    code: "unknown_error",
  });
});

test("a network failure becomes network_error with status 0", async () => {
  fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

  const error = await rejection(getHealth());

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 0, code: "network_error" });
});

test("an aborted request rejects with the abort error unchanged", async () => {
  const controller = new AbortController();
  fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
    return new Promise((_, reject) => {
      init.signal!.addEventListener("abort", () => reject(init.signal!.reason));
    });
  });

  const pending = rejection(getMeta("d1", { signal: controller.signal }));
  controller.abort();
  const error = await pending;

  expect(error).not.toBeInstanceOf(ApiError);
  expect((error as Error).name).toBe("AbortError");
  expect(lastCall().init.signal).toBe(controller.signal);
});

// Real bodies of GET /api/config from a running server.
const REAL_DEFAULTS = { public_demo_mode: false, max_upload_bytes: 52428800, max_rows: 500000 };
const REAL_DEMO = { public_demo_mode: true, max_upload_bytes: 1000, max_rows: 10 };

test("getConfig calls GET /api/config with no Authorization header and returns the three values", async () => {
  saveSession({ id: "d1", token: "tok" });
  fetchMock.mockResolvedValue(json(REAL_DEFAULTS));

  expect(await getConfig()).toEqual(REAL_DEFAULTS);

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const { url, init } = lastCall();
  expect(url).toBe("/api/config");
  expect(init.method).toBe("GET");
  expect(headersOf(init).has("Authorization")).toBe(false);
  expect(init.body).toBeUndefined();
});

test("getConfig returns a demo-mode body as sent and passes the abort signal on", async () => {
  fetchMock.mockResolvedValue(json(REAL_DEMO));
  const controller = new AbortController();

  expect(await getConfig({ signal: controller.signal })).toEqual(REAL_DEMO);
  expect(lastCall().init.signal).toBe(controller.signal);
});

test("getConfig drops keys it does not know", async () => {
  fetchMock.mockResolvedValue(json({ ...REAL_DEFAULTS, dataset_dir: "/secret" }));
  expect(await getConfig()).toEqual(REAL_DEFAULTS);
});

test.each([
  ["a body that is not JSON", () => new Response("<html>spa</html>", { status: 200 })],
  ["null", () => json(null)],
  ["an array", () => json([REAL_DEFAULTS])],
  ["a string", () => json("config")],
  ["an empty object", () => json({})],
  ["a missing flag", () => json({ max_upload_bytes: 1000, max_rows: 10 })],
  ["a missing size", () => json({ public_demo_mode: false, max_rows: 10 })],
  ["a missing row limit", () => json({ public_demo_mode: false, max_upload_bytes: 1000 })],
  ["a flag that is a string", () => json({ ...REAL_DEFAULTS, public_demo_mode: "false" })],
  ["a flag that is a number", () => json({ ...REAL_DEFAULTS, public_demo_mode: 0 })],
  ["a flag that is null", () => json({ ...REAL_DEFAULTS, public_demo_mode: null })],
  ["a size of zero", () => json({ ...REAL_DEFAULTS, max_upload_bytes: 0 })],
  ["a negative size", () => json({ ...REAL_DEFAULTS, max_upload_bytes: -1 })],
  ["a fractional size", () => json({ ...REAL_DEFAULTS, max_upload_bytes: 1.5 })],
  ["a size that is a string", () => json({ ...REAL_DEFAULTS, max_upload_bytes: "1000" })],
  ["a row limit of zero", () => json({ ...REAL_DEFAULTS, max_rows: 0 })],
  ["a fractional row limit", () => json({ ...REAL_DEFAULTS, max_rows: 2.5 })],
  ["a row limit that is null", () => json({ ...REAL_DEFAULTS, max_rows: null })],
])("getConfig treats %s as an unknown_error, not partial data", async (_name, response) => {
  fetchMock.mockResolvedValue(response());

  const error = await rejection(getConfig());

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ code: "unknown_error" });
});

test("getConfig turns an error status or a network failure into an ApiError", async () => {
  fetchMock.mockResolvedValue(json({ error: { code: "internal_error", message: "x" } }, 500));
  expect(await rejection(getConfig())).toMatchObject({ status: 500, code: "internal_error" });

  fetchMock.mockResolvedValue(new Response("", { status: 404 }));
  expect(await rejection(getConfig())).toMatchObject({ status: 404, code: "unknown_error" });

  fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
  expect(await rejection(getConfig())).toMatchObject({ status: 0, code: "network_error" });
});
