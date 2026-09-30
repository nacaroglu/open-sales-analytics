import { useId } from "react";

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700";
const BUTTON = `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold ${FOCUS} disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600`;
const SECONDARY = `${BUTTON} border border-slate-500 bg-white text-slate-900 enabled:hover:bg-slate-100`;
const INPUT = `mt-1 block h-10 w-full rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-600 aria-[invalid=true]:border-2 aria-[invalid=true]:border-red-700 ${FOCUS}`;

export interface RangeErrors {
  start: string | null;
  end: string | null;
}

// A real calendar date written YYYY-MM-DD with a four-digit year. A browser
// reports a five-digit year as "12025-03-01", which must not pass.
// No Date object: the text is checked as it is, so no time zone can touch it.
export function isIsoDate(text: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (match === null) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const last = month === 2 ? (leap ? 29 : 28) : [4, 6, 9, 11].includes(month) ? 30 : 31;
  return day <= last;
}

// Validates the two inputs against the dataset's first and last date. An empty
// input (a date being typed) has no error and is not a valid range yet. The
// dates are compared as text: YYYY-MM-DD sorts like the dates it names.
export function validateRange(
  min: string,
  max: string,
  start: string,
  end: string,
): { errors: RangeErrors; valid: boolean } {
  const inside = (value: string) => isIsoDate(value) && value >= min && value <= max;
  const errors: RangeErrors = { start: null, end: null };
  if (start !== "" && !inside(start)) {
    errors.start = `Start date must be between ${min} and ${max}`;
  }
  if (end !== "" && !inside(end)) {
    errors.end = `End date must be between ${min} and ${max}`;
  }
  if (start !== "" && end !== "" && errors.start === null && errors.end === null && start > end) {
    errors.start = "Start date must be on or before end date";
  }
  const valid = start !== "" && end !== "" && errors.start === null && errors.end === null;
  return { errors, valid };
}

function FieldError({ id, message }: { id: string; message: string }) {
  return (
    <p id={id} role="alert" className="mt-1 text-sm font-medium text-red-800">
      <span aria-hidden>✕</span> {message}
    </p>
  );
}

// The last row of the Date range card. It makes no request: the dashboard owns
// the range and tells it what to show. min and max are undefined while the
// metadata loads or has failed; then everything is disabled and empty.
export default function DateRangeFilter({
  min,
  max,
  start,
  end,
  onStartChange,
  onEndChange,
  onReset,
  updating,
}: {
  min: string | undefined;
  max: string | undefined;
  start: string;
  end: string;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
  onReset: () => void;
  updating: boolean;
}) {
  const id = useId();
  const errors =
    min !== undefined && max !== undefined
      ? validateRange(min, max, start, end).errors
      : { start: null, end: null };
  const startErrorId = `${id}-start-error`;
  const endErrorId = `${id}-end-error`;
  const atFullRange = start === min && end === max;
  const disabled = min === undefined || max === undefined;

  return (
    <div className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4">
      <div className="w-44">
        <label htmlFor={`${id}-start`} className="block text-sm font-medium">
          Start date
        </label>
        <input
          id={`${id}-start`}
          type="date"
          className={INPUT}
          value={disabled ? "" : start}
          min={min}
          max={max}
          disabled={disabled}
          aria-invalid={errors.start !== null ? "true" : undefined}
          aria-describedby={errors.start !== null ? startErrorId : undefined}
          onChange={(event) => onStartChange(event.target.value)}
          onBlur={() => {
            if (min !== undefined && start === "") onStartChange(min);
          }}
        />
        {errors.start !== null && <FieldError id={startErrorId} message={errors.start} />}
      </div>
      <div className="w-44">
        <label htmlFor={`${id}-end`} className="block text-sm font-medium">
          End date
        </label>
        <input
          id={`${id}-end`}
          type="date"
          className={INPUT}
          value={disabled ? "" : end}
          min={min}
          max={max}
          disabled={disabled}
          aria-invalid={errors.end !== null ? "true" : undefined}
          aria-describedby={errors.end !== null ? endErrorId : undefined}
          onChange={(event) => onEndChange(event.target.value)}
          onBlur={() => {
            if (max !== undefined && end === "") onEndChange(max);
          }}
        />
        {errors.end !== null && <FieldError id={endErrorId} message={errors.end} />}
      </div>
      <button type="button" className={SECONDARY} disabled={disabled || atFullRange} onClick={onReset}>
        Reset
      </button>
      {updating && (
        <p role="status" className="self-center text-sm text-slate-600">
          Updating…
        </p>
      )}
    </div>
  );
}
