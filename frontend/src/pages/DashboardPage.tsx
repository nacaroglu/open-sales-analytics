import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { deleteDataset } from "../lib/api";
import DateRangeFilter, { validateRange } from "../components/DateRangeFilter";
import ErrorBlock from "../components/ErrorBlock";
import FullPageCard from "../components/FullPageCard";
import SectionBoundary from "../components/SectionBoundary";
import KpiCards from "../components/KpiCards";
import TopProducts from "../components/TopProducts";
import TrendChart from "../components/TrendChart";
import { useAnalytics, useMeta } from "../lib/hooks";
import {
  EXPIRED_SENTENCE,
  EXPIRED_TITLE,
  LOAD_FAILED,
  UNAUTHORIZED_SENTENCE,
  UNAUTHORIZED_TITLE,
  describeError,
  errorKind,
} from "../lib/errors";
import { clearSession, readSession, tokenFor } from "../lib/session";
import type { Issue, Meta } from "../lib/types";

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";
const BUTTON = `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold ${FOCUS} disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600`;
const PRIMARY = `${BUTTON} bg-indigo-700 text-white enabled:hover:bg-indigo-800`;
const SECONDARY = `${BUTTON} bg-white text-slate-900 border border-slate-500 enabled:hover:bg-slate-100`;
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
      <FullPageCard title={UNAUTHORIZED_TITLE} sentence={UNAUTHORIZED_SENTENCE}>
        <Link to="/" className={LINK}>
          Go to the upload screen
        </Link>
      </FullPageCard>
    </div>
  );
}

function Expired() {
  return (
    <div className="space-y-8">
      <Header />
      <FullPageCard title={EXPIRED_TITLE} sentence={EXPIRED_SENTENCE}>
        <Link to="/" className={LINK}>
          Go to the upload screen
        </Link>
      </FullPageCard>
    </div>
  );
}

