import { ApiError } from "./api";

// The one place that turns a thrown value into what the user is told. Pages
// and components never look at a status code or a server `code` themselves.
export type ErrorKind =
  | "expired" // 404: the dataset expired or was deleted
  | "unauthorized" // 401: the browser session has no valid token
  | "bad_range" // 400 from analytics: the range was refused
  | "upload_disabled" // 403 upload_disabled: a demo that takes no uploads
  | "bad_request" // 400 invalid_request: the request itself was refused
  | "failed"; // everything else: 5xx, network, unreadable answer, not an ApiError

// Where the error happened: loading a dataset (the default), sending a file, or
// loading the sample. It only changes the sentence of `failed` and, for the
// sample, of every kind.
export type ErrorContext = "load" | "upload" | "sample";

export interface Described {
  kind: ErrorKind;
  message: string;
}

export const EXPIRED_TITLE = "This dataset has expired or was deleted";
export const EXPIRED_SENTENCE = "Upload a file or try the sample data again.";
export const UNAUTHORIZED_TITLE = "This dataset cannot be opened from this browser session";
export const UNAUTHORIZED_SENTENCE = "Datasets can only be opened in the tab where they were created.";
export const LOAD_FAILED = "Something went wrong loading this data";
export const SECTION_FAILED = "Something went wrong showing this section";
export const BAD_RANGE = "The selected date range is not valid for this dataset";
export const UPLOAD_FAILED = "Something went wrong — your file was not imported";
export const SAMPLE_FAILED = "Something went wrong — the sample data could not be loaded";
export const UPLOAD_DISABLED_HINT = "You can still use Try sample data.";

export function errorKind(error: unknown): ErrorKind {
  if (!(error instanceof ApiError)) return "failed";
  if (error.status === 404) return "expired";
  if (error.status === 401) return "unauthorized";
  if (error.status === 400) return error.code === "invalid_request" ? "bad_request" : "bad_range";
  if (error.status === 403 && error.code === "upload_disabled") return "upload_disabled";
  return "failed";
}

function serverText(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.message.trim() !== "" ? error.message : fallback;
}

export function describeError(error: unknown, context: ErrorContext = "load"): Described {
  const kind = errorKind(error);
  if (context === "sample") return { kind, message: SAMPLE_FAILED };
  if (kind === "expired") return { kind, message: EXPIRED_TITLE };
  if (kind === "unauthorized") return { kind, message: UNAUTHORIZED_TITLE };
  if (kind === "bad_range") return { kind, message: BAD_RANGE };
  if (context === "upload") {
    if (kind === "upload_disabled") {
      return {
        kind,
        message: `${serverText(error, "Uploads are disabled on this demo.")} ${UPLOAD_DISABLED_HINT}`,
      };
    }
    if (kind === "bad_request") {
      return { kind, message: serverText(error, "The request is not valid.") };
    }
    return { kind, message: UPLOAD_FAILED };
  }
  return { kind, message: LOAD_FAILED };
}
