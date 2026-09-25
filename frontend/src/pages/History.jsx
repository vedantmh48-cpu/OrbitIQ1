import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { History as HistoryIcon, ChevronRight, Clock } from "lucide-react";
import { api } from "../api/client.js";
import { Alert, Badge, EmptyState } from "../components/ui.jsx";

export default function History() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setItems(await api.get("/api/queries/history?limit=100"));
      } catch (e) {
        setError(e.message);
        setItems([]);
      }
    })();
  }, []);

  if (!items) return <div className="mx-auto max-w-5xl space-y-4"><SkeletonRow /></div>;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Query history</h1>
        <p className="mt-1 text-sm text-slate-400">Your past natural-language queries and their status.</p>
      </div>
      {error && <Alert type="error">{error}</Alert>}
      {items.length === 0 ? (
        <EmptyState
          icon={<HistoryIcon className="h-10 w-10" />}
          title="No queries yet"
          message="Ask your first question on the dashboard — it will be recorded here."
          action={<Link to="/dashboard" className="btn-primary">Ask a question</Link>}
        />
      ) : (
        <div className="space-y-2">
          {items.map(q => (
            <Link
              key={q.id}
              to={`/results/${q.result_id || ""}`}
              className="card group flex items-center justify-between gap-3 p-4 transition hover:border-accent/50"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-100">{q.text}</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                  <Clock className="h-3 w-3" />
                  {q.created_at?.replace("T", " ").slice(0, 16)}
                  {q.agent && <Badge color="slate">{q.agent}</Badge>}
                  {q.model && <span className="hidden sm:inline">{q.model.split(" ")[0]}</span>}
                </div>
              </div>
              <span className="chip text-xs">
                {q.status === "completed" ? "completed" : q.status} <ChevronRight className="h-3 w-3" />
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <>{[1, 2, 3].map(i => (
      <div key={i} className="h-16 animate-pulse rounded-xl bg-space-800/60" />
    ))}</>
  );
}