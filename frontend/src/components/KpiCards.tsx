import { formatCount, formatMoney } from "../lib/format";
import type { ComparedCount, ComparedMoney, Overview, Summary } from "../lib/types";

const CARD = "rounded-lg border border-slate-200 bg-white p-4";
const LABEL = "text-sm font-medium text-slate-600";
const VALUE = "mt-1 text-2xl lg:text-xl font-semibold tabular-nums wrap-anywhere";

type Kpis = Summary["kpis"] | Overview["kpis"];
type Metric = string | number | ComparedMoney | ComparedCount;

function isCompared(value: Metric): value is ComparedMoney | ComparedCount {
  return typeof value === "object" && value !== null && "value" in value;
}

function display(value: Metric | undefined, currency: string | undefined): string | undefined {
  if (value === undefined || currency === undefined) return undefined;
  if (typeof value === "string") return formatMoney(value, currency);
  if (typeof value === "number") return formatCount(value);
  if (typeof value === "object" && value !== null && "value" in value) {
    return typeof value.value === "string" ? formatMoney(value.value, currency) : formatCount(value.value);
  }
  throw new Error("Metric value is unreadable");
}

function Delta({ value, currency }: { value: Metric; currency: string }) {
  if (!isCompared(value) || value.comparison_value === null || value.absolute_change === null) return null;
  const absolute = typeof value.absolute_change === "string" ? formatMoney(value.absolute_change, currency) : formatCount(value.absolute_change);
  const negative = typeof value.absolute_change === "string" ? value.absolute_change.startsWith("-") : value.absolute_change < 0;
  const signedAbsolute = negative ? `−${absolute.replace("-", "")}` : `+${absolute}`;
  const percent = value.percent_change === null ? null : `${value.percent_change.startsWith("-") ? "−" : "+"}${value.percent_change.replace("-", "")}%`;
  const direction = negative ? "down" : "up";
  return <span className="mt-1 block text-sm font-normal text-slate-600"><span className="sr-only">{direction}</span>vs {display(value.comparison_value, currency)}: {signedAbsolute}{percent === null ? "" : ` (${percent})`}</span>;
}

// Shows the four headline numbers. It makes no request: the dashboard passes in
// the kpis (undefined while the analytics load) and the dataset's currency.
export default function KpiCards({
  kpis,
  currency,
}: {
  kpis: Kpis | undefined;
  currency: string | undefined;
}) {
  const cards: { label: string; metric: Metric | undefined }[] = [
    {
      label: "Gross sales",
      metric: kpis?.gross_sales,
    },
    { label: "Orders", metric: kpis?.orders },
    { label: "Units sold", metric: kpis?.units_sold },
    {
      label: "Average order value",
      metric: kpis?.average_order_value,
    },
  ];
  const loading = kpis === undefined || currency === undefined;

  const list = (
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map(({ label, metric }) => (
        <div key={label} className={CARD}>
          <dt className={LABEL}>{label}</dt>
          <dd className={VALUE}>
            {display(metric, currency) ?? (
              <span className="block h-8 w-32 animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
            )}
            {currency !== undefined && metric !== undefined && <Delta value={metric} currency={currency} />}
          </dd>
        </div>
      ))}
    </dl>
  );

  if (!loading) return list;
  return (
    <div role="status" aria-busy="true">
      <span className="sr-only">Loading…</span>
      {list}
    </div>
  );
}
