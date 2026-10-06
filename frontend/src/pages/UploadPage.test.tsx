import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import UploadPage from "./UploadPage";
import { ApiError } from "../lib/api";
import { readSession } from "../lib/session";
import type { Created, Issue, PublicConfig } from "../lib/types";

const { upload, sample, config } = vi.hoisted(() => ({
  upload: vi.fn(),
  sample: vi.fn(),
  config: vi.fn(),
}));

vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  createDatasetFromUpload: upload,
  createSampleDataset: sample,
  getConfig: config,
}));

const created: Created = {
  dataset_id: "d1",
  token: "secret-token",
  meta: {
    id: "d1",
    currency: "USD",
    created_at: "2026-09-30T12:00:00Z",
    expires_at: "2026-10-01T12:00:00Z",
    row_count: 1,
    date_range: { min: "2025-01-01", max: "2025-01-01" },
  },
  warnings: [],
  initial_summary: {
    range: { start: "2025-01-01", end: "2025-01-01" },
    currency: "USD",
    granularity: "daily",
    kpis: { gross_sales: "1.0000", orders: 1, units_sold: 1, average_order_value: "1.0000" },
    trend: [],
    top_products: [],
  },
};

// Real bodies of GET /api/config from a running server (defaults, and
// PUBLIC_DEMO_MODE=true MAX_UPLOAD_BYTES=1000 MAX_ROWS=10).
const DEFAULTS: PublicConfig = { public_demo_mode: false, max_upload_bytes: 52428800, max_rows: 500000 };
const DEMO: PublicConfig = { public_demo_mode: true, max_upload_bytes: 1000, max_rows: 10 };

const onCreated = vi.fn();

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <UploadPage onCreated={onCreated} />
    </QueryClientProvider>,
  );
}

// The page with the full form on screen: the config has loaded (or failed).
async function renderForm() {
  renderPage();
  await screen.findByLabelText("CSV file");
}

beforeEach(() => {
  config.mockResolvedValue(DEFAULTS);
  upload.mockResolvedValue(created);
  sample.mockResolvedValue(created);
});

afterEach(() => {
  cleanup();
  upload.mockReset();
  sample.mockReset();
  config.mockReset();
  onCreated.mockReset();
  window.sessionStorage.clear();
});

