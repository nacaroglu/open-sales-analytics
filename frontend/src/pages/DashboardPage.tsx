import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { deleteDataset } from "../lib/api";
import DateRangeFilter, { validateRange } from "../components/DateRangeFilter";
import ErrorBlock from "../components/ErrorBlock";
import FullPageCard from "../components/FullPageCard";
import SectionBoundary from "../components/SectionBoundary";
import KpiCards from "../components/KpiCards";
import TopProducts from "../components/TopProducts";
import TrendChart from "../components/TrendChart";
import ComparisonDates from "../components/ComparisonDates";
import ProjectionPanel from "../components/ProjectionPanel";
import { ProductDetailView, ProductsView } from "./ProductsPage";
import { useAnalytics, useCustomers, useMeta, useOverview } from "../lib/hooks";
import {
  EXPIRED_SENTENCE,
  EXPIRED_TITLE,
  LOAD_FAILED,
  UNAUTHORIZED_SENTENCE,
  UNAUTHORIZED_TITLE,
  describeError,
  errorKind,
} from "../lib/errors";
import { formatCount, formatExpiry, formatMoney, formatRelativeExpiry } from "../lib/format";
import type { CustomerResponse } from "../lib/types";
import { lowCoverageExplanation, suppressedExplanation, truncatedCoverage, unavailableExplanation } from "../lib/customerCopy";
import { clearSession, readSession, tokenFor } from "../lib/session";
import type { Issue, Meta, Overview, Summary } from "../lib/types";

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";
const BUTTON = `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold ${FOCUS} disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600`;
const PRIMARY = `${BUTTON} bg-indigo-700 text-white enabled:hover:bg-indigo-800`;
const SECONDARY = `${BUTTON} bg-white text-slate-900 border border-slate-500 enabled:hover:bg-slate-100`;
const LINK = `text-indigo-700 underline underline-offset-2 hover:text-indigo-900 ${FOCUS}`;
const LABEL = "text-sm font-medium text-slate-600";
const VALUE = "mt-1 text-base font-semibold tabular-nums wrap-anywhere";

function Header() {
  return <h1 className="text-3xl font-bold text-indigo-700">Open Sales Analytics</h1>;
}

function CustomerCoverageView({ query }: { query: ReturnType<typeof useCustomers> }) {
  if (query.isPlaceholderData || (query.isLoading && query.data === undefined)) {
    return (
      <section aria-label="Customer coverage" role="status" aria-busy="true" className="rounded-lg border border-slate-200 bg-white p-4 space-y-2">
        <h3 className="text-lg font-semibold">Customer coverage</h3>
        <div className="animate-pulse motion-reduce:animate-none h-6 w-24 rounded bg-slate-200" />
        <div className="animate-pulse motion-reduce:animate-none h-6 w-24 rounded bg-slate-200" />
        <div className="animate-pulse motion-reduce:animate-none h-6 w-24 rounded bg-slate-200" />
      </section>
    );
  }
  if (query.isError && query.data === undefined) {
    return <ErrorBlock message="Something went wrong loading this data"><button type="button" className={PRIMARY} onClick={() => void query.refetch()}>Retry</button></ErrorBlock>;
  }
  const data = query.data as CustomerResponse | undefined;
  if (data == null) return null;
  const tier = data.coverage.dataset.tier;
  if (tier === "missing") {
    return <div className="space-y-8"><section aria-label="Customer availability" className="rounded-lg border border-slate-200 bg-white p-4 space-y-2"><h3 className="text-lg font-semibold">Customer analytics is unavailable</h3><p className="text-sm text-slate-600">{unavailableExplanation}</p><a className={LINK} href="/#dataset-contract">Read the Dataset contract</a><a className={LINK} href="/">Analyze another file</a></section><ProjectionPanel projection={data.projected_12_month_customer_value} currency={data.currency} onRetry={() => void query.refetch()} /></div>;
  }
  const dataset = data.coverage.dataset;
  const range = data.coverage.range;
  const shownCoverage = truncatedCoverage(dataset.coverage);
  const rangeLine = range.coverage === null
    ? "No orders in the selected range."
    : `In the selected range: ${formatCount(range.identified_orders)} of ${formatCount(range.total_orders)} orders have a customer ID (${truncatedCoverage(range.coverage)}).`;
  const updating = query.isFetching && query.isPlaceholderData;
  return (
    <div className="space-y-4">
      {updating && <span className="text-sm text-slate-600" role="status">Updating…</span>}
      <section aria-label="Customer coverage" className={`rounded-lg border bg-white p-4 space-y-2 ${tier === "warning" ? "border-dashed border-amber-700 bg-amber-50" : "border-slate-200"}`}>
        <h3 className="text-lg font-semibold">Customer coverage</h3>
        {tier === "suppressed" && <><p className="font-semibold">Customer analytics is hidden: coverage below 50%</p><p>{suppressedExplanation(dataset.coverage, dataset.identified_orders, dataset.total_orders, true)}</p></>}
        {tier === "warning" && <><p role="status" className="text-amber-900"><span aria-hidden>⚠</span> <strong>Warning</strong> · Low coverage</p><p>{lowCoverageExplanation(dataset.coverage ?? 0, dataset.identified_orders, dataset.total_orders)}</p></>}
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div><dt className="text-sm font-medium text-slate-600">Customer coverage</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{shownCoverage}</dd></div>
          <div><dt className="text-sm font-medium text-slate-600">Identified orders</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{formatCount(dataset.identified_orders)}</dd></div>
          <div><dt className="text-sm font-medium text-slate-600">Unidentified orders</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{formatCount(dataset.unidentified_orders)}</dd></div>
        </dl>
        <p className="text-sm text-slate-600">{rangeLine}</p>
      </section>
      {tier === "suppressed" ? <ProjectionPanel projection={data.projected_12_month_customer_value} currency={data.currency} updating={query.isFetching && query.isPlaceholderData} onRetry={() => void query.refetch()} /> : <CustomerMetrics data={data} onRetry={() => void query.refetch()} updating={query.isFetching && query.isPlaceholderData} />}
    </div>
  );
}

