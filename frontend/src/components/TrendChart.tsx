import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDay, formatMonthYear, formatMoney } from "../lib/format";
import type { Granularity, Summary } from "../lib/types";

// Colours from _docs/design-system.md (Charts). Recharts takes hex values, so
// these are the same colours as the Tailwind classes named next to them.
const LINE = "#432dd7"; // indigo-700
const GRID = "#e2e8f0"; // slate-200
const AXIS = "#62748e"; // slate-500
const TICK = "#45556c"; // slate-600
const TOOLTIP_BORDER = "#cad5e2"; // slate-300
const TOOLTIP_TEXT = "#0f172b";

const CARD = "rounded-lg border border-slate-200 bg-white p-6 space-y-2";
const EMPTY = "flex h-72 items-center justify-center text-center text-slate-600";

type Bucket = Summary["trend"][number];

const NOUN: Record<Granularity, string> = { daily: "Daily", weekly: "Weekly", monthly: "Monthly" };

// Every date is formatted from its YYYY-MM-DD text as a UTC instant, so the
// browser's time zone can never move it to the neighbouring day.

// Reads "2025-03-01" as a UTC date. Anything else is null.
export function parseBucketDate(text: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const date = new Date(`${text}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

// Axis label: "5 Mar", "Week of 3 Mar", "Mar 2025".
export function bucketLabel(text: string, granularity: Granularity): string {
  const date = parseBucketDate(text);
  if (date === null) return text;
  if (granularity === "monthly") return formatMonthYear(date);
  const day = formatDay(date, false);
  return granularity === "weekly" ? `Week of ${day}` : day;
}

// Tooltip label: the same with the year, "5 Mar 2025", "Week of 3 Mar 2025", "Mar 2025".
export function bucketLabelWithYear(text: string, granularity: Granularity): string {
  const date = parseBucketDate(text);
  if (date === null) return text;
  if (granularity === "monthly") return formatMonthYear(date);
  const day = formatDay(date, true);
  return granularity === "weekly" ? `Week of ${day}` : day;
}

const DAY_MS = 86_400_000;

// What part of its calendar bucket (a day, a Monday-Sunday week, a calendar
// month) the inclusive range covers. `from` and `to` are the covered dates as UTC
// dates; `partial` is true when the range cuts the bucket. Coverage comes from
// the range and the calendar alone, so a day with zero sales still counts as
// covered. A day is always whole (the data holds dates only). Null for text
// that is not a date.
export interface Coverage {
  from: Date;
  to: Date;
  partial: boolean;
}

export function bucketCoverage(
  bucketStart: string,
  granularity: Granularity,
  range: { start: string; end: string },
): Coverage | null {
  const first = parseBucketDate(bucketStart);
  const start = parseBucketDate(range.start);
  const end = parseBucketDate(range.end);
  if (first === null || start === null || end === null) return null;
  let last = first;
  if (granularity === "weekly") {
    last = new Date(first.getTime() + 6 * DAY_MS);
  } else if (granularity === "monthly") {
    last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0));
  }
  const from = new Date(Math.max(first.getTime(), start.getTime()));
  const to = new Date(Math.min(last.getTime(), end.getTime()));
  if (from.getTime() > to.getTime()) return null; // a bucket outside the range: nothing to say about it
  return { from, to, partial: from.getTime() !== first.getTime() || to.getTime() !== last.getTime() };
}

// "29–31 Dec", "29 Dec–4 Jan", "29 Dec 2024–4 Jan 2025" (with the year), "5 Mar" for one day.
export function coverageLabel(coverage: Coverage, withYear: boolean): string {
  const { from, to } = coverage;
  if (from.getTime() === to.getTime()) return formatDay(from, withYear);
  const sameMonth = from.getUTCFullYear() === to.getUTCFullYear() && from.getUTCMonth() === to.getUTCMonth();
  if (sameMonth) return `${from.getUTCDate()}–${formatDay(to, withYear)}`;
  return `${formatDay(from, withYear)}–${formatDay(to, withYear)}`;
}

// Axis label of a bucket for this range: a partial week or month shows the
// dates it covers ("29–31 Dec", "10–31 Mar 2025") instead of "Week of 29 Dec"
// or the month name, which would hide the truncation.
export function axisLabel(text: string, granularity: Granularity, range: { start: string; end: string }): string {
  const coverage = bucketCoverage(text, granularity, range);
  if (coverage !== null && coverage.partial && granularity !== "daily") {
    return coverageLabel(coverage, granularity === "monthly");
  }
  return bucketLabel(text, granularity);
}

const compactFormats = new Map<string, Intl.NumberFormat>();

// Y-axis money: "$12K", "$1.2M", "$0". Falls back to the plain number for an unknown currency code.
export function formatMoneyShort(value: number, currency: string): string {
  let format = compactFormats.get(currency);
  try {
    if (format === undefined) {
      format = new Intl.NumberFormat("en-US", { style: "currency", currency, notation: "compact" });
      compactFormats.set(currency, format);
    }
    return format.format(value);
  } catch {
    return `${value} ${currency}`;
  }
}

// The sentence for screen readers and for the page: "Daily gross sales from 2025-01-01 to 2025-03-31".
export function rangeSentence(granularity: Granularity, range: { start: string; end: string }): string {
  return `${NOUN[granularity]} gross sales from ${range.start} to ${range.end}`;
}

// Shows the sales trend. It makes no request: the dashboard passes in the trend
// of the analytics response (buckets is undefined while it loads).
export default function TrendChart({
  granularity,
  buckets,
  range,
  currency,
}: {
  granularity: Granularity | undefined;
  buckets: Bucket[] | undefined;
  range: { start: string; end: string } | undefined;
  currency: string | undefined;
}) {
  if (
    granularity === undefined ||
    buckets === undefined ||
    range === undefined ||
    currency === undefined
  ) {
    return (
      <div className={CARD} role="status" aria-busy="true">
        <h2 className="text-xl font-semibold text-slate-900">Gross sales</h2>
        <span className="sr-only">Loading…</span>
        <div className="h-72 w-full animate-pulse rounded bg-slate-200 motion-reduce:animate-none" />
      </div>
    );
  }

  const sentence = rangeSentence(granularity, range);
  const noSales = buckets.every((bucket) => Number(bucket.gross_sales) === 0);
  const data = buckets.map((bucket) => ({
    bucket_start: bucket.bucket_start,
    sales: Number(bucket.gross_sales),
    exact: bucket.gross_sales,
    coverage: bucketCoverage(bucket.bucket_start, granularity, range),
  }));
  const hasPartial = data.some((point) => point.coverage?.partial);

  return (
    <div className={CARD}>
      <h2 className="text-xl font-semibold text-slate-900">
        Gross sales — {granularity}
      </h2>
      <p className="text-sm text-slate-600">{sentence}</p>
      {hasPartial && (
        <p className="text-sm text-slate-600">
          Partial period: the range cuts the first or last {granularity === "weekly" ? "week" : "month"}, so
          its label shows the dates it covers and its point is hollow.
        </p>
      )}
      {noSales ? (
        <div className={EMPTY}>No sales in this range</div>
      ) : (
        <div role="img" aria-label={sentence} className="h-72 w-full">
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
                        <span className="block font-semibold">
                          Partial period: {coverageLabel(coverage, true)}
                        </span>
                      )}
                    </>
                  );
                }}
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
              <Line
                type="linear"
                dataKey="sales"
                name="Gross sales"
                stroke={LINE}
                strokeWidth={2}
                dot={(props: { key?: React.Key | null; cx?: number; cy?: number; payload?: { coverage: Coverage | null } }) => {
                  const { key, cx, cy, payload } = props;
                  if (cx === undefined || cy === undefined) return <g key={key ?? undefined} />;
                  // A partial bucket gets a hollow point (white fill), so it differs by shape, not only by label.
                  const partial = payload?.coverage?.partial === true;
                  return <circle key={key ?? undefined} cx={cx} cy={cy} r={3} fill={partial ? "#ffffff" : LINE} stroke={LINE} strokeWidth={2} />;
                }}
                activeDot={{ r: 5, fill: LINE, stroke: LINE }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
