import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCount, formatMoney } from "../lib/format";
import { formatMoneyShort } from "./TrendChart";
import type { Summary } from "../lib/types";

// Colours from _docs/design-system.md (Charts): one colour for every bar.
const BAR = "#432dd7"; // indigo-700
const GRID = "#e2e8f0"; // slate-200
const AXIS = "#62748e"; // slate-500
const TICK = "#45556c"; // slate-600
const TOOLTIP_BORDER = "#cad5e2"; // slate-300
const TOOLTIP_TEXT = "#0f172b";

const CARD = "rounded-lg border border-slate-200 bg-white p-6 space-y-2";
const EMPTY = "flex h-72 items-center justify-center text-center text-slate-600";
const TH = "px-3 py-2 text-sm font-semibold text-slate-700";
const TD = "px-3 py-2 align-top text-sm wrap-anywhere";

// Longest name drawn on the chart's label axis; the table has the full name.
const MAX_LABEL_CHARS = 22;

type Product = Summary["top_products"][number];

// "A very long product na…": at most `max` characters, never splitting a
// surrogate pair. The text stays text (React/SVG escape it).
export function shortenName(name: string, max: number = MAX_LABEL_CHARS): string {
  const chars = Array.from(name);
  return chars.length <= max ? name : `${chars.slice(0, max - 1).join("")}…`;
}

// The sentence for screen readers: "Top 10 products by gross sales from 2025-03-01 to 2025-03-31".
export function topProductsSentence(count: number, range: { start: string; end: string }): string {
  return `Top ${count} ${count === 1 ? "product" : "products"} by gross sales from ${range.start} to ${range.end}`;
}

// Shows the best-selling products as a bar chart and a table, in the order the
// server sent them. It makes no request: the dashboard passes in the top
// products of the analytics response (topProducts is undefined while it loads).
export default function TopProducts({
  topProducts,
  currency,
  range,
}: {
  topProducts: Product[] | undefined;
  currency: string | undefined;
  range: { start: string; end: string } | undefined;
}) {
  if (topProducts === undefined || currency === undefined || range === undefined) {
    return (
      <div className={CARD} role="status" aria-busy="true">
        <h2 className="text-xl font-semibold text-slate-900">Top products</h2>
        <span className="sr-only">Loading…</span>
        <div className="h-72 w-full animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
      </div>
    );
  }

  if (topProducts.length === 0) {
    return (
      <div className={CARD}>
        <h2 className="text-xl font-semibold text-slate-900">Top products</h2>
        <div className={EMPTY}>No products sold in this range</div>
      </div>
    );
  }

  const sentence = topProductsSentence(topProducts.length, range);
  // The category axis is keyed by product_id (unique), not by name (not unique).
  const data = topProducts.map((product) => ({
    product_id: product.product_id,
    name: product.product_name,
    sales: Number(product.gross_sales),
    exact: product.gross_sales,
  }));
  const nameOf = new Map(data.map((row) => [row.product_id, row.name]));

  return (
    <div className={CARD}>
      <h2 className="text-xl font-semibold text-slate-900">Top products</h2>
      <p className="text-sm text-slate-600">{sentence}</p>
      <div role="img" aria-label={sentence} className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis
              type="number"
              domain={[0, "auto"]}
              tickFormatter={(value: number) => formatMoneyShort(value, currency)}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <YAxis
              type="category"
              dataKey="product_id"
              width={170}
              interval={0}
              tickFormatter={(id: string) => shortenName(nameOf.get(id) ?? id)}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <Tooltip
              cursor={{ fill: GRID, fillOpacity: 0.5 }}
              labelFormatter={(id) => nameOf.get(String(id)) ?? String(id)}
              formatter={(_value, _name, item) => [
                formatMoney((item.payload as { exact: string }).exact, currency),
                "Gross sales",
              ]}
              contentStyle={{
                background: "#ffffff",
                border: `1px solid ${TOOLTIP_BORDER}`,
                borderRadius: 6,
                color: TOOLTIP_TEXT,
                fontSize: 14,
              }}
              itemStyle={{ color: TOOLTIP_TEXT }}
            />
            <Bar dataKey="sales" name="Gross sales" fill={BAR} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left">
          <thead className="bg-slate-100">
            <tr>
              <th className={TH}>Product</th>
              <th className={`${TH} text-right tabular-nums`}>Gross sales</th>
              <th className={`${TH} text-right tabular-nums`}>Units sold</th>
              <th className={`${TH} text-right tabular-nums`}>Orders</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {topProducts.map((product) => (
              <tr key={product.product_id}>
                <td className={`${TD} text-slate-900`}>{product.product_name}</td>
                <td className={`${TD} text-right tabular-nums`}>{formatMoney(product.gross_sales, currency)}</td>
                <td className={`${TD} text-right tabular-nums`}>{formatCount(product.units_sold)}</td>
                <td className={`${TD} text-right tabular-nums`}>{formatCount(product.distinct_orders)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
