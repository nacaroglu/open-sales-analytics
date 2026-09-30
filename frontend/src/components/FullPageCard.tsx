import type { ReactNode } from "react";

// The full-page card of the design system (expired, no session). The h1 stays
// outside it, on the page.
export default function FullPageCard({
  title,
  sentence,
  children,
}: {
  title: string;
  sentence: string;
  children: ReactNode;
}) {
  return (
    <div
      role="alert"
      className="mx-auto max-w-md space-y-4 rounded-lg border border-slate-200 bg-white p-6 text-center"
    >
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <p className="text-sm text-slate-600">{sentence}</p>
      {children}
    </div>
  );
}
