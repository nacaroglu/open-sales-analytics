import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatMoney, formatShare } from "../lib/format";
import type { Granularity } from "../lib/types";
import { axisLabel, bucketCoverage, bucketLabelWithYear, coverageLabel, formatMoneyShort } from "./TrendChart";
import type { Coverage } from "./TrendChart";

// Colours from _docs/design-system.md (Charts), as in TrendChart.
const LINE = "#432dd7"; // indigo-700
const GRID = "#e2e8f0"; // slate-200
const AXIS = "#62748e"; // slate-500
const TICK = "#45556c"; // slate-600
const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #cad5e2", // slate-300
  borderRadius: 6,
  color: "#0f172b",
  fontSize: 14,
};
const TH = "px-3 py-2 text-sm font-semibold text-slate-700";
const TD = "px-3 py-2 align-top text-sm wrap-anywhere";
// Up to this many points every point gets a dot; more would hide the line.
const MAX_DOTS = 40;

type ShareRow = { product_id: string; product_name: string; cumulative_share: string | null };

// Cumulative share of gross sales over the products ranked by gross sales,
// with the dashed 80% reference line. The figures above it are its text alternative.
export function ParetoChart({ products, range }: { products: ShareRow[]; range: { start: string; end: string } }) {
  const data = products
    .filter((row) => row.cumulative_share !== null)
    .map((row, index) => ({
      rank: index + 1,
      name: row.product_name,
      share: Number(row.cumulative_share),
      exact: row.cumulative_share as string,
    }));
  const label = `Cumulative share of gross sales over ${data.length} products ranked by gross sales, from ${range.start} to ${range.end}`;
  return (
    <>
      <div role="img" aria-label={label} className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="rank"
              type="number"
              domain={[1, Math.max(1, data.length)]}
              allowDecimals={false}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <YAxis
              width={64}
              domain={[0, 1]}
              ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <ReferenceLine y={0.8} stroke={LINE} strokeDasharray="6 4" strokeWidth={2} />
            <Tooltip
              labelFormatter={(_rank, items) => {
                const point = items[0]?.payload as { rank: number; name: string } | undefined;
                return point === undefined ? "" : `#${point.rank} ${point.name}`;
              }}
              formatter={(_value, _name, item) => [formatShare((item.payload as { exact: string }).exact), "Cumulative share"]}
              contentStyle={TOOLTIP_STYLE}
              itemStyle={{ color: TOOLTIP_STYLE.color }}
            />
            <Line
              type="linear"
              dataKey="share"
              name="Cumulative share"
              stroke={LINE}
              strokeWidth={2}
              dot={data.length <= MAX_DOTS ? { r: 3, fill: LINE, stroke: LINE } : false}
              activeDot={{ r: 5, fill: LINE, stroke: LINE }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-sm text-slate-600">Products ranked by gross sales, left to right. Solid line: cumulative share of gross sales. Dashed line: 80% of gross sales.</p>
    </>
  );
}

// Table label with the year: the covered dates of a partial bucket, otherwise the bucket's own label.
function periodLabel(text: string, coverage: Coverage | null, granularity: Granularity): string {
  return coverage !== null && coverage.partial && granularity !== "daily" ? coverageLabel(coverage, true) : bucketLabelWithYear(text, granularity);
}

type BucketPoint = { bucket_start: string; value: string | null };

// One money series over date buckets (a product's gross sales or its weighted
// unit price), drawn like the sales trend: partial buckets get a hollow point
// and their covered dates as the label. A null value is a gap, not a zero. The
// values are repeated in a table under "Show values".
export function BucketLineChart({
  points,
  granularity,
  range,
  currency,
  seriesName,
  label,
}: {
  points: BucketPoint[];
  granularity: Granularity;
  range: { start: string; end: string };
  currency: string;
  seriesName: string;
  label: string;
}) {
  const data = points.map((point) => ({
    bucket_start: point.bucket_start,
    value: point.value === null ? null : Number(point.value),
    exact: point.value,
    coverage: bucketCoverage(point.bucket_start, granularity, range),
  }));
  return (
    <>
      <div role="img" aria-label={label} className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="bucket_start"
              tickFormatter={(value: string) => axisLabel(value, granularity, range)}
              interval="preserveStartEnd"
              minTickGap={16}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <YAxis
              width={64}
              tickFormatter={(value: number) => formatMoneyShort(value, currency)}
              stroke={AXIS}
              tick={{ fill: TICK, fontSize: 12 }}
            />
            <Tooltip
              labelFormatter={(value) => {
                const text = String(value);
                const coverage = bucketCoverage(text, granularity, range);
                return (
                  <>
                    <span>{bucketLabelWithYear(text, granularity)}</span>
                    {coverage !== null && coverage.partial && (
                      <span className="block font-semibold">Partial period: {coverageLabel(coverage, true)}</span>
                    )}
                  </>
                );
              }}
              formatter={(_value, _name, item) => {
                const exact = (item.payload as { exact: string | null }).exact;
                return [exact === null ? "No sales" : formatMoney(exact, currency), seriesName];
              }}
              contentStyle={TOOLTIP_STYLE}
              itemStyle={{ color: TOOLTIP_STYLE.color }}
            />
            <Line
              type="linear"
              dataKey="value"
              name={seriesName}
              stroke={LINE}
              strokeWidth={2}
              connectNulls={false}
              dot={(props: { key?: React.Key | null; cx?: number; cy?: number; payload?: { coverage: Coverage | null; value: number | null } }) => {
                const { key, cx, cy, payload } = props;
                if (cx === undefined || cy === undefined || payload?.value == null) return <g key={key ?? undefined} />;
                const partial = payload.coverage?.partial === true;
                return <circle key={key ?? undefined} cx={cx} cy={cy} r={3} fill={partial ? "#ffffff" : LINE} stroke={LINE} strokeWidth={2} />;
              }}
              activeDot={{ r: 5, fill: LINE, stroke: LINE }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details>
        <summary className="cursor-pointer text-sm text-indigo-700 underline underline-offset-2 hover:text-indigo-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700">
          Show values
        </summary>
        <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left">
            <thead className="bg-slate-100">
              <tr>
                <th className={TH}>Period</th>
                <th className={`${TH} text-right tabular-nums`}>{seriesName}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {data.map((point) => (
                <tr key={point.bucket_start}>
                  <td className={TD}>{periodLabel(point.bucket_start, point.coverage, granularity)}</td>
                  <td className={`${TD} text-right tabular-nums`}>{point.exact === null ? "—" : formatMoney(point.exact, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