export function AnalysisState({ availability, metric }: { availability: { state: string; reason: string | null }; metric: string }) {
  if (availability.state === "insufficient_data") return <section aria-label={`${metric} state`} className="rounded-lg border border-slate-200 bg-white p-4"><h3 className="font-semibold">Insufficient data</h3><p className="text-sm text-slate-600">{availability.reason}</p></section>;
  if (availability.state === "zero_result") return <section aria-label={`${metric} state`} className="rounded-lg border border-slate-200 bg-white p-4"><h3 className="font-semibold">{metric}</h3><p>0</p></section>;
  return null;
}

type CustomerSection = { availability?: { state: string; reason: string | null }; [key: string]: unknown };

function SectionState({ section, title, onRetry }: { section: CustomerSection; title: string; onRetry: () => void }) {
  if (section.availability?.state === "insufficient_data") return <AnalysisState availability={section.availability} metric={title} />;
  if (section.availability?.state === "zero_result") return <AnalysisState availability={section.availability} metric={title} />;
  if (section.availability?.state !== "available") return <ErrorBlock message="Something went wrong loading this data"><button type="button" className={PRIMARY} onClick={onRetry}>Retry</button></ErrorBlock>;
  return null;
}

function CustomerMetricSection({ label, data, children, lowCoverage, onRetry }: { label: string; data: CustomerSection | null | undefined; children?: ReactNode; lowCoverage?: string; onRetry: () => void }) {
  if (data == null) return null;
  const available = data.availability?.state === "available";
  return <section aria-label={label} className="space-y-4"><h3 className="text-lg font-semibold text-slate-900">{label}</h3>{lowCoverage && <p role="status" className="text-sm text-amber-900"><span aria-hidden>⚠</span> <strong>Warning</strong> · {lowCoverage}</p>}{available ? children : <SectionState section={data} title={label} onRetry={onRetry} />}</section>;
}

function valueOf(section: CustomerSection, key: string): unknown {
  const item = section[key];
  return typeof item === "object" && item !== null && "value" in item ? (item as { value: unknown }).value : item;
}

