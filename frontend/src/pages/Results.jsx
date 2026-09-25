import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileSearch, Trash2, ExternalLink, Clock, ChevronRight, FileText } from "lucide-react";
import { api, formatPct, prettyOp, timeAgo } from "../api/client.js";
import { Alert, Badge, EmptyState, SimulatedBadge, Skeleton } from "../components/ui.jsx";

export default function Results() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setItems(await api.get("/api/results?limit=50"));
    } catch (e) {
      setError(e.message);
      setItems([]);
    }
  };

  useEffect(() => { load(); }, []);

  const remove = async id => {
    try {
      await api.del(`/api/results/${id}`);
      setItems(items => (items || []).filter(i => i.id !== id));
    } catch (e) {
      setError(e.message);
    }
  };

  if (!items) return <ResultListSkeleton />;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="animate-fade-up">
        <div className="section-kicker">Your analyses</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">Results</h1>
        <p className="mt-1 text-sm text-slate-400">Every satellite analysis you've run, newest first.</p>
      </div>
      {error && <Alert type="error">{error}</Alert>}
      {items.length === 0 ? (
        <EmptyState
          icon={<FileSearch className="h-10 w-10" />}
          title="No analyses yet"
          message="Run a natural-language query on the dashboard and your satellite results will appear here."
          action={<Link to="/dashboard" className="btn-primary">Run your first query</Link>}
        />
      ) : (
        <div className="stagger space-y-3">
          {items.map(item => (
            <div key={item.id} className="card group flex flex-wrap items-center justify-between gap-3 p-4 transition hover:border-accent/50">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-100">{item.label || "Analysis"}</span>
                  <Badge color="slate">{prettyOp(item.op)}</Badge>
                  <SimulatedBadge simulated={item.simulated} />
                  {item.google_doc_url && (
                    <a href={item.google_doc_url} target="_blank" rel="noreferrer" title="Google Doc" className="chip !cursor-pointer !border-accent/40 !text-accent hover:!bg-accent/10">
                      <FileText className="h-3 w-3" /> G-Docs
                    </a>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {timeAgo(item.created_at)}</span>
                  <span>{formatPct(item.confidence)} confidence</span>
                  <span className="hidden sm:inline">{item.id.slice(0, 8)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link to={`/results/${item.id}`} className="btn-ghost !py-2 text-xs" title="Open result">
                  <ExternalLink className="h-4 w-4" /> Open <ChevronRight className="h-4 w-4" />
                </Link>
                <button
                  onClick={() => remove(item.id)}
                  className="rounded-lg p-2 text-slate-500 transition hover:bg-rose-500/10 hover:text-rose-400"
                  title="Delete"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ResultListSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="space-y-3">
        {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 rounded-2xl" />)}
      </div>
    </div>
  );
}