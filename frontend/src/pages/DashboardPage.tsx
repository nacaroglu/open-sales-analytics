import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, deleteDataset } from "../lib/api";
import KpiCards from "../components/KpiCards";
import { useAnalytics, useMeta } from "../lib/hooks";
import { clearSession, tokenFor } from "../lib/session";
import type { Issue } from "../lib/types";

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";
const BUTTON = `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold ${FOCUS} disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600`;
const PRIMARY = `${BUTTON} bg-indigo-700 text-white enabled:hover:bg-indigo-800`;
const LINK = `text-indigo-700 underline underline-offset-2 hover:text-indigo-900 ${FOCUS}`;
const LABEL = "text-sm font-medium text-slate-600";
const VALUE = "mt-1 text-base font-semibold tabular-nums wrap-anywhere";

// The expiry is a UTC instant, shown in the browser's local time zone. The two
// dates are calendar dates and are shown exactly as received, never converted.
function formatExpiry(utc: string): string {
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return utc;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function Header() {
  return <h1 className="text-3xl font-bold text-indigo-700">Open Sales Analytics</h1>;
}

function CannotOpen() {
  return (
    <div className="space-y-8">
      <Header />
      <div className="mx-auto max-w-md space-y-4 rounded-lg border border-slate-200 bg-white p-6 text-center">
        <h2 className="text-xl font-semibold text-slate-900">
          This dataset cannot be opened from this browser session
        </h2>
        <p className="text-sm text-slate-600">
          Datasets can only be opened in the tab where they were created.
        </p>
        <Link to="/" className={LINK}>
          Go to the upload screen
        </Link>
      </div>
    </div>
  );
}

function WarningNotice({ warnings, onDismiss }: { warnings: Issue[]; onDismiss: () => void }) {
  return (
    <div
      role="status"
      className="flex items-start justify-between gap-3 rounded-md border border-l-4 border-dashed border-amber-700 bg-amber-50 p-3 text-sm text-amber-900"
    >
      <div className="space-y-1">
        <p>
          <span aria-hidden>⚠</span> <strong>Warning</strong>
        </p>
        <ul className="list-disc space-y-1 pl-6">
          {warnings.map((warning, index) => (
            <li key={index} className="wrap-anywhere">
              {warning.reason}
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        aria-label="Dismiss notice"
        onClick={onDismiss}
        className={`shrink-0 ${LINK}`}
      >
        Dismiss
      </button>
    </div>
  );
}

const FACTS = ["Period", "Currency", "Rows", "Expires"];

export default function DashboardPage({
  datasetId,
  warnings,
  onDismissWarnings,
}: {
  datasetId: string;
  warnings: Issue[];
  onDismissWarnings: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const meta = useMeta(datasetId);
  // The one analytics request of the page (full range). The trend chart (#29)
  // and the top products (#30) read it from here too.
  const analytics = useAnalytics(datasetId);
  const [leaving, setLeaving] = useState(false);

  const hasToken = tokenFor(datasetId) !== null;
  if (!hasToken || (meta.error instanceof ApiError && meta.error.status === 401)) {
    return <CannotOpen />;
  }

  async function analyzeAnother() {
    if (leaving) return;
    setLeaving(true);
    try {
      await deleteDataset(datasetId);
    } catch {
      // Even if the server could not delete it, this browser lets go of it.
    }
    clearSession();
    onDismissWarnings();
    navigate("/");
    queryClient.removeQueries({ queryKey: ["meta", datasetId] });
    queryClient.removeQueries({ queryKey: ["analytics", datasetId] });
  }

  const data = meta.data;

  return (
    <div className="space-y-8">
      <Header />

      {warnings.length > 0 && <WarningNotice warnings={warnings} onDismiss={onDismissWarnings} />}

      <section aria-label="Date range">
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex justify-end">
            <button type="button" className={PRIMARY} disabled={leaving} onClick={analyzeAnother}>
              Analyze another file
            </button>
          </div>
          {meta.isError ? (
            <div
              role="alert"
              className="space-y-3 rounded-md border border-l-4 border-red-700 bg-red-50 p-3 text-sm text-red-900"
            >
              <p>
                <span aria-hidden>✕</span> <strong>Error</strong> Something went wrong loading
                this data
              </p>
              <button type="button" className={PRIMARY} onClick={() => void meta.refetch()}>
                Retry
              </button>
            </div>
          ) : data === undefined ? (
            <div role="status" aria-busy="true" className="space-y-2">
              <p className="text-sm text-slate-600">Loading…</p>
              <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                {FACTS.map((label) => (
                  <div key={label}>
                    <dt className={LABEL}>{label}</dt>
                    <dd className="mt-1">
                      <div className="h-6 w-24 animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : (
            <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <div>
                <dt className={LABEL}>Period</dt>
                <dd className={VALUE}>
                  {data.date_range.min} to {data.date_range.max}
                </dd>
              </div>
              <div>
                <dt className={LABEL}>Currency</dt>
                <dd className={VALUE}>{data.currency}</dd>
              </div>
              <div>
                <dt className={LABEL}>Rows</dt>
                <dd className={VALUE}>{data.row_count.toLocaleString("en-US")}</dd>
              </div>
              <div>
                <dt className={LABEL}>Expires</dt>
                <dd className={VALUE}>{formatExpiry(data.expires_at)}</dd>
              </div>
            </dl>
          )}
          {/* The date-range filter (#31) goes here. */}
        </div>
      </section>

      {/* Empty areas: #28, #29 and #30 place their content here. */}
      <section aria-label="Key figures">
        <KpiCards kpis={analytics.data?.kpis} currency={analytics.data?.currency} />
      </section>
      <section aria-label="Sales trend" />
      <section aria-label="Top products" />
    </div>
  );
}