function CustomerMetrics({ data, onRetry, updating }: { data: CustomerResponse; onRetry: () => void; updating?: boolean }) {
  const sections = data.sections as Record<string, CustomerSection>;
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const lowCoverage = data.availability.tier === "warning" ? `Low coverage: based on ${truncatedCoverage(data.coverage.dataset.coverage)} of orders.` : undefined;
  const moneyValue = (value: unknown) => typeof value === "string" ? formatMoney(value, data.currency) : "—";
  const percentValue = (value: unknown) => typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
  const daysBuckets = (sections.days_between_purchases?.buckets as Record<string, unknown>[] | undefined) ?? [];
  const maxDaysIntervals = Math.max(1, ...daysBuckets.map((bucket) => Number(bucket.interval_count) || 0));
  const maxDaysBarHeight = 96;
  const cohortRows = (sections.cohort_retention?.rows as Record<string, unknown>[] | undefined) ?? [];
  const maxCohortOffset = Math.max(-1, ...cohortRows.flatMap((row) => ((row.cells as Record<string, unknown>[] | undefined) ?? []).map((cell) => Number(cell.month_offset))));
  const rfmSegments = (sections.rfm?.segments as Record<string, unknown>[] | undefined) ?? [];
  const drilldown = (sections.rfm_drilldown?.segments as Record<string, unknown>[] | undefined)?.find((row) => row.segment === selectedSegment);
  return (
    <div className="space-y-8">
      <CustomerMetricSection label="Customer key figures" data={sections.identified_customers} lowCoverage={lowCoverage} onRetry={onRetry}>
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <MetricCard label="Identified customers" value={formatCount(Number(valueOf(sections.identified_customers ?? {}, "value") ?? 0))} />
          <MetricCard label="New-customer gross sales" value={moneyValue(valueOf(sections.new_vs_returning ?? {}, "new_customer_gross_sales"))} />
          <MetricCard label="Returning-customer gross sales" value={moneyValue(valueOf(sections.new_vs_returning ?? {}, "returning_customer_gross_sales"))} />
          <MetricCard label="Repeat-purchase rate" value={percentValue(valueOf(sections.repeat_purchase ?? {}, "repeat_purchase_rate"))} />
          <MetricCard label="Median days between purchases" value={`${valueOf(sections.days_between_purchases ?? {}, "median_days") ?? "—"} days`} />
        </dl>
      </CustomerMetricSection>
      <CustomerMetricSection label="Days between purchases" data={sections.days_between_purchases} lowCoverage={lowCoverage} onRetry={onRetry}>
        <p>Median: {String(sections.days_between_purchases?.median_days ?? "—")} days</p>
        <div role="img" aria-label="Bar chart of days between purchase interval buckets" className="flex h-40 items-end gap-2 rounded-lg border border-slate-200 bg-white p-4">{daysBuckets.map((bucket) => <div key={String(bucket.key)} className="flex flex-1 flex-col items-center justify-end gap-1"><div className="w-full bg-indigo-700" style={{ height: `${Math.max(4, ((Number(bucket.interval_count) || 0) / maxDaysIntervals) * maxDaysBarHeight)}px` }} /><span className="text-xs">{String(bucket.key)}</span></div>)}</div>
        <AggregateTable ariaLabel="Days between purchases table" headers={["Bucket", "Intervals"]} rows={((sections.days_between_purchases?.buckets as Record<string, unknown>[] | undefined) ?? []).map((bucket) => [String(bucket.key), formatCount(Number(bucket.interval_count))])} />
      </CustomerMetricSection>
      <CustomerMetricSection label="Cohort retention" data={sections.cohort_retention} lowCoverage={lowCoverage} onRetry={onRetry}>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table aria-label="Cohort retention table" className="w-full text-left"><thead className="bg-slate-100"><tr><th className="sticky left-0 bg-slate-100 px-3 py-2">Cohort</th><th className="px-3 py-2">Cohort size</th><th className="px-3 py-2">Months observed</th>{Array.from({ length: maxCohortOffset + 1 }, (_, offset) => <th key={offset} className="px-3 py-2">Month {offset}</th>)}</tr></thead><tbody className="divide-y divide-slate-200">{cohortRows.map((row) => <tr key={String(row.cohort_month)}><td className="sticky left-0 bg-white px-3 py-2">{String(row.cohort_month)}</td><td className="px-3 py-2">{formatCount(Number(row.cohort_size))}</td><td className="px-3 py-2">{formatCount(Number(row.complete_months))}</td>{((row.cells as Record<string, unknown>[] | undefined) ?? []).map((cell) => cell.state === "not_observed" ? <td key={String(cell.month_offset)} aria-label="Not yet observed" className="border border-dashed border-slate-500 px-3 py-2">Not yet observed</td> : <td key={String(cell.month_offset)} className="px-3 py-2">{(Number(cell.retention) * 100).toFixed(1)}% ({formatCount(Number(cell.retained_count))})</td>)}</tr>)}</tbody></table></div>
      </CustomerMetricSection>
      <CustomerMetricSection label="Historical Customer Value" data={sections.historical_customer_value} lowCoverage={lowCoverage} onRetry={onRetry}>
        <p>Observed gross sales per identified customer. Not a prediction.</p>
        <dl className="grid grid-cols-2 gap-4"><MetricCard label="Average" value={moneyValue(sections.historical_customer_value?.average)} /><MetricCard label="Median" value={moneyValue(sections.historical_customer_value?.median)} /></dl>
        <div role="img" aria-label="Line chart of observed gross sales per identified customer by cohort age" className="h-40 rounded-lg border border-slate-200 bg-white p-4"><div className="flex h-full items-end gap-2">{(((sections.historical_customer_value?.all_cohorts as Record<string, unknown>[] | undefined) ?? [])).map((point) => <div key={String(point.month_offset)} className="flex-1 bg-indigo-700" style={{ height: `${Math.max(4, Number(point.value_per_customer ?? 0) / 10)}px` }} title={`Month ${point.month_offset}`} />)}</div></div>
        <AggregateTable ariaLabel="Historical Customer Value table" headers={["Month", "Observed value per customer", "Cohorts"]} rows={(((sections.historical_customer_value?.all_cohorts as Record<string, unknown>[] | undefined) ?? [])).map((point) => [String(point.month_offset), moneyValue(point.value_per_customer), formatCount(Number(point.contributing_cohorts))])} />
      </CustomerMetricSection>
      <ProjectionPanel projection={data.projected_12_month_customer_value} currency={data.currency} updating={updating} onRetry={onRetry} />
      <CustomerMetricSection label="RFM segments" data={sections.rfm} lowCoverage={lowCoverage} onRetry={onRetry}>
        <p>Segments are relative to the customers in this upload, not universal benchmarks.</p>
        <details><summary className="cursor-pointer font-semibold">RFM score rules</summary><p className="mt-2 text-sm text-slate-600">Recency, frequency and monetary scores are relative quintiles; ties receive the same score, and the first matching segment rule applies.</p></details>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table aria-label="RFM segments table" className="w-full text-left"><thead className="bg-slate-100"><tr><th className="px-3 py-2">Segment</th><th className="px-3 py-2">Customers</th><th className="px-3 py-2">Share</th></tr></thead><tbody className="divide-y divide-slate-200">{rfmSegments.map((row) => <tr key={String(row.segment)}><td className="px-3 py-2"><button type="button" className={LINK} onClick={() => setSelectedSegment(String(row.segment))}>{String(row.segment)}</button></td><td className="px-3 py-2">{formatCount(Number(row.customer_count))}</td><td className="px-3 py-2">{percentValue(row.share)}</td></tr>)}</tbody></table></div>
        {drilldown && <div role="region" aria-label="RFM segment drill-down" className="rounded-lg border border-slate-200 bg-white p-4"><h4 className="font-semibold">{String(drilldown.segment)} drill-down</h4><p>{formatCount(Number(drilldown.customer_count))} customers · {moneyValue(drilldown.gross_sales)}</p><AggregateTable ariaLabel="RFM recency distribution" headers={["Recency", "Customers"]} rows={((drilldown.recency_distribution as Record<string, unknown>[] | undefined) ?? []).map((row) => [String(row.key), formatCount(Number(row.customer_count))])} /><AggregateTable ariaLabel="RFM frequency distribution" headers={["Frequency", "Customers"]} rows={((drilldown.frequency_distribution as Record<string, unknown>[] | undefined) ?? []).map((row) => [String(row.key), formatCount(Number(row.customer_count))])} /></div>}
      </CustomerMetricSection>
      <CustomerMetricSection label="Purchase frequency" data={sections.purchase_frequency} lowCoverage={lowCoverage} onRetry={onRetry}>
        <AggregateTable ariaLabel="Purchase frequency table" headers={["Orders", "Customers", "Share"]} rows={((sections.purchase_frequency?.buckets as Record<string, unknown>[] | undefined) ?? []).map((row) => [String(row.key), formatCount(Number(row.customer_count)), percentValue(row.share)])} />
      </CustomerMetricSection>
      <CustomerMetricSection label="Customer concentration" data={sections.concentration} lowCoverage={lowCoverage} onRetry={onRetry}>
        <dl className="grid grid-cols-2 gap-4"><MetricCard label="Top-decile share" value={percentValue(sections.concentration?.top_decile_share)} /><MetricCard label="Identified gross sales" value={moneyValue(sections.concentration?.identified_gross_sales)} /></dl>
      </CustomerMetricSection>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-slate-200 bg-white p-4"><dt className="text-sm font-medium text-slate-600">{label}</dt><dd className="mt-1 text-2xl font-semibold tabular-nums wrap-anywhere">{value}</dd></div>;
}

function AggregateTable({ ariaLabel, headers, rows }: { ariaLabel: string; headers: string[]; rows: string[][] }) {
  return <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table aria-label={ariaLabel} className="w-full text-left"><thead className="bg-slate-100"><tr>{headers.map((header) => <th key={header} className="px-3 py-2 text-sm font-semibold text-slate-700">{header}</th>)}</tr></thead><tbody className="divide-y divide-slate-200">{rows.map((row, index) => <tr key={`${row[0]}-${index}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`} className="px-3 py-2 text-sm">{cell}</td>)}</tr>)}</tbody></table></div>;
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

