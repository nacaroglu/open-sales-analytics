# Design system

Read before any UI task. Today: Tailwind 4 through `@import "tailwindcss"` in `frontend/src/index.css`, no config file,
no component library (none may be added), and one placeholder `<h1 className="text-3xl font-bold text-indigo-700">`
in `<main className="p-8">`. Everything below is the rule for new UI. All classes are Tailwind's built-in ones.

- One light theme, no dark mode. System font stack only (Tailwind's default), no web fonts, no external requests: the page works offline.
- Product name: the visible `<h1>` of the upload screen is exactly "Open Sales Analytics" (`App.test.tsx` looks for it).
- The measure is "gross sales", never "revenue": the word appears nowhere (labels, tooltips, alt text, errors).
- Fixed labels: "Gross sales", "Orders", "Units sold", "Average order value", "Try sample data", "Download sample CSV", "Upload", "Reset", "Retry", "Analyze another file".
- Text from the server or the user (reasons, field names, product names) is rendered as text, never as raw HTML.
- Something not covered here: add one line to this file in your task; do not invent a private style.

## Colour roles (contrast checked with WCAG 2.x, every text pair, disabled ones included, >= 4.5:1; ratios recomputed from Tailwind 4's palette)

| Role | Classes | Ratio |
|---|---|---|
| App wrapper (page background, text) | `min-h-screen bg-slate-50 text-slate-900` | 17.0 |
| Surface (cards, tables, inputs) | `bg-white border border-slate-200` | text 17.8 |
| Muted text | `text-slate-600` | 7.6 on white, 7.2 on slate-50 |
| Link | `text-indigo-700 underline underline-offset-2 hover:text-indigo-900` | 7.7 on slate-50 (8.1 on white) |
| Primary action | `bg-indigo-700 text-white enabled:hover:bg-indigo-800` | 8.1 |
| Error | `bg-red-50 border-red-700 text-red-900` | 9.2 |
| Warning | `bg-amber-50 border-amber-700 text-amber-900` | 8.8 |
| Success | `bg-emerald-50 border-emerald-700 text-emerald-900` | 9.0 (emerald-900 on emerald-50) |

Control borders use `border-slate-500` (4.8:1 on white, 4.6 on slate-50, above the 3:1 needed for controls); decorative borders `border-slate-200`. Success (added in #42, for a finished upload) is in the States table; there is no neutral role.

## Type and spacing

| Role | Classes |
|---|---|
| Page title (h1) | `text-3xl font-bold text-indigo-700` |
| Section heading (h2) | `text-xl font-semibold text-slate-900` |
| Card label | `text-sm font-medium text-slate-600` |
| KPI value | `text-2xl lg:text-xl font-semibold tabular-nums wrap-anywhere` |
| Body | `text-base` |
| Small / help text | `text-sm text-slate-600` |
| Table header / cell | `text-sm font-semibold text-slate-700` / `text-sm text-slate-900` |
| Codes (Code column) | `font-mono text-sm` |

Spacing steps 1, 2, 3, 4, 6, 8 only. Page padding `px-8 py-8`; gap between sections `space-y-8`; card padding `p-4` (KPI) or `p-6`
(chart section); table cell `px-3 py-2`; inside a card `space-y-2`; label to control `mt-1`; button gap `gap-3`.

## Layout (768 px and up)

Supported: desktop and tablet, 768 px and wider, no horizontal page scroll at 768 px. Phones are not supported. Page: `<main className="mx-auto max-w-5xl px-8 py-8 space-y-8">`. Dashboard, top to bottom, each a `<section aria-label="...">` stacked full width: Date range, Key figures, Sales trend, Top products (the four names from #27).
Key figures: `grid grid-cols-2 lg:grid-cols-4 gap-4`. At 768 px the cards are ~340 px wide, so `$1,234,567,890.12` fits at `text-2xl`; from 1024 px they are narrower, hence `lg:text-xl` and `wrap-anywhere`, which wraps rather than overflows.

Date range section (#27 + #31) is one card `rounded-lg border border-slate-200 bg-white p-4 space-y-4`, top to bottom: right-aligned primary **Analyze another file**;
the dataset facts `<dl className="grid grid-cols-2 lg:grid-cols-4 gap-4">`, each a `<dt>` (card-label classes) over a `<dd className="mt-1 text-base font-semibold tabular-nums wrap-anywhere">`,
labelled "Period" (`2025-01-01 to 2025-03-31`, as received), "Currency" (ISO code), "Rows" (`1,234`), "Expires" (relative text first, "Expires in 23 hours", with the exact local date and time as `mt-1 block text-sm font-normal text-slate-600` below and as `title`), loading as `h-6 w-24` pulse blocks;
then `<div className="flex flex-wrap items-end gap-3 border-t border-slate-200 pt-4">` with two `<div className="w-44">` (label "Start date" / "End date" over a date input, inline error `mt-1` below it) and a secondary **Reset** button, in that order.
Wide content scrolls or wraps in its own box (`overflow-x-auto`, `wrap-anywhere`), never the page.

## Components

**Focus (every button, link, input, select):** `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700`. Never `outline-none` without this replacement.

**Buttons.** Base `inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold` plus the focus classes.

| Kind | Extra classes | Used for |
|---|---|---|
| Primary | `bg-indigo-700 text-white enabled:hover:bg-indigo-800` | Upload, Retry, Analyze another file |
| Secondary | `bg-white text-slate-900 border border-slate-500 enabled:hover:bg-slate-100` | Try sample data, Reset |
| Disabled (both) | `disabled:cursor-not-allowed disabled:border disabled:border-dashed disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600` | not clickable, dashed outline |

Busy: the button is `disabled` and the "Processing…" indicator is shown beside it. Text-only actions (Dismiss, links) use the link classes.

**Form fields.** Visible `<label className="block text-sm font-medium">` above the control, never placeholder-only; the control follows with `mt-1`.
Text, date and select: `block h-10 w-full rounded-md border border-slate-500 bg-white px-3 text-base text-slate-900 disabled:bg-slate-100 disabled:text-slate-600 disabled:cursor-not-allowed aria-[invalid=true]:border-2 aria-[invalid=true]:border-red-700` + focus classes.
File input: `block w-full text-sm file:mr-3 file:h-10 file:rounded-md file:border file:border-slate-500 file:bg-white file:px-3 file:font-medium hover:file:bg-slate-100`. Invalid: set `aria-invalid="true"` and `aria-describedby` on the control, and the inline error (below) under it.

**Card:** `rounded-lg border border-slate-200 bg-white p-4` (`p-6` for a chart section). KPI card: `<dt>`/label `text-sm font-medium text-slate-600` above the value, in a `<dl>` pair so they are read together.

**Table:** wrapper `overflow-x-auto rounded-lg border border-slate-200 bg-white`; `<table className="w-full text-left">`;
`<thead className="bg-slate-100">` with `<th className="px-3 py-2 text-sm font-semibold text-slate-700">`; `<tbody className="divide-y divide-slate-200">`;
`<td className="px-3 py-2 align-top text-sm wrap-anywhere">`. Numbers: add `text-right tabular-nums` to both th and td; text stays left.

**Error and warning** (block or inline). They differ by word and icon, not only colour.

| | Classes | Content |
|---|---|---|
| Error | `rounded-md border border-l-4 border-red-700 bg-red-50 p-3 text-sm text-red-900` and `role="alert"` | `<span aria-hidden>✕</span>` + bold "Error" + message |
| Warning / notice | `rounded-md border border-l-4 border-dashed border-amber-700 bg-amber-50 p-3 text-sm text-amber-900` | `<span aria-hidden>⚠</span>` + bold "Warning" + message |

Inline field error: `mt-1 text-sm font-medium text-red-800` with the same "✕" icon, `role="alert"`, under the field.
Warnings from an accepted upload are a dismissible notice: warning look plus a link-style `<button aria-label="Dismiss notice">Dismiss</button>` at the right; it is a status (`role="status"`), not an alert.

## Dates and times

Every date the application writes is English and fixed to one locale (day first, month names from `en-US`: "5 Mar 2025", "30 Sep 2026, 08:19 EDT"), never the browser's (`lib/format.ts`, `TrendChart.tsx`); a Turkish and an English browser show the same words. Calendar dates (period, range) are shown as received, `YYYY-MM-DD`, and never converted. Only an instant (expiry) is shown in the browser's time zone. Relative text is English with whole units rounded down ("Expires in 23 hours", "Expires in 2 days").

## Helper text

A disabled primary action whose cause is the user's selection gets a `text-sm text-slate-600` line below the buttons, tied to the button with `aria-describedby`; it disappears when the action is enabled. Upload: "Select a CSV file and currency to continue."

## States

| State | Look |
|---|---|
| Loading card / chart / page (reduced motion: every animation carries `motion-reduce:animate-none`) | `animate-pulse motion-reduce:animate-none rounded bg-slate-200` blocks: `h-8 w-32` (KPI value), `h-72 w-full` (chart), a page-level block plus visible text "Loading…". Wrapper has `role="status"` and `aria-busy="true"`. Never hides the rest of the page. |
| Processing (upload) | Text "Processing…" (`text-sm text-slate-600`, `role="status"`) above a track `h-1 w-full overflow-hidden rounded bg-slate-200` holding `h-full w-1/3 animate-pulse motion-reduce:animate-none bg-indigo-700` |
| Refresh over old data | Old data stays, unchanged; add `text-sm text-slate-600` "Updating…" (`role="status"`) beside the section heading |
| Refresh after a date-range change | One "Updating…" (`role="status"`, `text-sm text-slate-600`) beside **Reset** in the Date range card, for all three sections, because Key figures has no heading |
| Empty chart / table | Inside the same box, same height (`h-72`): `flex h-72 items-center justify-center text-center text-slate-600`: "No sales in this range" / "No products sold in this range". A range with no sales also shows the warning notice "No sales in the selected range" with a secondary **Reset** |
| Success (upload or sample data ready) | `rounded-md border border-l-4 border-emerald-700 bg-emerald-50 p-3 text-sm text-emerald-900`, `role="status"`: `<span aria-hidden>✓</span>` + bold "Success" + message, link-style Dismiss at the right. Solid border like Error, so the word and icon (✓ vs ✕ vs ⚠) tell the three apart, plus Warning's dashed border |
| Section failed | Error look (above), text "Something went wrong loading this data" and a primary **Retry** |
| Full page (expired, no session) | `mx-auto max-w-md rounded-lg border border-slate-200 bg-white p-6 text-center` with an h2 message and one button or link; the h1 stays |

## Charts (Recharts)

Chart area `h-72` in a `ResponsiveContainer`, on a white card. One series colour only: bars are ranked by length, not category, so no colour per bar.

| Part | Value |
|---|---|
| Trend line and bars | `#432dd7` (`indigo-700`, 8.1:1 on white); line `strokeWidth` 2 with dots (a single bucket must show) |
| Grid lines | `#e2e8f0` (slate-200) |
| Axis lines | `#62748e` (slate-500) |
| Tick labels | `#45556c` (slate-600), font size 12 |
| Tooltip | white background, `1px solid #cad5e2` (slate-300) border, radius 6, text `#0f172b`, size 14 |

The line and bars are saturated violet-blue (8.1 on white; axis 4.8, grid 1.2) and the axes, ticks and grid are grey slate, so hue and lightness both differ. One series is safe for colour-blind readers. A second series would need a dash pattern or marker too (add a line here first).

## Accessibility (every task)

- Every control has a visible label; everything works with the keyboard alone; one `<h1>` per page, headings in order.
- Errors use `role="alert"`; loading, refresh, notices use `role="status"`; regions have `aria-label`.
- A chart has a text alternative (`role="img"` and `aria-label` naming granularity and range) and its numbers are also text (table in #30, range sentence in #29).
- Meaning is never carried by colour alone (word and icon on errors and warnings, dashed outline on disabled buttons and warnings).
