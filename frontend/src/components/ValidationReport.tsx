import type { Issue } from "../lib/types";

const TH = "px-3 py-2 text-sm font-semibold text-slate-700";
const TD = "px-3 py-2 align-top text-sm wrap-anywhere";

const count = (n: number) => n.toLocaleString("en-US");
const plural = (n: number, word: string) => `${count(n)} ${word}${n === 1 ? "" : "s"}`;

// The report for a rejected upload (422 validation_failed). All text from the
// server (reasons, fields) is rendered as text, never as HTML.
export default function ValidationReport({
  errors,
  errorCount,
  warnings,
}: {
  errors: Issue[];
  errorCount?: number;
  warnings: Issue[];
}) {
  const total = Math.max(errorCount ?? errors.length, errors.length);

  return (
    <section aria-label="Validation report" className="space-y-4">
      <div
        role="alert"
        className="space-y-3 rounded-md border border-l-4 border-red-700 bg-red-50 p-3 text-sm text-red-900"
      >
        <p>
          <span aria-hidden>✕</span> <strong>Error</strong> The file was rejected and
          nothing was imported: {plural(total, "error")} to fix.
        </p>
        {total > errors.length && (
          <p>
            Showing the first {count(errors.length)} of {count(total)} errors
          </p>
        )}
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white text-slate-900">
          <table aria-label="Errors" className="w-full text-left">
            <thead className="bg-slate-100">
              <tr>
                <th className={TH}>Row</th>
                <th className={TH}>Field</th>
                <th className={TH}>Code</th>
                <th className={TH}>Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {errors.map((issue, index) => (
                <tr key={index}>
                  <td className={TD}>{issue.row_number ?? "File"}</td>
                  <td className={TD}>{issue.field ?? "—"}</td>
                  <td className={`${TD} font-mono`}>{issue.code}</td>
                  <td className={TD}>{issue.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="space-y-2 rounded-md border border-l-4 border-dashed border-amber-700 bg-amber-50 p-3 text-sm text-amber-900">
          <h2 className="text-xl font-semibold text-slate-900">Warnings</h2>
          <p>
            <span aria-hidden>⚠</span> <strong>Warning</strong> These are not the reason
            the file was rejected. Fix the errors above.
          </p>
          <ul className="list-disc space-y-1 pl-6">
            {warnings.map((issue, index) => (
              <li key={index} className="wrap-anywhere">
                {issue.field !== null && (
                  <>
                    <span className="font-mono">{issue.field}</span>:{" "}
                  </>
                )}
                {issue.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
