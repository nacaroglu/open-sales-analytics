import { formatCount, formatPercent } from "../lib/format";

export type CohortCell = { month_offset: number; state: string; retained_count: number | null; retention: number | string | null };
export type CohortRow = { cohort_month: string; cohort_size: number; complete_months: number; cells?: CohortCell[] };

const TH = "px-3 py-2 text-sm font-semibold text-slate-700";
const TD = "px-3 py-2 text-sm text-slate-900 text-right tabular-nums whitespace-nowrap";

// Sequential scale: one hue, lighter to darker as retention rises. Every step
// keeps slate-900 text above 4.5:1, and the cell always prints its value, so the
// shade is never the only carrier of the number.
const SCALE = [
  { below: 0.1, label: "Under 10%", className: "bg-indigo-50" },
  { below: 0.25, label: "10–25%", className: "bg-indigo-100" },
  { below: 0.5, label: "25–50%", className: "bg-indigo-200" },
  { below: 0.75, label: "50–75%", className: "bg-indigo-300" },
  { below: Infinity, label: "75% and over", className: "bg-indigo-400" },
];

export function retentionShade(retention: number): string {
  if (retention <= 0) return "bg-white";
  return (SCALE.find((step) => retention < step.below) ?? SCALE[SCALE.length - 1]).className;
}

// The cohort retention matrix as a heatmap: a cohort per row, a month offset
// per column, each cell shaded by retention and labelled with the percentage
// and the retained customers. A cell the cutoff has not reached is "Not yet
// observed", never 0%; a cell the cutoff cuts says "partial".
export default function CohortHeatmap({ rows }: { rows: CohortRow[] }) {
  const maxOffset = Math.max(-1, ...rows.flatMap((row) => (row.cells ?? []).map((cell) => Number(cell.month_offset))));
  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table aria-label="Cohort retention table" className="w-full text-left">
          <thead className="bg-slate-100">
            <tr>
              <th className={`sticky left-0 bg-slate-100 ${TH}`}>Cohort</th>
              <th className={`${TH} text-right`}>Cohort size</th>
              <th className={`${TH} text-right`}>Months observed</th>
              {Array.from({ length: maxOffset + 1 }, (_, offset) => <th key={offset} className={`${TH} text-right`}>Month {offset}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((row) => (
              <tr key={row.cohort_month}>
                <td className="sticky left-0 whitespace-nowrap bg-white px-3 py-2 text-sm text-slate-900">{row.cohort_month}</td>
                <td className={TD}>{formatCount(Number(row.cohort_size))}</td>
                <td className={TD}>{formatCount(Number(row.complete_months))}</td>
                {(row.cells ?? []).map((cell) => {
                  if (cell.state === "not_observed" || cell.retention === null) {
                    return <td key={cell.month_offset} className="border border-dashed border-slate-500 bg-white px-3 py-2 text-sm text-slate-600">Not yet observed</td>;
                  }
                  const retention = Number(cell.retention);
                  return (
                    <td key={cell.month_offset} className={`${TD} ${retentionShade(retention)}`}>
                      {formatPercent(retention, 1)} ({formatCount(Number(cell.retained_count))})
                      {cell.state === "partial" && <span className="block text-xs">partial</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600" aria-label="Retention shading key" role="group">
        <span>Shading, retention:</span>
        <span className="inline-flex items-center gap-1"><span aria-hidden className="h-4 w-4 rounded border border-slate-200 bg-white" />0%</span>
        {SCALE.map((step) => (
          <span key={step.label} className="inline-flex items-center gap-1"><span aria-hidden className={`h-4 w-4 rounded border border-slate-200 ${step.className}`} />{step.label}</span>
        ))}
        <span className="inline-flex items-center gap-1"><span aria-hidden className="h-4 w-4 rounded border border-dashed border-slate-500 bg-white" />Not yet observed</span>
      </div>
    </>
  );
}
