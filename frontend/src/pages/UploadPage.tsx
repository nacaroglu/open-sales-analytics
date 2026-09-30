import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { createDatasetFromUpload, createSampleDataset } from "../lib/api";
import { saveSession } from "../lib/session";
import type { Created } from "../lib/types";

export const MAX_UPLOAD_BYTES = 52_428_800;

const CURRENCIES = [
  "USD",
  "EUR",
  "GBP",
  "TRY",
  "CAD",
  "AUD",
  "JPY",
  "CHF",
  "SEK",
  "PLN",
];

const COLUMNS: { name: string; type: string; rule: string }[] = [
  {
    name: "order_id",
    type: "String",
    rule: "Required and non-empty. Used for distinct order counting.",
  },
  {
    name: "order_date",
    type: "Date",
    rule: "Required ISO calendar date in YYYY-MM-DD format. Must not be in the future.",
  },
  {
    name: "product_id",
    type: "String",
    rule: "Required and non-empty. Identifies the product.",
  },
  {
    name: "product_name",
    type: "String",
    rule: "Required and non-empty. One product_id must map to exactly one name within an upload.",
  },
  {
    name: "quantity",
    type: "Integer",
    rule: "Required and greater than zero. Zero and negative quantities are invalid.",
  },
  {
    name: "unit_price",
    type: "Decimal",
    rule: "Required and non-negative. A zero price is accepted with a warning; a negative price is invalid.",
  },
];

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";
const BUTTON = `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold ${FOCUS} disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600`;
const PRIMARY = `${BUTTON} bg-indigo-700 text-white enabled:hover:bg-indigo-800`;
const SECONDARY = `${BUTTON} bg-white text-slate-900 border border-slate-500 enabled:hover:bg-slate-100`;
const SELECT = `block h-10 w-full rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 disabled:bg-slate-100 disabled:text-slate-600 disabled:cursor-not-allowed aria-[invalid=true]:border-2 aria-[invalid=true]:border-red-700 ${FOCUS}`;
const FILE_INPUT = `block w-full text-sm file:mr-3 file:h-10 file:rounded-md file:border file:border-slate-500 file:bg-white file:px-3 file:font-medium hover:file:bg-slate-100 ${FOCUS}`;

function fileProblem(file: File | null): string | null {
  if (file === null) return null;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return "The file must be a .csv file.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "The file is larger than the 50 MB limit.";
  }
  return null;
}

export default function UploadPage({
  onCreated,
}: {
  onCreated: (created: Created) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [currency, setCurrency] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  const problem = fileProblem(file);
  const canUpload = file !== null && problem === null && currency !== "" && !busy;

  async function run(start: () => Promise<Created>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      const created = await start();
      saveSession({ id: created.dataset_id, token: created.token });
      onCreated(created);
    } catch {
      // What to show for a failure is #26 and #32; the controls just come back.
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold text-indigo-700">Open Sales Analytics</h1>
        <p className="text-base">
          Upload a CSV of completed sales lines and see gross sales, orders and
          top products.
        </p>
      </header>

      <section
        aria-label="File format"
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-6"
      >
        <h2 className="text-xl font-semibold text-slate-900">File format</h2>
        <p className="text-sm text-slate-600">
          One row is one product line within one completed order. The file must
          have these six columns.
        </p>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left">
            <thead className="bg-slate-100">
              <tr>
                <th className="px-3 py-2 text-sm font-semibold text-slate-700">Column</th>
                <th className="px-3 py-2 text-sm font-semibold text-slate-700">Type</th>
                <th className="px-3 py-2 text-sm font-semibold text-slate-700">Rule</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {COLUMNS.map((column) => (
                <tr key={column.name}>
                  <td className="px-3 py-2 align-top text-sm wrap-anywhere">
                    <span className="font-mono text-sm">{column.name}</span>
                  </td>
                  <td className="px-3 py-2 align-top text-sm wrap-anywhere">{column.type}</td>
                  <td className="px-3 py-2 align-top text-sm wrap-anywhere">{column.rule}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="list-disc space-y-1 pl-6 text-sm text-slate-600">
          <li>Limits: 50 MB and 500,000 rows per upload.</li>
          <li>If any row is invalid, the whole file is rejected.</li>
          <li>Extra columns are ignored.</li>
        </ul>
      </section>

      <section
        aria-label="Start an analysis"
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-6"
      >
        <h2 className="text-xl font-semibold text-slate-900">Start an analysis</h2>
        <div>
          <label htmlFor="csv-file" className="block text-sm font-medium">
            CSV file
          </label>
          <input
            id="csv-file"
            type="file"
            accept=".csv"
            onChange={onFile}
            disabled={busy}
            aria-invalid={problem !== null ? "true" : undefined}
            aria-describedby={problem !== null ? "csv-file-error" : undefined}
            className={`mt-1 ${FILE_INPUT}`}
          />
          {problem !== null && (
            <p
              id="csv-file-error"
              role="alert"
              className="mt-1 text-sm font-medium text-red-800"
            >
              <span aria-hidden>✕</span> {problem}
            </p>
          )}
        </div>
        <div className="w-44">
          <label htmlFor="currency" className="block text-sm font-medium">
            Currency
          </label>
          <select
            id="currency"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
            disabled={busy}
            className={`mt-1 ${SELECT}`}
          >
            <option value="">Select a currency</option>
            {CURRENCIES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={PRIMARY}
            disabled={!canUpload}
            onClick={() => file !== null && run(() => createDatasetFromUpload(file, currency))}
          >
            Upload
          </button>
          <button
            type="button"
            className={SECONDARY}
            disabled={busy}
            onClick={() => run(() => createSampleDataset())}
          >
            Try sample data
          </button>
        </div>
        {busy && (
          <div role="status" aria-busy="true" className="space-y-2">
            <p className="text-sm text-slate-600">Processing…</p>
            <div className="h-1 w-full overflow-hidden rounded bg-slate-200">
              <div className="h-full w-1/3 animate-pulse motion-reduce:animate-none bg-indigo-700" />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
