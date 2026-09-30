import { formatCount, formatMoney } from "../lib/format";
import type { Summary } from "../lib/types";

const CARD = "rounded-lg border border-slate-200 bg-white p-4";
const LABEL = "text-sm font-medium text-slate-600";
const VALUE = "mt-1 text-2xl lg:text-xl font-semibold tabular-nums wrap-anywhere";

type Kpis = Summary["kpis"];

// Shows the four headline numbers. It makes no request: the dashboard passes in
// the kpis (undefined while the analytics load) and the dataset's currency.
export default function KpiCards({
  kpis,
  currency,
}: {
  kpis: Kpis | undefined;
  currency: string | undefined;
}) {
  const cards: { label: string; value: string | undefined }[] = [
    {
      label: "Gross sales",
      value: kpis && currency ? formatMoney(kpis.gross_sales, currency) : undefined,
    },
    { label: "Orders", value: kpis ? formatCount(kpis.orders) : undefined },
    { label: "Units sold", value: kpis ? formatCount(kpis.units_sold) : undefined },
    {
      label: "Average order value",
      value: kpis && currency ? formatMoney(kpis.average_order_value, currency) : undefined,
    },
  ];
  const loading = kpis === undefined || currency === undefined;

  const list = (
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {cards.map(({ label, value }) => (
        <div key={label} className={CARD}>
          <dt className={LABEL}>{label}</dt>
          <dd className={VALUE}>
            {value ?? (
              <span className="block h-8 w-32 animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
            )}
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
