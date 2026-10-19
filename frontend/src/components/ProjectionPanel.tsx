import { formatCount, formatMoney, formatMonthYear } from "../lib/format";
import type {
  Projected12MonthCustomerValue,
  ProjectedCustomerValueCohort,
  ProjectionEligibilityCondition,
} from "../lib/types";
import ErrorBlock from "./ErrorBlock";

const PRIMARY =
  "inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700 disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600 bg-indigo-700 text-white enabled:hover:bg-indigo-800";

export interface ProjectionPanelProps {
  projection?: Projected12MonthCustomerValue;
  currency: string;
  loading?: boolean;
  error?: boolean;
  updating?: boolean;
  onRetry: () => void;
}

function ConditionActual({ condition }: { condition: ProjectionEligibilityCondition }) {
  if (condition.actual === null) return <>not available</>;
  if (condition.code === "customer_coverage") {
    const coverage = Number(condition.actual);
    return Number.isFinite(coverage) ? `${(coverage * 100).toFixed(2)}%` : String(condition.actual);
  }
  return <>{typeof condition.actual === "number" ? formatCount(condition.actual) : condition.actual}</>;
}

function Conditions({ conditions }: { conditions: ProjectionEligibilityCondition[] }) {
  const ordered = [...conditions].sort((left, right) => Number(left.passed) - Number(right.passed));
  return (
    <ul className="space-y-2">
      {ordered.map((condition) => (
        <li key={condition.code} className="flex flex-wrap items-start justify-between gap-3 text-sm">
          <span className="font-medium">{condition.label}</span>
          <span className={condition.passed ? "text-emerald-900" : "text-red-900"}>
            <span aria-hidden>{condition.passed ? "✓" : "✕"}</span>{" "}
            <strong>{condition.passed ? "Met" : "Not met"}</strong> · this dataset: <ConditionActual condition={condition} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function LoadingPanel() {
  return (
    <section aria-label="Projected 12-Month Customer Value" role="status" aria-busy="true" className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
      <h2 className="text-xl font-semibold text-slate-900">Projected 12-Month Customer Value</h2>
      <div className="animate-pulse motion-reduce:animate-none h-8 w-32 rounded bg-slate-200" />
      <div className="animate-pulse motion-reduce:animate-none h-8 w-32 rounded bg-slate-200" />
      <div className="animate-pulse motion-reduce:animate-none h-8 w-32 rounded bg-slate-200" />
    </section>
  );
}

function FailedPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <section aria-label="Projected 12-Month Customer Value" className="space-y-4">
      <h2 className="text-xl font-semibold text-slate-900">Projected 12-Month Customer Value</h2>
      <ErrorBlock message="Something went wrong loading this data">
        <button type="button" className={PRIMARY} onClick={onRetry}>Retry</button>
      </ErrorBlock>
    </section>
  );
}

function EstimateCard({ label, value, currency, dashed = false }: { label: string; value: string; currency: string; dashed?: boolean }) {
  return (
    <div className={`rounded-lg border bg-white p-4 ${dashed ? "border-dashed border-indigo-700" : "border-slate-200"}`}>
      <dt className="text-sm font-medium text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums wrap-anywhere">{formatMoney(value, currency)}</dd>
    </div>
  );
}

function cohortDate(value: string): Date {
  return new Date(`${value}-01T00:00:00Z`);
}

function CohortRow({ cohort, currency }: { cohort: ProjectedCustomerValueCohort; currency: string }) {
  return (
    <tr>
      <td className="px-3 py-2 align-top text-sm wrap-anywhere">{formatMonthYear(cohortDate(cohort.cohort_month))}</td>
      <td className="px-3 py-2 align-top text-right text-sm tabular-nums">{formatCount(cohort.customers)}</td>
      <td className="px-3 py-2 align-top text-right text-sm tabular-nums">{formatCount(cohort.observed_age_months)}</td>
      <td className="px-3 py-2 align-top text-sm">{cohort.mature ? "Yes" : "No"}</td>
      <td className="px-3 py-2 align-top text-right text-sm tabular-nums">{formatMoney(cohort.observed_per_customer, currency)}</td>
      <td className="border border-dashed border-indigo-700 px-3 py-2 align-top text-right text-sm tabular-nums">{formatMoney(cohort.projected_per_customer_estimate, currency)}</td>
      <td className="border border-dashed border-indigo-700 px-3 py-2 align-top text-right text-sm tabular-nums">{formatMoney(cohort.total_per_customer_estimate, currency)}</td>
    </tr>
  );
}

export default function ProjectionPanel({ projection, currency, loading = false, error = false, updating = false, onRetry }: ProjectionPanelProps) {
  if (error) return <FailedPanel onRetry={onRetry} />;
  if (loading || projection === undefined) return <LoadingPanel />;

  const { eligibility, value } = projection;
  const matureCohorts = value?.contributing_mature_cohorts ?? 0;
  const customerCount = value?.customers ?? 0;
  const description = "Estimate of average gross sales per customer in their first 12 months, based on how earlier customer groups behaved. It is not a guarantee of future sales and does not include costs, discounts or refunds.";
  return (
    <section aria-label="Projected 12-Month Customer Value" className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-center gap-3">
      <h2 className="text-xl font-semibold text-slate-900">Projected 12-Month Customer Value</h2>
        <span className="rounded border border-dashed border-indigo-700 px-3 py-1 text-sm font-semibold">Estimate</span>
        <span className="text-sm text-slate-600">12-month horizon</span>
        {updating && <span role="status" className="text-sm text-slate-600">Updating…</span>}
      </div>
      {eligibility.status === "eligible" && value !== null ? (
        <>
          <dl className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <EstimateCard label="Observed so far" value={value.observed_per_customer} currency={currency} />
            <EstimateCard label="Projected (estimate)" value={value.projected_per_customer_estimate} currency={currency} dashed />
            <EstimateCard label="12-month total (estimate)" value={value.total_per_customer_estimate} currency={currency} dashed />
          </dl>
          <p className="text-sm text-slate-600">
            Data up to {projection.data_cutoff} · based on {formatCount(matureCohorts)} {matureCohorts === 1 ? "mature cohort" : "mature cohorts"} · {formatCount(customerCount)} customers
          </p>
          <p className="text-sm text-slate-600">{description}</p>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table aria-label="Projected 12-Month Customer Value table" className="w-full text-left">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-3 py-2 text-sm font-semibold text-slate-700">Cohort</th>
                  <th className="px-3 py-2 text-right text-sm font-semibold text-slate-700 tabular-nums">Customers</th>
                  <th className="px-3 py-2 text-right text-sm font-semibold text-slate-700 tabular-nums">Months observed</th>
                  <th className="px-3 py-2 text-sm font-semibold text-slate-700">Mature</th>
                  <th className="px-3 py-2 text-right text-sm font-semibold text-slate-700 tabular-nums">Observed</th>
                  <th className="border border-dashed border-indigo-700 px-3 py-2 text-right text-sm font-semibold text-slate-700 tabular-nums">Projected (estimate)</th>
                  <th className="border border-dashed border-indigo-700 px-3 py-2 text-right text-sm font-semibold text-slate-700 tabular-nums">12-month total (estimate)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">{value.cohorts.map((cohort) => <CohortRow key={cohort.cohort_month} cohort={cohort} currency={currency} />)}</tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <h4 className="text-lg font-semibold text-slate-900">{eligibility.status === "unavailable" ? "Add a customer_id column to your file to see this estimate." : "Not enough data for a reliable estimate"}</h4>
          <Conditions conditions={eligibility.conditions} />
          <p className="text-sm text-slate-600">{description}</p>
        </>
      )}
    </section>
  );
}