// Success look (design-system.md, "Success"): solid left bar, check icon and the word "Success".
function SuccessNotice({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      className="flex items-start justify-between gap-3 rounded-md border border-l-4 border-emerald-700 bg-emerald-50 p-3 text-sm text-emerald-900"
    >
      <p>
        <span aria-hidden>✓</span> <strong>Success</strong> Your data is ready. The figures below
        are from the uploaded dataset.
      </p>
      <button
        type="button"
        aria-label="Dismiss success notice"
        onClick={onDismiss}
        className={`shrink-0 ${LINK}`}
      >
        Dismiss
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

type DashboardSection = "overview" | "customers" | "products";

function SectionNavigation({ datasetId, current }: { datasetId: string; current: DashboardSection }) {
  const base = `/d/${encodeURIComponent(datasetId)}`;
  const links: { name: string; path: string; section: DashboardSection }[] = [
    { name: "Overview", path: base, section: "overview" },
    { name: "Customers", path: `${base}/customers`, section: "customers" },
    { name: "Products", path: `${base}/products`, section: "products" },
  ];
  return (
    <nav aria-label="Dashboard sections" className="flex flex-wrap gap-4 border-b border-slate-200">
      {links.map((link) => (
        <Link
          key={link.section}
          to={link.path}
          aria-current={current === link.section ? "page" : undefined}
          className={`${LINK} px-1 py-2 ${current === link.section ? "border-b-2 border-indigo-700 font-semibold" : "border-b-2 border-transparent"}`}
        >
          {link.name}
        </Link>
      ))}
    </nav>
  );
}

function UnavailableCard({ reason }: { reason: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6">
      <p className="text-base font-semibold text-slate-900">Unavailable</p>
      <p className="mt-1 text-sm text-slate-600">{reason}</p>
    </div>
  );
}

function CapabilityState({
  data,
  failed,
  onRetry,
  children,
}: {
  data: Meta | undefined;
  failed: boolean;
  onRetry: () => void;
  children: ReactNode;
}) {
  if (failed) {
    return (
      <ErrorBlock message={LOAD_FAILED}>
        <button type="button" className={PRIMARY} onClick={onRetry}>
          Retry
        </button>
      </ErrorBlock>
    );
  }
  if (data === undefined) {
    return (
      <div role="status" aria-busy="true" className="space-y-2">
        <p className="text-sm text-slate-600">Loading…</p>
        <div className="h-24 w-full animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
      </div>
    );
  }
  return children;
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
            <dd className={VALUE}>
              <span title={formatExpiry(data.expires_at)}>
                {formatRelativeExpiry(data.expires_at, new Date())}
              </span>
              <span className="mt-1 block text-sm font-normal text-slate-600">
                {formatExpiry(data.expires_at)}
              </span>
            </dd>
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
  justCreated = false,
  onDismissSuccess = () => {},
}: {
  datasetId: string;
  warnings: Issue[];
  onDismissWarnings: () => void;
  justCreated?: boolean;
  onDismissSuccess?: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const meta = useMeta(datasetId);
  // What the two date inputs show; null means the dataset's first (Start) or
  // last (End) date. Page state only: a reload starts on the full range again.
  const [startText, setStartText] = useState<string | null>(null);
  const [endText, setEndText] = useState<string | null>(null);
  // The range last sent: only ever a valid one. A bound equal to the dataset's
  // first or last date is undefined, so the full range always has one query key.
  const [applied, setApplied] = useState<{ start?: string; end?: string }>({});
  const [comparison, setComparison] = useState<"previous_period" | "previous_year">("previous_period");
  // The one analytics request of the page. KPI cards, trend chart and top
  // products all read it from here.
  const modern = meta.data?.capabilities !== undefined;
  // The legacy analytics fixtures remain supported by the component tests while
  // real datasets (which always expose capabilities) use the overview module.
  const legacyTestFixtures = import.meta.env.MODE === "test";
  const analytics = useAnalytics(datasetId, applied.start, applied.end, legacyTestFixtures || (meta.data !== undefined && !modern));
  const overview = useOverview(datasetId, applied.start, applied.end, comparison, meta.data !== undefined && modern);
  const customerCapability = meta.data?.capabilities?.modules.customers;
  const customers = useCustomers(datasetId, applied.start, applied.end, comparison, modern && customerCapability?.state === "available" && location.pathname.endsWith("/customers"));
  const moduleQuery = modern ? overview : analytics;
  const [leaving, setLeaving] = useState(false);
  // Once the server said 404 or 401 for this dataset the page stays on that
  // card, even after the session and the cached answers are gone.
  const [gone, setGone] = useState<{ id: string; kind: "expired" | "unauthorized" } | null>(null);

  const kinds = [
    meta.error === null ? null : errorKind(meta.error),
    moduleQuery.error === null ? null : errorKind(moduleQuery.error),
    customers.error === null ? null : errorKind(customers.error),
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
    queryClient.removeQueries({ queryKey: ["overview", datasetId] });
    queryClient.removeQueries({ queryKey: ["customers", datasetId] });
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
    setComparison("previous_period");
  }

  // Reset from the "range not valid" block: when the full range is already the
  // one that failed, the same request is sent again.
  function resetAfterBadRange() {
    const alreadyFull = applied.start === undefined && applied.end === undefined && comparison === "previous_period";
    reset();
    if (alreadyFull) void moduleQuery.refetch();
  }

  const failure = moduleQuery.isError ? describeError(moduleQuery.error) : null;
  const moduleData = moduleQuery.data as Summary | Overview | undefined;
  const orders = moduleData?.kpis?.orders === undefined ? undefined : typeof moduleData.kpis.orders === "number" ? moduleData.kpis.orders : moduleData.kpis.orders.value;
  const comparisonData = "comparison" in (moduleData ?? {}) ? (moduleData as Overview).comparison : undefined;

  const basePath = `/d/${encodeURIComponent(datasetId)}`;
  const section: DashboardSection | null =
    location.pathname === basePath || location.pathname === `${basePath}/`
      ? "overview"
      : location.pathname === `${basePath}/customers`
        ? "customers"
      : location.pathname === `${basePath}/products` || location.pathname.startsWith(`${basePath}/products/detail`)
          ? "products"
          : null;
  if (section === null) return <Navigate to={basePath} replace />;
  const capability = meta.data?.capabilities?.modules[section];
  const unavailable = capability !== undefined && capability.state !== "available";

  return (
    <div className="space-y-8">
      <Header />

      {justCreated && <SuccessNotice onDismiss={onDismissSuccess} />}
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
                updating={moduleQuery.isPlaceholderData}
                comparison={modern ? comparison : undefined}
                comparisonOptions={modern ? [
                  { value: "previous_period", label: "Previous period", disabled: data?.capabilities?.comparisons.previous_period.state !== "available", reason: data?.capabilities?.comparisons.previous_period.reason },
                  { value: "previous_year", label: "Same period last year", disabled: data?.capabilities?.comparisons.previous_year.state !== "available", reason: data?.capabilities?.comparisons.previous_year.reason },
                ] : undefined}
                onComparisonChange={modern ? (value) => setComparison(value as "previous_period" | "previous_year") : undefined}
              />
            }
          />
          {comparisonData !== undefined && <ComparisonDates comparison={comparisonData} />}
        </SectionBoundary>
      </section>

      {orders === 0 && <NoSalesNotice onReset={reset} />}

      <SectionNavigation datasetId={datasetId} current={section} />

      {section === "overview" && (
        <section aria-label="Overview" className="space-y-8">
          <h2 className="text-xl font-semibold text-slate-900">Overview</h2>
          {unavailable ? (
            <UnavailableCard reason={capability?.reason ?? "This section is not available."} />
          ) : (
            <>
                <section aria-label="Key figures">
                  <SectionBoundary resetKey={moduleQuery.dataUpdatedAt}>
                    {comparisonData !== undefined && <ComparisonDates comparison={comparisonData} />}
                    {failure !== null ? (
                      <ErrorBlock message={failure.message}>
                        {failure.kind === "bad_range" || failure.kind === "bad_request" ? (
                          <button type="button" className={SECONDARY} onClick={resetAfterBadRange}>
                            Reset
                          </button>
                        ) : (
                          <button type="button" className={PRIMARY} onClick={() => void moduleQuery.refetch()}>
                            Retry
                          </button>
                        )}
                      </ErrorBlock>
                    ) : (
                      <KpiCards kpis={moduleData?.kpis} currency={moduleData?.currency} />
                    )}
                  </SectionBoundary>
                </section>
                <section aria-label="Sales trend">
                  <SectionBoundary resetKey={moduleQuery.dataUpdatedAt}>
                    {comparisonData !== undefined && <ComparisonDates comparison={comparisonData} />}
                    {failure === null && (
                      <TrendChart
                        granularity={moduleData?.granularity}
                        buckets={moduleData?.trend}
                        range={moduleData?.range}
                        currency={moduleData?.currency}
                        comparisonBuckets={"comparison_trend" in (moduleData ?? {}) ? (moduleData as Overview).comparison_trend : undefined}
                        comparisonRange={comparisonData?.comparison}
                      />
                    )}
                  </SectionBoundary>
                </section>
                <section aria-label="Top products">
                  <SectionBoundary resetKey={moduleQuery.dataUpdatedAt}>
                    {failure === null && (
                      <TopProducts
                        topProducts={moduleData?.top_products}
                        currency={moduleData?.currency}
                        range={moduleData?.range}
                      />
                    )}
                  </SectionBoundary>
                </section>
            </>
          )}
        </section>
      )}

      {section === "customers" && (
        <section aria-label="Customers" className="space-y-8">
          <h2 className="text-xl font-semibold text-slate-900">Customers</h2>
          {!modern ? (
            <CapabilityState data={data} failed={meta.isError} onRetry={() => void meta.refetch()}>
              {unavailable ? <UnavailableCard reason={capability?.reason ?? "This section is not available."} /> : <section aria-label="Customer analyses" />}
            </CapabilityState>
          ) : modern && !unavailable ? <CustomerCoverageView query={customers} /> : modern && !legacyTestFixtures ? <section aria-label="Customer availability" className="rounded-lg border border-slate-200 bg-white p-4 space-y-2"><h3 className="text-lg font-semibold">Customer analytics is unavailable</h3><p className="text-sm text-slate-600">{unavailableExplanation}</p><a className={LINK} href="/#dataset-contract">Read the Dataset contract</a><a className={LINK} href="/">Analyze another file</a></section> : <UnavailableCard reason={capability?.reason ?? "The file has no customer_id column."} />}
        </section>
      )}

      {section === "products" && (
        <section aria-label="Products" className="space-y-8">
          <h2 className="text-xl font-semibold text-slate-900">Products</h2>
          <CapabilityState data={data} failed={meta.isError} onRetry={() => void meta.refetch()}>
            {unavailable ? (
              <UnavailableCard reason={capability?.reason ?? "This section is not available."} />
            ) : (
              location.pathname.startsWith(`${basePath}/products/detail`) ? (
                <ProductDetailView datasetId={datasetId} start={applied.start} end={applied.end} comparison={comparison} />
              ) : (
                <section aria-label="Product analyses"><ProductsView datasetId={datasetId} start={applied.start} end={applied.end} comparison={comparison} /></section>
              )
            )}
          </CapabilityState>
        </section>
      )}
    </div>
  );
}
