import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ApiError, createDatasetFromUpload, createSampleDataset, getAnalytics, getMeta } from "./api";
import { describeError, errorKind } from "./errors";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

// The bodies below were captured from the real backend (through the dev proxy).
const NOT_FOUND = { error: { code: "not_found", message: "The dataset was not found." } };
const UNAUTHORIZED = { error: { code: "unauthorized", message: "A valid bearer token is required." } };
const INVALID_RANGE = { error: { code: "invalid_range", message: "start must not be after end." } };
const INVALID_REQUEST = { error: { code: "invalid_request", message: "A file part named 'file' is required." } };
const UPLOAD_DISABLED = {
  error: {
    code: "upload_disabled",
    message: "Uploads are disabled on this demo. Upload your own file with the self-hosted version.",
  },
};
const INTERNAL = { error: { code: "internal_error", message: "Something went wrong on the server." } };

function answer(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status }),
  );
}

async function caught(call: () => Promise<unknown>): Promise<unknown> {
  try {
    await call();
  } catch (error) {
    return error;
  }
  throw new Error("expected the call to fail");
}

const file = new File(["a"], "sales.csv");

test("a 404 answer is expired", async () => {
  answer(404, NOT_FOUND);
  const error = await caught(() => getMeta("d1"));
  expect(describeError(error)).toEqual({ kind: "expired", message: "This dataset has expired or was deleted" });
  answer(404, NOT_FOUND);
  expect(errorKind(await caught(() => getAnalytics("d1")))).toBe("expired");
});

test("a 401 answer is unauthorized", async () => {
  answer(401, UNAUTHORIZED);
  expect(describeError(await caught(() => getMeta("d1")))).toEqual({
    kind: "unauthorized",
    message: "This dataset cannot be opened from this browser session",
  });
});

test("a 400 invalid_range from analytics is bad_range and shows no server text", async () => {
  answer(400, INVALID_RANGE);
  const described = describeError(await caught(() => getAnalytics("d1", { start: "2025-02-01", end: "2025-01-01" })));
  expect(described).toEqual({
    kind: "bad_range",
    message: "The selected date range is not valid for this dataset",
  });
  expect(described.message).not.toContain("start must");
});

test("a 403 upload_disabled is upload_disabled: the server's message and the sample hint", async () => {
  answer(403, UPLOAD_DISABLED);
  const described = describeError(await caught(() => createDatasetFromUpload(file, "USD")), "upload");
  expect(described.kind).toBe("upload_disabled");
  expect(described.message).toBe(`${UPLOAD_DISABLED.error.message} You can still use Try sample data.`);
});

test("a 403 with another code is failed", () => {
  expect(errorKind(new ApiError(403, "forbidden", "no"))).toBe("failed");
});

test("a 400 invalid_request from upload is bad_request and shows the server's message", async () => {
  answer(400, INVALID_REQUEST);
  const described = describeError(await caught(() => createDatasetFromUpload(file, "USD")), "upload");
  expect(described).toEqual({ kind: "bad_request", message: "A file part named 'file' is required." });
});

test("a 500 answer is failed, with the sentence of its context", async () => {
  answer(500, INTERNAL);
  const error = await caught(() => getMeta("d1"));
  expect(describeError(error)).toEqual({ kind: "failed", message: "Something went wrong loading this data" });
  expect(describeError(error, "upload")).toEqual({
    kind: "failed",
    message: "Something went wrong — your file was not imported",
  });
  expect(describeError(error, "sample")).toEqual({
    kind: "failed",
    message: "Something went wrong — the sample data could not be loaded",
  });
});

test("a 502 with an HTML body is unknown_error and failed", async () => {
  answer(502, "<html><body>Bad Gateway</body></html>");
  const error = await caught(() => getMeta("d1"));
  expect(error).toMatchObject({ status: 502, code: "unknown_error" });
  expect(describeError(error).kind).toBe("failed");
  expect(describeError(error).message).not.toMatch(/html|502|Bad Gateway/i);
});

test("a 502 with an empty body (the dev proxy, backend stopped) is failed", async () => {
  answer(502, "");
  expect(describeError(await caught(() => getMeta("d1"))).kind).toBe("failed");
});

test("a network failure is failed", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  const error = await caught(() => getMeta("d1"));
  expect(error).toMatchObject({ status: 0, code: "network_error" });
  expect(describeError(error)).toEqual({ kind: "failed", message: "Something went wrong loading this data" });
});

test("a 422 without an errors array is failed", async () => {
  answer(422, { error: { code: "validation_failed", message: "The file has problems." } });
  const error = await caught(() => createDatasetFromUpload(file, "USD"));
  expect(describeError(error, "upload")).toEqual({
    kind: "failed",
    message: "Something went wrong — your file was not imported",
  });
});

test("a value that is not an ApiError is failed", () => {
  for (const value of [new Error("boom"), "text", null, undefined, { status: 404 }]) {
    expect(describeError(value).kind).toBe("failed");
  }
});

test("a sample failure always says the sample could not be loaded, whatever the kind", async () => {
  answer(403, UPLOAD_DISABLED);
  const error = await caught(() => createSampleDataset());
  expect(describeError(error, "sample")).toEqual({
    kind: "upload_disabled",
    message: "Something went wrong — the sample data could not be loaded",
  });
});

test("no message carries a status code, a server code or a stack", () => {
  const errors = [
    new ApiError(404, "not_found", "The dataset was not found."),
    new ApiError(401, "unauthorized", "A valid bearer token is required."),
    new ApiError(400, "invalid_range", "start must not be after end."),
    new ApiError(500, "internal_error", "Something went wrong on the server."),
    new ApiError(0, "network_error", "The server could not be reached."),
    new ApiError(502, "unknown_error", "The server sent an unexpected response."),
  ];
  for (const error of errors) {
    const { message } = describeError(error);
    expect(message).not.toContain(error.code);
    expect(message).not.toMatch(/\b(0|400|401|404|500|502)\b|\bat .*\(|\{/);
  }
});

test("a 400 with an unexpected code from analytics is still bad_range", () => {
  expect(errorKind(new ApiError(400, "whatever", "x"))).toBe("bad_range");
});