function csv(name = "sales.csv", size?: number) {
  const file = new File(["a,b\n1,2\n"], name, { type: "text/csv" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

const input = () => screen.getByLabelText("CSV file") as HTMLInputElement;
const select = () => screen.getByLabelText("Currency") as HTMLSelectElement;
const uploadButton = () => screen.getByRole("button", { name: "Upload" });
const sampleButton = () => screen.getByRole("button", { name: "Try sample data" });

function choose(file: File, code = "USD") {
  fireEvent.change(input(), { target: { files: [file] } });
  if (code) fireEvent.change(select(), { target: { value: code } });
}

test("first render explains the tool, the schema and the limits", async () => {
  await renderForm();

  expect(screen.getByRole("heading", { level: 1, name: "Open Sales Analytics" })).toBeInTheDocument();
  expect(screen.getByText(/gross sales, orders and top products/)).toBeInTheDocument();
  for (const name of ["order_id", "order_date", "product_id", "product_name", "quantity", "unit_price"]) {
    expect(screen.getByText(name)).toBeInTheDocument();
  }
  expect(screen.getByText(/50 MB and 500,000 rows/)).toBeInTheDocument();
  expect(screen.getByText(/whole file is rejected/)).toBeInTheDocument();
  expect(screen.getByText(/Extra columns are ignored/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/revenue/i);
  expect(input()).toHaveAttribute("accept", ".csv");
  expect(input()).not.toHaveAttribute("multiple");
  expect(select().value).toBe("");
  const codes = Array.from(select().options).map((o) => o.value).filter(Boolean);
  expect(codes).toEqual(["USD", "EUR", "GBP", "TRY", "CAD", "AUD", "JPY", "CHF", "SEK", "PLN"]);
  expect(uploadButton()).toBeDisabled();
  expect(sampleButton()).toBeEnabled();
  expect(screen.queryByText("Processing…")).not.toBeInTheDocument();
});

test("Upload needs both a file and a currency", async () => {
  await renderForm();

  fireEvent.change(input(), { target: { files: [csv()] } });
  expect(uploadButton()).toBeDisabled();
  fireEvent.change(select(), { target: { value: "EUR" } });
  expect(uploadButton()).toBeEnabled();
});

test("a currency alone does not enable Upload", async () => {
  await renderForm();

  fireEvent.change(select(), { target: { value: "EUR" } });
  expect(uploadButton()).toBeDisabled();
});

test("a name not ending in .csv shows a message, in any letter case for .CSV", async () => {
  await renderForm();

  choose(csv("sales.txt"));
  expect(screen.getByRole("alert")).toHaveTextContent(".csv");
  expect(input()).toHaveAttribute("aria-invalid", "true");
  expect(uploadButton()).toBeDisabled();

  choose(csv("SALES.CSV"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();
});

test("50 MB exactly is accepted and one byte more is refused without a request", async () => {
  await renderForm();

  choose(csv("big.csv", 52_428_800));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();

  choose(csv("big.csv", 52_428_801));
  expect(screen.getByRole("alert")).toHaveTextContent("50 MB");
  expect(uploadButton()).toBeDisabled();
  fireEvent.click(uploadButton());
  expect(upload).not.toHaveBeenCalled();
});

test("an empty .csv is sent to the server", async () => {
  await renderForm();

  choose(new File([], "empty.csv"));
  fireEvent.click(uploadButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalled());
  expect(upload).toHaveBeenCalledTimes(1);
});

test("Upload calls the api once with the file and currency, saves the session and reports the result", async () => {
  await renderForm();
  const file = csv();
  choose(file, "GBP");

  fireEvent.click(uploadButton());
  fireEvent.click(uploadButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
  expect(upload).toHaveBeenCalledTimes(1);
  expect(upload.mock.calls[0][0]).toBe(file);
  expect(upload.mock.calls[0][1]).toBe("GBP");
  expect(readSession()).toEqual({ id: "d1", token: "secret-token" });
  expect(document.body.textContent).not.toContain("secret-token");
  expect(screen.queryByText("Processing…")).not.toBeInTheDocument();
});

test("Try sample data works with no file and no currency", async () => {
  await renderForm();

  fireEvent.click(sampleButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
  expect(sample).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
  expect(readSession()).toEqual({ id: "d1", token: "secret-token" });
});

test("while a request runs, Processing is shown and every control is disabled", async () => {
  let finish: (value: Created) => void = () => {};
  sample.mockReturnValue(new Promise<Created>((resolve) => (finish = resolve)));
  await renderForm();
  choose(csv());

  fireEvent.click(sampleButton());

  expect(screen.getByText("Processing…")).toBeInTheDocument();
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(input()).toBeDisabled();
  expect(select()).toBeDisabled();
  expect(uploadButton()).toBeDisabled();
  expect(sampleButton()).toBeDisabled();
  fireEvent.click(sampleButton());
  expect(sample).toHaveBeenCalledTimes(1);

  finish(created);
  await waitFor(() => expect(screen.queryByText("Processing…")).not.toBeInTheDocument());
  expect(input()).toBeEnabled();
});

test("after a failure the controls come back and the choices stay", async () => {
  upload.mockRejectedValue(new ApiError(500, "internal_error", "boom"));
  await renderForm();
  choose(csv(), "CHF");

  fireEvent.click(uploadButton());
  await waitFor(() => expect(screen.queryByText("Processing…")).not.toBeInTheDocument());

  expect(onCreated).not.toHaveBeenCalled();
  expect(readSession()).toBeNull();
  expect(select().value).toBe("CHF");
  expect(select()).toBeEnabled();
  expect(input()).toBeEnabled();
  expect(input().files?.[0].name).toBe("sales.csv");
  expect(uploadButton()).toBeEnabled();
  expect(sampleButton()).toBeEnabled();
});

// Shape of a real 422 body from the backend (checked against a running server).
const XSS = "<script>alert(1)</script>";
const LONG = "Expected a real date written YYYY-MM-DD, got '" + "9".repeat(300) + "'.";

function rejection(overrides: Partial<{ errors: Issue[]; errorCount: number; warnings: Issue[] }> = {}) {
  return new ApiError(422, "validation_failed", "The file has problems.", {
    errors: [
      { code: "missing_column", reason: "The required column 'quantity' is missing.", row_number: null, field: "quantity" },
      { code: "invalid_date", reason: LONG, row_number: 2, field: "order_date" },
      { code: "invalid_quantity", reason: "Expected a whole number, got '0'.", row_number: 2, field: "quantity" },
      { code: "duplicate_line", reason: `The line repeats row 2 <b>${XSS}</b>.`, row_number: 7, field: null },
    ],
    errorCount: 3214,
    warnings: [
      { code: "extra_column", reason: `The column '${XSS}' is not used and will be ignored.`, row_number: null, field: XSS },
      { code: "zero_price", reason: "3 lines have a unit price of 0.", row_number: null, field: "unit_price" },
    ],
    ...overrides,
  });
}

async function reject(error: ApiError) {
  upload.mockRejectedValue(error);
  await renderForm();
  choose(csv());
  fireEvent.click(uploadButton());
  return screen.findByRole("region", { name: "Validation report" });
}

test("a 422 report keeps the form usable and says the file was rejected and nothing was imported", async () => {
  const report = await reject(rejection());

  expect(report).toHaveTextContent("rejected");
  expect(report).toHaveTextContent("nothing was imported");
  expect(report).toHaveTextContent("3,214 errors");
  expect(onCreated).not.toHaveBeenCalled();
  expect(readSession()).toBeNull();
  expect(uploadButton()).toBeEnabled();
  expect(input()).toBeEnabled();
  expect(screen.getByRole("alert")).toHaveTextContent("3,214 errors");
});

test("the error table lists every error in order, one table row each", async () => {
  await reject(rejection());

  const table = screen.getByRole("table", { name: "Errors" });
  const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
  expect(headers).toEqual(["Row", "Field", "Code", "Reason"]);
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows).toHaveLength(4);
  const cells = rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent));
  expect(cells[0].slice(0, 3)).toEqual(["File", "quantity", "missing_column"]);
  expect(cells[1].slice(0, 3)).toEqual(["2", "order_date", "invalid_date"]);
  expect(cells[2].slice(0, 3)).toEqual(["2", "quantity", "invalid_quantity"]);
  expect(cells[3].slice(0, 3)).toEqual(["7", "—", "duplicate_line"]);
});

test("a very long reason sits in a wrapping cell inside a scrolling wrapper", async () => {
  await reject(rejection());

  const cell = screen.getByText(LONG);
  expect(cell).toHaveClass("wrap-anywhere");
  expect(screen.getByRole("table", { name: "Errors" }).parentElement).toHaveClass("overflow-x-auto");
});

test("the truncation line shows the real numbers, singular and plural", async () => {
  await reject(rejection());
  expect(screen.getByText("Showing the first 4 of 3,214 errors")).toBeInTheDocument();
});

test("no truncation line when every error is shown, and one error is singular", async () => {
  const one: Issue = { code: "invalid_date", reason: "bad", row_number: 2, field: "order_date" };
  await reject(rejection({ errors: [one], errorCount: 1, warnings: [] }));

  expect(screen.getByRole("alert")).toHaveTextContent("1 error to fix");
  expect(screen.getByRole("alert")).not.toHaveTextContent("1 errors");
  expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument();
});

test("warnings have their own heading and are worded as not the reason for the rejection", async () => {
  const report = await reject(rejection());

  expect(within(report).getByRole("heading", { name: "Warnings" })).toBeInTheDocument();
  expect(report).toHaveTextContent("not the reason the file was rejected");
  expect(within(report).getByText(/3 lines have a unit price of 0\./)).toBeInTheDocument();
  // errors are in the alert, warnings are outside it
  expect(screen.getByRole("alert")).not.toHaveTextContent("Warnings");
  expect(screen.getByRole("alert")).toHaveTextContent("Error");
  expect(within(report).getByText("Warning")).toBeInTheDocument();
});

test("no warnings heading when the response has no warnings", async () => {
  await reject(rejection({ warnings: [] }));
  expect(screen.queryByRole("heading", { name: "Warnings" })).not.toBeInTheDocument();
});

test("HTML in reasons, fields and warning fields is shown as text", async () => {
  const report = await reject(rejection());

  expect(report.querySelector("script")).toBeNull();
  expect(report.querySelector("b")).toBeNull();
  expect(within(report).getAllByText(XSS).length).toBeGreaterThan(0); // warning field
  expect(report).toHaveTextContent(`<b>${XSS}</b>`);
});

test("a field that is HTML is shown as text in the table", async () => {
  const bad: Issue = { code: "c", reason: "r", row_number: 1, field: XSS };
  await reject(rejection({ errors: [bad], errorCount: 1, warnings: [] }));
  expect(screen.getByRole("cell", { name: XSS })).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});

test("nothing says or suggests that some rows were accepted", async () => {
  const report = await reject(rejection());
  expect(report.textContent).not.toMatch(/accepted|partial|some rows|imported \d|revenue/i);
});

test("choosing a different file removes the report", async () => {
  await reject(rejection());
  fireEvent.change(input(), { target: { files: [csv("other.csv")] } });
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
});

test("starting a new upload removes the report, and a second 422 shows the new one", async () => {
  await reject(rejection());
  let fail: (e: ApiError) => void = () => {};
  upload.mockReturnValue(new Promise<Created>((_, reject) => (fail = reject)));
  fireEvent.click(uploadButton());
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
  fail(rejection({ errors: [], errorCount: 1, warnings: [] }));
  expect(await screen.findByText(/1 error to fix/)).toBeInTheDocument();
});

test("Try sample data removes the report", async () => {
  await reject(rejection());
  fireEvent.click(sampleButton());
  await waitFor(() => expect(onCreated).toHaveBeenCalled());
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
});

test("other failures show no validation report", async () => {
  upload.mockRejectedValue(new ApiError(500, "internal_error", "boom"));
  await renderForm();
  choose(csv());
  fireEvent.click(uploadButton());
  await waitFor(() => expect(uploadButton()).toBeEnabled());
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
});

test("the File format section links to the sample CSV as a plain download anchor", async () => {
  await renderForm();

  const link = screen.getByRole("link", { name: "Download sample CSV" });
  expect(link.tagName).toBe("A");
  expect(link).toHaveAttribute("href", "/api/sample.csv");
  expect(link).toHaveAttribute("download", "sample_sales.csv");
  expect(link).not.toHaveAttribute("target");
  expect(link).not.toHaveAttribute("tabindex");
  expect(link.className).toContain("text-indigo-700 underline underline-offset-2 hover:text-indigo-900");
  expect(link.className).toContain("focus-visible:outline-2");

  const section = screen.getByRole("region", { name: "File format" });
  expect(section).toContainElement(link);
  const limits = within(section).getByText(/Limits: 50 MB/);
  expect(limits.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  link.focus();
  expect(link).toHaveFocus();
  expect(upload).not.toHaveBeenCalled();
  expect(sample).not.toHaveBeenCalled();
});

test("the sample link stays visible while an upload is running", async () => {
  upload.mockReturnValue(new Promise(() => {}));
  await renderForm();

  choose(csv());
  fireEvent.click(uploadButton());

  expect(await screen.findByText("Processing…")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download sample CSV" })).toBeVisible();
});

// ---- Failures of Upload and Try sample data (#32) ----

// Bodies of the real backend: a demo that takes no uploads, a request without a file.
const DISABLED = () =>
  new ApiError(
    403,
    "upload_disabled",
    "Uploads are disabled on this demo. Upload your own file with the self-hosted version.",
  );
const INVALID_REQUEST = () => new ApiError(400, "invalid_request", "A file part named 'file' is required.");

function expectOneBlock(text: string | RegExp) {
  const alerts = screen.getAllByRole("alert");
  expect(alerts).toHaveLength(1);
  expect(alerts[0]).toHaveTextContent(text);
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
  return alerts[0];
}

async function failUpload(error: unknown, currency = "EUR") {
  upload.mockRejectedValue(error);
  await renderForm();
  choose(csv(), currency);
  fireEvent.click(uploadButton());
  await screen.findByRole("alert");
}

function expectFormKept(currency: string) {
  expect(onCreated).not.toHaveBeenCalled();
  expect(readSession()).toBeNull();
  expect(input().files?.[0].name).toBe("sales.csv");
  expect(select().value).toBe(currency);
  expect(uploadButton()).toBeEnabled();
  expect(sampleButton()).toBeEnabled();
  expect(input()).toBeEnabled();
  expect(screen.queryByText("Processing…")).not.toBeInTheDocument();
}

test("403 upload_disabled shows the server's message and the sample hint under the buttons, the form stays", async () => {
  await failUpload(DISABLED());

  const block = expectOneBlock(
    "Uploads are disabled on this demo. Upload your own file with the self-hosted version.",
  );
  expect(block).toHaveTextContent("You can still use Try sample data.");
  expect(block.textContent).not.toMatch(/403|upload_disabled/);
  expect(sampleButton().compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expectFormKept("EUR");
});

test("400 invalid_request shows the server's message", async () => {
  await failUpload(INVALID_REQUEST());

  const block = expectOneBlock("A file part named 'file' is required.");
  expect(block.textContent).not.toMatch(/400|invalid_request|Try sample data/);
  expectFormKept("EUR");
});

test("the server's text is shown as text, never as HTML", async () => {
  await failUpload(new ApiError(400, "invalid_request", "<b>bad</b> <script>alert(1)</script>"));

  const block = screen.getByRole("alert");
  expect(block).toHaveTextContent("<b>bad</b> <script>alert(1)</script>");
  expect(block.querySelector("b")).toBeNull();
  expect(block.querySelector("script")).toBeNull();
});

test("a 5xx shows that the file was not imported, and Upload can be pressed again without choosing again", async () => {
  await failUpload(new ApiError(500, "internal_error", "Something went wrong on the server."), "CHF");

  const block = expectOneBlock("Something went wrong — your file was not imported");
  expect(block.textContent).not.toMatch(/500|internal_error|on the server/);
  expectFormKept("CHF");

  upload.mockResolvedValue(created);
  fireEvent.click(uploadButton());
  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(upload).toHaveBeenCalledTimes(2);
  expect(upload.mock.calls[1][1]).toBe("CHF");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a network failure shows that the file was not imported", async () => {
  await failUpload(new ApiError(0, "network_error", "The server could not be reached."));

  const block = expectOneBlock("Something went wrong — your file was not imported");
  expect(block.textContent).not.toMatch(/reached|network/i);
  expectFormKept("EUR");
});

test("an unreadable answer (a 502 with an HTML body) shows that the file was not imported", async () => {
  await failUpload(new ApiError(502, "unknown_error", "The server sent an unexpected response."));

  expectOneBlock("Something went wrong — your file was not imported");
  expectFormKept("EUR");
});

test("a 422 without an errors array is a failure, not a report", async () => {
  await failUpload(new ApiError(422, "validation_failed", "The file has problems."));

  expectOneBlock("Something went wrong — your file was not imported");
});

test("a failure of Try sample data says the sample could not be loaded, and the form stays usable", async () => {
  sample.mockRejectedValue(new ApiError(500, "sample_unavailable", "The sample dataset is not available right now."));
  await renderForm();
  choose(csv(), "GBP");

  fireEvent.click(sampleButton());
  await screen.findByRole("alert");

  const block = expectOneBlock("Something went wrong — the sample data could not be loaded");
  expect(block.textContent).not.toMatch(/sample_unavailable|not available right now|file was not imported/);
  expectFormKept("GBP");
});

test("any status from Try sample data gives the sample sentence, including a 403", async () => {
  sample.mockRejectedValue(DISABLED());
  await renderForm();

  fireEvent.click(sampleButton());
  await screen.findByRole("alert");

  expectOneBlock("the sample data could not be loaded");
  expect(screen.getByRole("alert").textContent).not.toMatch(/Uploads are disabled/);
});

test("a failure of Try sample data can be retried", async () => {
  sample.mockRejectedValueOnce(new ApiError(0, "network_error", "x"));
  await renderForm();
  fireEvent.click(sampleButton());
  await screen.findByRole("alert");

  fireEvent.click(sampleButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("the error block is removed when a new attempt starts", async () => {
  await failUpload(new ApiError(500, "internal_error", "x"));
  let finish: (value: Created) => void = () => {};
  upload.mockReturnValue(new Promise<Created>((resolve) => (finish = resolve)));

  fireEvent.click(uploadButton());

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Processing…")).toBeInTheDocument();
  finish(created);
  await waitFor(() => expect(onCreated).toHaveBeenCalled());
});

test("Try sample data removes an earlier upload error", async () => {
  await failUpload(DISABLED());

  fireEvent.click(sampleButton());

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await waitFor(() => expect(onCreated).toHaveBeenCalled());
});

test("choosing a different file removes the error block", async () => {
  await failUpload(new ApiError(500, "internal_error", "x"));

  fireEvent.change(input(), { target: { files: [csv("other.csv")] } });

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a failure never shows together with the 422 report, in either order", async () => {
  await failUpload(new ApiError(500, "internal_error", "x"));
  upload.mockRejectedValue(rejection());
  fireEvent.click(uploadButton());
  await screen.findByRole("region", { name: "Validation report" });
  expect(screen.queryByText(/your file was not imported/)).not.toBeInTheDocument();

  upload.mockRejectedValue(INVALID_REQUEST());
  fireEvent.click(uploadButton());
  await screen.findByText("A file part named 'file' is required.");
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
});

test("no failure text says revenue", async () => {
  await failUpload(DISABLED());
  expect(document.body.textContent).not.toMatch(/revenue/i);
});

// --- config-driven form (GET /api/config) ---

const limitsBullet = () => screen.queryByText(/^Limits:/);
const loadingBlock = () => screen.queryByText("Loading…");

type Scenario = "demo" | "defaults" | "custom" | "loading" | "failed";

async function show(scenario: Scenario) {
  if (scenario === "demo") config.mockResolvedValue(DEMO);
  if (scenario === "custom") config.mockResolvedValue({ ...DEFAULTS, max_upload_bytes: 1048576, max_rows: 1000 });
  if (scenario === "loading") config.mockReturnValue(new Promise(() => {}));
  if (scenario === "failed") config.mockRejectedValue(new ApiError(0, "network_error", "down"));
  renderPage();
  if (scenario === "demo") await screen.findByText(/^Uploads are available in the self-hosted version\./);
  else if (scenario === "loading") await screen.findByText("Loading…");
  else await screen.findByLabelText("CSV file");
}

test("demo mode shows only Try sample data and the self-hosted sentence, with no limits bullet", async () => {
  await show("demo");

  expect(screen.queryByLabelText("CSV file")).not.toBeInTheDocument();
  expect(document.querySelector('input[type="file"]')).toBeNull();
  expect(screen.queryByLabelText("Currency")).not.toBeInTheDocument();
  expect(document.querySelector("select")).toBeNull();
  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  expect(limitsBullet()).not.toBeInTheDocument();
  expect(loadingBlock()).not.toBeInTheDocument();
  expect(sampleButton()).toBeEnabled();
  const help = screen.getByText(/^Uploads are available in the self-hosted version\./);
  expect(help).toHaveClass("text-sm", "text-slate-600");
  const section = screen.getByRole("region", { name: "Start an analysis" });
  expect(section).toContainElement(help);
  expect(within(section).getByRole("heading", { level: 2, name: "Start an analysis" })).toBeInTheDocument();
});

test("demo mode replaces the intro with a sample-only sentence near the top and leaves the File format section as it is", async () => {
  await show("demo");

  expect(screen.getByRole("heading", { level: 1, name: "Open Sales Analytics" })).toBeInTheDocument();
  const intro = screen.getByText(/This demo accepts sample data only/);
  expect(intro).toHaveTextContent("Click Try sample data to see gross sales, orders and top products.");
  const header = screen.getByRole("heading", { level: 1 }).parentElement as HTMLElement;
  expect(header).toContainElement(intro);
  expect(header.compareDocumentPosition(screen.getByRole("region", { name: "File format" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByText(/Upload a CSV/)).not.toBeInTheDocument();
  const format = screen.getByRole("region", { name: "File format" });
  expect(within(format).getByText("order_id")).toBeInTheDocument();
  expect(within(format).getByText(/whole file is rejected/)).toBeInTheDocument();
  expect(within(format).getByText(/Extra columns are ignored/)).toBeInTheDocument();
  expect(within(format).getByRole("link", { name: "Download sample CSV" })).toHaveAttribute("href", "/api/sample.csv");
  expect(document.body.textContent).not.toMatch(/revenue/i);
});

test("demo mode links the self-hosting text to the README Docker section with an absolute, focusable link", async () => {
  await show("demo");

  const link = screen.getByRole("link", { name: "Run it yourself with Docker" });
  expect(link).toHaveAttribute("href", "https://github.com/nacaroglu/open-sales-analytics#run-it-with-docker");
  expect(screen.getByRole("region", { name: "Start an analysis" })).toContainElement(link);
  expect(link).toHaveClass("underline", "text-indigo-700", "focus-visible:outline-2", "focus-visible:outline-indigo-700");
  link.focus();
  expect(document.activeElement).toBe(link);
  expect(link).not.toHaveAttribute("tabindex");
});

test("demo mode: Try sample data is the only way to start and Download sample CSV is still offered", async () => {
  await show("demo");

  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Try sample data"]);
  expect(screen.getByRole("link", { name: "Download sample CSV" })).toBeInTheDocument();
});

test("self-hosted default shows the upload intro and neither the sample-only nor the self-hosting text", async () => {
  await show("defaults");

  expect(screen.getByText(/Upload a CSV of completed sales lines/)).toBeInTheDocument();
  expect(screen.queryByText(/sample data only/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Run it yourself with Docker" })).not.toBeInTheDocument();
});

test("config failed and the server refuses the upload: the message with the self-hosting hint shows", async () => {
  upload.mockRejectedValue(DISABLED());
  await show("failed");
  choose(csv());
  fireEvent.click(uploadButton());

  const block = await screen.findByRole("alert");
  expect(block).toHaveTextContent("Uploads are disabled on this demo. Upload your own file with the self-hosted version.");
  expect(block).toHaveTextContent("You can still use Try sample data.");
  expect(screen.queryByRole("link", { name: "Run it yourself with Docker" })).not.toBeInTheDocument();
});

test("demo off with the real default payload shows the full form and the old limits text", async () => {
  await show("defaults");

  expect(input()).toBeEnabled();
  expect(select()).toBeEnabled();
  expect(uploadButton()).toBeDisabled();
  expect(limitsBullet()).toHaveTextContent("Limits: 50 MB and 500,000 rows per upload.");
  expect(screen.queryByText(/self-hosted version/)).not.toBeInTheDocument();
  expect(loadingBlock()).not.toBeInTheDocument();
  expect(config).toHaveBeenCalledTimes(1);
});

test("custom limits show as 1 MB and 1,000 rows, and the limit itself is accepted while one byte more is refused", async () => {
  await show("custom");

  expect(limitsBullet()).toHaveTextContent("Limits: 1 MB and 1,000 rows per upload.");
  choose(csv("edge.csv", 1_048_576));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();

  choose(csv("edge.csv", 1_048_577));
  expect(screen.getByRole("alert")).toHaveTextContent("The file is larger than the 1 MB limit.");
  expect(uploadButton()).toBeDisabled();
  fireEvent.click(uploadButton());
  expect(upload).not.toHaveBeenCalled();

  choose(csv("edge.csv", 0));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a 50 MB file is refused with the configured size when the limit is lower", async () => {
  await show("custom");

  choose(csv("big.csv", 52_428_800));
  expect(screen.getByRole("alert")).toHaveTextContent("larger than the 1 MB limit");
  expect(screen.getByRole("alert")).not.toHaveTextContent("50 MB");
});

test.each([
  [1000, "0.000954 MB"],
  [1_572_864, "1.5 MB"],
  [52_428_800, "50 MB"],
  [1_048_576 * 1000, "1e+03 MB"],
  [1_048_576 * 1024, "1.02e+03 MB"],
  [1_048_576 * 999.4, "999 MB"],
  [1, "9.54e-07 MB"],
])("a limit of %i bytes is written as %s like the server does", async (bytes, text) => {
  config.mockResolvedValue({ ...DEFAULTS, max_upload_bytes: Math.round(bytes) });
  renderPage();
  expect(await screen.findByText(`Limits: ${text} and 500,000 rows per upload.`)).toBeInTheDocument();
  choose(csv("big.csv", Math.round(bytes) + 1));
  expect(screen.getByRole("alert")).toHaveTextContent(`The file is larger than the ${text} limit.`);
});

test("max_rows is written with thousands separators", async () => {
  config.mockResolvedValue({ ...DEFAULTS, max_rows: 1234567 });
  renderPage();
  expect(await screen.findByText(/and 1,234,567 rows per upload\./)).toBeInTheDocument();
});

test("while loading, a loading block stands in for the form and the limits", async () => {
  await show("loading");

  const block = screen.getByText("Loading…").closest('[role="status"]')!;
  expect(block).toHaveAttribute("aria-busy", "true");
  expect(block.querySelector(".animate-pulse.motion-reduce\\:animate-none")).not.toBeNull();
  expect(screen.queryByLabelText("CSV file")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Currency")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  expect(limitsBullet()).not.toBeInTheDocument();
  expect(screen.queryByText(/self-hosted version/)).not.toBeInTheDocument();
  expect(sampleButton()).toBeEnabled();
});

test("the form appears in place of the loading block when the config arrives", async () => {
  let arrive: (value: PublicConfig) => void = () => {};
  config.mockReturnValue(new Promise<PublicConfig>((resolve) => (arrive = resolve)));
  renderPage();
  await screen.findByText("Loading…");

  arrive(DEFAULTS);

  expect(await screen.findByLabelText("CSV file")).toBeInTheDocument();
  expect(loadingBlock()).not.toBeInTheDocument();
  expect(limitsBullet()).toBeInTheDocument();
});

test("in demo mode the file input is never in the page, not even for a moment", async () => {
  let arrive: (value: PublicConfig) => void = () => {};
  config.mockReturnValue(new Promise<PublicConfig>((resolve) => (arrive = resolve)));
  renderPage();
  await screen.findByText("Loading…");
  const seen: boolean[] = [];
  const watcher = new MutationObserver(() => seen.push(document.querySelector('input[type="file"]') !== null));
  watcher.observe(document.body, { childList: true, subtree: true });

  arrive(DEMO);
  await screen.findByText(/self-hosted version/);
  watcher.disconnect();

  expect(seen.length).toBeGreaterThan(0);
  expect(seen).not.toContain(true);
});

test("if the config cannot be loaded the full form shows with no limits bullet, no error and no size check", async () => {
  await show("failed");

  expect(input()).toBeEnabled();
  expect(select()).toBeEnabled();
  expect(uploadButton()).toBeDisabled();
  expect(sampleButton()).toBeEnabled();
  expect(limitsBullet()).not.toBeInTheDocument();
  expect(loadingBlock()).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText(/self-hosted version/)).not.toBeInTheDocument();
  expect(screen.getByText(/whole file is rejected/)).toBeInTheDocument();

  choose(csv("huge.txt", 5));
  expect(screen.getByRole("alert")).toHaveTextContent(".csv");
  choose(csv("huge.csv", 10_000_000_000));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();
  fireEvent.click(uploadButton());
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
  expect(config).toHaveBeenCalledTimes(1);
});

test.each<Scenario>(["demo", "defaults", "custom", "loading", "failed"])(
  "Try sample data works in the %s state",
  async (scenario) => {
    await show(scenario);

    fireEvent.click(sampleButton());

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    expect(sample).toHaveBeenCalledTimes(1);
    expect(upload).not.toHaveBeenCalled();
    expect(readSession()).toEqual({ id: "d1", token: "secret-token" });
  },
);

// --- capacity_reached (#41): the real 503 body of a full server ---

const CAPACITY_MESSAGE = "The server is full right now. Please try again in a few minutes.";
const FULL = () =>
  new ApiError(
    503,
    "capacity_reached",
    "The server is holding the maximum number of datasets right now. Try again later.",
  );

test("a full server on Upload shows the capacity sentence, keeps file and currency, and Upload can be retried", async () => {
  await failUpload(FULL(), "SEK");

  const block = expectOneBlock(CAPACITY_MESSAGE);
  expect(block.textContent).not.toMatch(/503|capacity_reached|maximum number|not imported|Something went wrong/);
  expectFormKept("SEK");

  upload.mockResolvedValue(created);
  fireEvent.click(uploadButton());
  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(upload).toHaveBeenCalledTimes(2);
  expect(upload.mock.calls[1][1]).toBe("SEK");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a full server on Try sample data shows the capacity sentence, keeps the form, and the button can be pressed again", async () => {
  sample.mockRejectedValueOnce(FULL());
  await renderForm();
  choose(csv(), "PLN");

  fireEvent.click(sampleButton());
  await screen.findByRole("alert");

  const block = expectOneBlock(CAPACITY_MESSAGE);
  expect(block.textContent).not.toMatch(/sample data could not be loaded|capacity_reached/);
  expectFormKept("PLN");

  fireEvent.click(sampleButton());
  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(sample).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a 503 with an unreadable body gives the generic failure sentence, for Upload", async () => {
  await failUpload(new ApiError(503, "unknown_error", "The server sent an unexpected response."));

  const block = expectOneBlock("Something went wrong — your file was not imported");
  expect(block.textContent).not.toMatch(/full right now/);
  expectFormKept("EUR");
});

test("a 503 with an unreadable body gives the generic failure sentence, for Try sample data", async () => {
  sample.mockRejectedValue(new ApiError(503, "unknown_error", "The server sent an unexpected response."));
  await renderForm();

  fireEvent.click(sampleButton());
  await screen.findByRole("alert");

  const block = expectOneBlock("Something went wrong — the sample data could not be loaded");
  expect(block.textContent).not.toMatch(/full right now/);
});

test("the capacity block goes away when another file is picked or a new attempt starts", async () => {
  await failUpload(FULL());
  fireEvent.change(input(), { target: { files: [csv("other.csv")] } });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  upload.mockRejectedValue(FULL());
  fireEvent.click(uploadButton());
  await screen.findByRole("alert");
  let finish: (value: Created) => void = () => {};
  sample.mockReturnValue(new Promise<Created>((resolve) => (finish = resolve)));
  fireEvent.click(sampleButton());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  finish(created);
  await waitFor(() => expect(onCreated).toHaveBeenCalled());
});

// ---- Helper text and states (#42) ----

test("the disabled Upload button is described by the helper, which goes away once both are chosen", async () => {
  renderPage();
  const button = await screen.findByRole("button", { name: "Upload" });
  expect(button).toBeDisabled();
  const helper = screen.getByText("Select a CSV file and currency to continue.");
  expect(button).toHaveAccessibleDescription("Select a CSV file and currency to continue.");
  expect(button.getAttribute("aria-describedby")).toBe(helper.id);

  fireEvent.change(screen.getByLabelText("CSV file"), {
    target: { files: [new File(["x"], "sales.csv", { type: "text/csv" })] },
  });
  expect(screen.getByText("Select a CSV file and currency to continue.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "EUR" } });

  expect(button).toBeEnabled();
  expect(button).not.toHaveAttribute("aria-describedby");
  expect(screen.queryByText("Select a CSV file and currency to continue.")).not.toBeInTheDocument();
});

test("the file input is the native one: no custom text or locale on it", async () => {
  renderPage();
  const input = await screen.findByLabelText("CSV file");
  expect(input).toHaveAttribute("type", "file");
  expect(input).not.toHaveAttribute("lang");
  expect(input).not.toHaveAttribute("title");
});

// ---- Selection feedback: clearing and replacing (#46) ----

const HELP = "Select a CSV file and currency to continue.";

test("clearing the chosen file disables Upload again and brings the helper back", async () => {
  await renderForm();
  choose(csv());
  expect(uploadButton()).toBeEnabled();
  expect(screen.queryByText(HELP)).not.toBeInTheDocument();

  fireEvent.change(input(), { target: { files: [] } });

  expect(uploadButton()).toBeDisabled();
  expect(uploadButton()).toHaveAccessibleDescription(HELP);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(select().value).toBe("USD");
  fireEvent.click(uploadButton());
  expect(upload).not.toHaveBeenCalled();
});

test("going back to the placeholder currency disables Upload and shows the helper again", async () => {
  await renderForm();
  choose(csv(), "EUR");
  expect(uploadButton()).toBeEnabled();

  fireEvent.change(select(), { target: { value: "" } });

  expect(uploadButton()).toBeDisabled();
  expect(screen.getByText(HELP)).toBeInTheDocument();
});

test("replacing a refused file with a good one clears the message and enables Upload, which sends the new file", async () => {
  await renderForm();
  choose(csv("notes.txt"), "GBP");
  expect(screen.getByRole("alert")).toHaveTextContent("The file must be a .csv file.");
  expect(uploadButton()).toBeDisabled();
  expect(screen.getByText(HELP)).toBeInTheDocument();

  const good = csv("march.csv");
  fireEvent.change(input(), { target: { files: [good] } });

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(input()).not.toHaveAttribute("aria-invalid");
  expect(input()).not.toHaveAttribute("aria-describedby");
  expect(uploadButton()).toBeEnabled();
  fireEvent.click(uploadButton());
  await waitFor(() => expect(upload).toHaveBeenCalledWith(good, "GBP"));
});

test("replacing a good file with a refused one disables Upload and ties the message to the input", async () => {
  await renderForm();
  choose(csv("march.csv"));
  expect(uploadButton()).toBeEnabled();

  fireEvent.change(input(), { target: { files: [csv("march.xlsx")] } });

  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("The file must be a .csv file.");
  expect(input()).toHaveAttribute("aria-invalid", "true");
  expect(input()).toHaveAccessibleDescription("The file must be a .csv file.");
  expect(alert.id).toBe(input().getAttribute("aria-describedby"));
  expect(uploadButton()).toBeDisabled();
});
