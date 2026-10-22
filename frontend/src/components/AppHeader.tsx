import LanguageSelector from "./LanguageSelector";
import type { ReactNode } from "react";

export default function AppHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-3xl font-bold text-indigo-700">Open Sales Analytics</h1>
        <LanguageSelector />
        {children && <div className="basis-full">{children}</div>}
      </div>
    </header>
  );
}
