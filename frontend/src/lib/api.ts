import { tokenFor } from "./session";
import type { Created, Health, Issue, Meta, PublicConfig, Summary } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  errors?: Issue[];
  errorCount?: number;
  warnings?: Issue[];

  constructor(
    status: number,
    code: string,
    message: string,
    extra: { errors?: Issue[]; errorCount?: number; warnings?: Issue[] } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    Object.assign(this, extra);
  }
}

interface Options {
  signal?: AbortSignal;
}

function isAbort(error: unknown, signal?: AbortSignal): boolean {
  return (
    signal?.aborted === true ||
    (error instanceof Error && error.name === "AbortError")
  );
}

function unknownError(status: number): ApiError {
  return new ApiError(status, "unknown_error", "The server sent an unexpected response.");
}

function errorFrom(status: number, body: unknown): ApiError {
  const error =
    typeof body === "object" && body !== null
      ? (body as { error?: unknown }).error
      : undefined;
  if (typeof error !== "object" || error === null) return unknownError(status);
  const { code, message } = error as { code?: unknown; message?: unknown };
  if (typeof code !== "string" || typeof message !== "string") {
    return unknownError(status);
  }
  if (status === 422) {
    const detail = error as {
      errors?: Issue[];
      error_count?: number;
      warnings?: Issue[];
    };
    return new ApiError(status, code, message, {
      errors: detail.errors,
      errorCount: detail.error_count,
      warnings: detail.warnings,
    });
  }
  return new ApiError(status, code, message);
}

async function send(
  url: string,
  init: RequestInit,
  signal: AbortSignal | undefined,
): Promise<Response> {
  try {
    return await fetch(url, { ...init, signal });
  } catch (error) {
    if (isAbort(error, signal)) throw error;
    throw new ApiError(0, "network_error", "The server could not be reached.");
  }
}

async function readJson(response: Response, signal?: AbortSignal): Promise<unknown> {
  try {
    return await response.json();
  } catch (error) {
    if (isAbort(error, signal)) throw error;
    return undefined;
  }
}

async function request<T>(
  method: string,
  url: string,
  { signal, body, datasetId }: Options & { body?: FormData; datasetId?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (datasetId !== undefined) {
    const token = tokenFor(datasetId);
    if (token !== null) headers.Authorization = `Bearer ${token}`;
  }
  const response = await send(url, { method, headers, body }, signal);
  if (!response.ok) {
    throw errorFrom(response.status, await readJson(response, signal));
  }
  if (response.status === 204) return undefined as T;
  const data = await readJson(response, signal);
  if (data === undefined) throw unknownError(response.status);
  return data as T;
}

const datasetUrl = (id: string) => `/api/datasets/${encodeURIComponent(id)}`;

export function getHealth(options: Options = {}): Promise<Health> {
  return request("GET", "/api/health", options);
}

const isLimit = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value > 0;

export async function getConfig(options: Options = {}): Promise<PublicConfig> {
  const data = await request<unknown>("GET", "/api/config", options);
  const config = (typeof data === "object" && data !== null ? data : {}) as Record<string, unknown>;
  const { public_demo_mode, max_upload_bytes, max_rows } = config;
  if (typeof public_demo_mode !== "boolean" || !isLimit(max_upload_bytes) || !isLimit(max_rows)) {
    throw unknownError(200);
  }
  return { public_demo_mode, max_upload_bytes, max_rows };
}

export function createDatasetFromUpload(
  file: File,
  currency: string,
  options: Options = {},
): Promise<Created> {
  const form = new FormData();
  form.append("currency", currency);
  form.append("file", file);
  return request("POST", "/api/datasets", { ...options, body: form });
}

export function createSampleDataset(options: Options = {}): Promise<Created> {
  return request("POST", "/api/datasets/sample", options);
}

export function getMeta(id: string, options: Options = {}): Promise<Meta> {
  return request("GET", datasetUrl(id), { ...options, datasetId: id });
}

export function getAnalytics(
  id: string,
  range: { start?: string; end?: string } = {},
  options: Options = {},
): Promise<Summary> {
  const params = new URLSearchParams();
  if (range.start !== undefined) params.set("start", range.start);
  if (range.end !== undefined) params.set("end", range.end);
  const query = params.size > 0 ? `?${params}` : "";
  return request("GET", `${datasetUrl(id)}/analytics${query}`, {
    ...options,
    datasetId: id,
  });
}

export function deleteDataset(id: string, options: Options = {}): Promise<void> {
  return request("DELETE", datasetUrl(id), { ...options, datasetId: id });
}
