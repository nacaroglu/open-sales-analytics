import type { ReactNode } from "react";

// The error look of the design system. The message is text, never HTML.
export default function ErrorBlock({
  message,
  children,
}: {
  message: string;
  children?: ReactNode;
}) {
  return (
    <div
      role="alert"
      className="space-y-3 rounded-md border border-l-4 border-red-700 bg-red-50 p-3 text-sm text-red-900"
    >
      <p className="wrap-anywhere">
        <span aria-hidden>✕</span> <strong>Error</strong> {message}
      </p>
      {children}
    </div>
  );
}
