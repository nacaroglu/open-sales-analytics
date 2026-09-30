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
}

function Dashboard({
  notice,
  onDismiss,
}: {
  notice: Notice | null;
  onDismiss: () => void;
}) {
  const { datasetId = "" } = useParams();
  const warnings = notice !== null && notice.id === datasetId ? notice.warnings : [];
  return <DashboardPage datasetId={datasetId} warnings={warnings} onDismissWarnings={onDismiss} />;
}

export default function App() {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<Notice | null>(null);

  function onCreated(created: Created) {
    setNotice(
      created.warnings.length > 0
        ? { id: created.dataset_id, warnings: created.warnings }
        : null,
    );
    navigate(`/d/${encodeURIComponent(created.dataset_id)}`);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <main className="mx-auto max-w-5xl px-8 py-8 space-y-8">
        <Routes>
          <Route path="/" element={<UploadPage onCreated={onCreated} />} />
          <Route
            path="/d/:datasetId"
            element={<Dashboard notice={notice} onDismiss={() => setNotice(null)} />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
