import type { Comparison } from "../lib/types";

export default function ComparisonDates({ comparison }: { comparison: Comparison }) {
  const mode = comparison.mode === "previous_year" ? "same period last year" : "previous period";
  if (comparison.state !== "available") {
    return <p role="status" className="text-sm text-slate-600"><strong>Comparison unavailable</strong> — {comparison.reason} ({comparison.comparison.start} to {comparison.comparison.end}, {mode})</p>;
  }
  return <p className="text-sm text-slate-600">{comparison.current.start} to {comparison.current.end} compared with {comparison.comparison.start} to {comparison.comparison.end} ({mode})</p>;
}