function NoSalesNotice({ onReset }: { onReset: () => void }) {
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 rounded-md border border-l-4 border-dashed border-amber-700 bg-amber-50 p-3 text-sm text-amber-900"
    >
      <p>
        <span aria-hidden>⚠</span> <strong>Warning</strong> No sales in the selected range
      </p>
      <button type="button" className={`shrink-0 ${SECONDARY}`} onClick={onReset}>
        Reset
      </button>
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

// The Date range card: the facts of the dataset and the filter. It is one
// section, so a render error in it (a meta it cannot read) stops here.
function DateRangeCard({
  data,
  failed,
  onRetry,
  leaving,
  onAnalyzeAnother,
  filter,
}: {
  data: Meta | undefined;
  failed: boolean;
  onRetry: () => void;
  leaving: boolean;
  onAnalyzeAnother: () => void;
  filter: ReactNode;
}) {
  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex justify-end">
        <button type="button" className={PRIMARY} disabled={leaving} onClick={onAnalyzeAnother}>
          Analyze another file
        </button>
      </div>
      {failed ? (
        <ErrorBlock message={LOAD_FAILED}>
          <button type="button" className={PRIMARY} onClick={onRetry}>
            Retry
          </button>
        </ErrorBlock>
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
      {filter}
    </div>
  );
}

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
  // What the two date inputs show; null means the dataset's first (Start) or
  // last (End) date. Page state only: a reload starts on the full range again.
  const [startText, setStartText] = useState<string | null>(null);
  const [endText, setEndText] = useState<string | null>(null);
  // The range last sent: only ever a valid one. A bound equal to the dataset's
  // first or last date is undefined, so the full range always has one query key.
  const [applied, setApplied] = useState<{ start?: string; end?: string }>({});
  // The one analytics request of the page. KPI cards, trend chart and top
  // products all read it from here.
  const analytics = useAnalytics(datasetId, applied.start, applied.end);
  const [leaving, setLeaving] = useState(false);
  // Once the server said 404 or 401 for this dataset the page stays on that
  // card, even after the session and the cached answers are gone.
  const [gone, setGone] = useState<{ id: string; kind: "expired" | "unauthorized" } | null>(null);

  const kinds = [
    meta.error === null ? null : errorKind(meta.error),
    analytics.error === null ? null : errorKind(analytics.error),
  ];
  const terminal = kinds.includes("expired")
    ? "expired"
    : kinds.includes("unauthorized")
      ? "unauthorized"
      : null;

  useEffect(() => {
    if (terminal === null) return;
    // Justified exception: the query cache is emptied just below, so the terminal answer
    // has to be copied into state here or the page would flip back to a blank dashboard.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGone({ id: datasetId, kind: terminal });
    // Only this dataset's own session is let go of, never another one's.
    if (readSession()?.id === datasetId) clearSession();
    queryClient.removeQueries({ queryKey: ["meta", datasetId] });
    queryClient.removeQueries({ queryKey: ["analytics", datasetId] });
  }, [terminal, datasetId, queryClient]);

  const hasToken = tokenFor(datasetId) !== null;
  const blocked =
    (gone !== null && gone.id === datasetId ? gone.kind : null) ??
    terminal ??
    (hasToken ? null : "unauthorized");
  if (blocked === "expired") return <Expired />;
  if (blocked === "unauthorized") return <CannotOpen />;

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
  const min = data?.date_range?.min;
  const max = data?.date_range?.max;
  const start = startText ?? min ?? "";
  const end = endText ?? max ?? "";

  // Takes the new texts of the two inputs; sends a range only if it is valid.
  function change(nextStart: string, nextEnd: string) {
    setStartText(nextStart);
    setEndText(nextEnd);
    if (min === undefined || max === undefined) return;
    if (!validateRange(min, max, nextStart, nextEnd).valid) return;
    setApplied({
      start: nextStart === min ? undefined : nextStart,
      end: nextEnd === max ? undefined : nextEnd,
    });
  }

  function reset() {
    setStartText(null);
    setEndText(null);
    setApplied({});
  }

  // Reset from the "range not valid" block: when the full range is already the
  // one that failed, the same request is sent again.
  function resetAfterBadRange() {
    const alreadyFull = applied.start === undefined && applied.end === undefined;
    reset();
    if (alreadyFull) void analytics.refetch();
  }

  const failure = analytics.isError ? describeError(analytics.error) : null;

  return (
    <div className="space-y-8">
      <Header />

      {warnings.length > 0 && <WarningNotice warnings={warnings} onDismiss={onDismissWarnings} />}

      <section aria-label="Date range">
        <SectionBoundary resetKey={meta.dataUpdatedAt}>
          <DateRangeCard
            data={data}
            failed={meta.isError}
            onRetry={() => void meta.refetch()}
            leaving={leaving}
            onAnalyzeAnother={analyzeAnother}
            filter={
              <DateRangeFilter
                min={min}
                max={max}
                start={start}
                end={end}
                onStartChange={(value) => change(value, end)}
                onEndChange={(value) => change(start, value)}
                onReset={reset}
                updating={analytics.isPlaceholderData}
              />
            }
          />
        </SectionBoundary>
      </section>

      {analytics.data?.kpis?.orders === 0 && <NoSalesNotice onReset={reset} />}

      <section aria-label="Key figures">
        <SectionBoundary resetKey={analytics.dataUpdatedAt}>
          {failure !== null ? (
            <ErrorBlock message={failure.message}>
              {failure.kind === "bad_range" || failure.kind === "bad_request" ? (
                <button type="button" className={SECONDARY} onClick={resetAfterBadRange}>
                  Reset
                </button>
              ) : (
                <button type="button" className={PRIMARY} onClick={() => void analytics.refetch()}>
                  Retry
                </button>
              )}
            </ErrorBlock>
          ) : (
            <KpiCards kpis={analytics.data?.kpis} currency={analytics.data?.currency} />
          )}
        </SectionBoundary>
      </section>
      <section aria-label="Sales trend">
        <SectionBoundary resetKey={analytics.dataUpdatedAt}>
          {failure === null && (
            <TrendChart
              granularity={analytics.data?.granularity}
              buckets={analytics.data?.trend}
              range={analytics.data?.range}
              currency={analytics.data?.currency}
            />
          )}
        </SectionBoundary>
      </section>
      <section aria-label="Top products">
        <SectionBoundary resetKey={analytics.dataUpdatedAt}>
          {failure === null && (
            <TopProducts
              topProducts={analytics.data?.top_products}
              currency={analytics.data?.currency}
              range={analytics.data?.range}
            />
          )}
        </SectionBoundary>
      </section>
    </div>
  );
}
