import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import UploadPage, { MAX_UPLOAD_BYTES } from "./UploadPage";
import { ApiError } from "../lib/api";
import { readSession } from "../lib/session";
import type { Created, Issue } from "../lib/types";

const { upload, sample } = vi.hoisted(() => ({ upload: vi.fn(), sample: vi.fn() }));

vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  createDatasetFromUpload: upload,
  createSampleDataset: sample,
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

const onCreated = vi.fn();

beforeEach(() => {
  upload.mockResolvedValue(created);
  sample.mockResolvedValue(created);
});

afterEach(() => {
  cleanup();
  upload.mockReset();
  sample.mockReset();
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

test("first render explains the tool, the schema and the limits", () => {
  render(<UploadPage onCreated={onCreated} />);

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

test("Upload needs both a file and a currency", () => {
  render(<UploadPage onCreated={onCreated} />);

  fireEvent.change(input(), { target: { files: [csv()] } });
  expect(uploadButton()).toBeDisabled();
  fireEvent.change(select(), { target: { value: "EUR" } });
  expect(uploadButton()).toBeEnabled();
});

test("a currency alone does not enable Upload", () => {
  render(<UploadPage onCreated={onCreated} />);

  fireEvent.change(select(), { target: { value: "EUR" } });
  expect(uploadButton()).toBeDisabled();
});

test("a name not ending in .csv shows a message, in any letter case for .CSV", () => {
  render(<UploadPage onCreated={onCreated} />);

  choose(csv("sales.txt"));
  expect(screen.getByRole("alert")).toHaveTextContent(".csv");
  expect(input()).toHaveAttribute("aria-invalid", "true");
  expect(uploadButton()).toBeDisabled();

  choose(csv("SALES.CSV"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();
});

test("50 MB exactly is accepted and one byte more is refused without a request", () => {
  render(<UploadPage onCreated={onCreated} />);

  choose(csv("big.csv", MAX_UPLOAD_BYTES));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(uploadButton()).toBeEnabled();

  choose(csv("big.csv", MAX_UPLOAD_BYTES + 1));
  expect(screen.getByRole("alert")).toHaveTextContent("50 MB");
  expect(uploadButton()).toBeDisabled();
  fireEvent.click(uploadButton());
  expect(upload).not.toHaveBeenCalled();
});

test("an empty .csv is sent to the server", async () => {
  render(<UploadPage onCreated={onCreated} />);

  choose(new File([], "empty.csv"));
  fireEvent.click(uploadButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalled());
  expect(upload).toHaveBeenCalledTimes(1);
});

test("Upload calls the api once with the file and currency, saves the session and reports the result", async () => {
  render(<UploadPage onCreated={onCreated} />);
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
  render(<UploadPage onCreated={onCreated} />);

  fireEvent.click(sampleButton());

  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
  expect(sample).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
  expect(readSession()).toEqual({ id: "d1", token: "secret-token" });
});

test("while a request runs, Processing is shown and every control is disabled", async () => {
  let finish: (value: Created) => void = () => {};
  sample.mockReturnValue(new Promise<Created>((resolve) => (finish = resolve)));
  render(<UploadPage onCreated={onCreated} />);
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
  render(<UploadPage onCreated={onCreated} />);
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
  render(<UploadPage onCreated={onCreated} />);
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
  render(<UploadPage onCreated={onCreated} />);
  choose(csv());
  fireEvent.click(uploadButton());
  await waitFor(() => expect(uploadButton()).toBeEnabled());
  expect(screen.queryByRole("region", { name: "Validation report" })).not.toBeInTheDocument();
});
