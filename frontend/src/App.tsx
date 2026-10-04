import { useState } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import UploadPage from "./pages/UploadPage";
import type { Created, Issue } from "./lib/types";

// Upload warnings live in memory only: not in sessionStorage and not in the
// router state (both survive a reload), so a reload does not show them again.
interface Notice {
  id: string;
  warnings: Issue[];
  success: boolean;
}

function Dashboard({
  notice,
  onDismissWarnings,
  onDismissSuccess,
}: {
  notice: Notice | null;
  onDismissWarnings: () => void;
  onDismissSuccess: () => void;
}) {
  const { datasetId = "" } = useParams();
  const mine = notice !== null && notice.id === datasetId ? notice : null;
  return (
    <DashboardPage
      datasetId={datasetId}
      warnings={mine?.warnings ?? []}
      onDismissWarnings={onDismissWarnings}
      justCreated={mine?.success ?? false}
      onDismissSuccess={onDismissSuccess}
    />
  );
}

export default function App() {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<Notice | null>(null);

  function onCreated(created: Created) {
    setNotice({ id: created.dataset_id, warnings: created.warnings, success: true });
    navigate(`/d/${encodeURIComponent(created.dataset_id)}`);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <main className="mx-auto max-w-5xl px-8 py-8 space-y-8">
        <Routes>
          <Route path="/" element={<UploadPage onCreated={onCreated} />} />
          <Route
            path="/d/:datasetId"
            element={
              <Dashboard
                notice={notice}
                onDismissWarnings={() =>
                  setNotice((current) => (current === null ? null : { ...current, warnings: [] }))
                }
                onDismissSuccess={() =>
                  setNotice((current) => (current === null ? null : { ...current, success: false }))
                }
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
