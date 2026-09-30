import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <main className="mx-auto max-w-5xl px-8 py-8 space-y-8">
        {/* Navigating to the dashboard after success is #27. */}
        <UploadPage onCreated={() => {}} />
      </main>
    </div>
  );
}
