import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FolderHeart, ExternalLink, Trash2, ChevronRight } from "lucide-react";
import { api, formatPct } from "../api/client.js";
import { Alert, Badge, EmptyState, SimulatedBadge } from "../components/ui.jsx";
import DataModal from "../components/DataModal.jsx";

export default function Saved() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [quick, setQuick] = useState(null);

  const load = async () => {
    try {
      setItems(await api.get("/api/saved"));
    } catch (e) {
      setError(e.message);
      setItems([]);
    }
  };

  useEffect(() => { load(); }, []);

  const remove = async id => {
    try {
      await api.del(`/api/saved/${id}`);
      setItems(items => (items || []).filter(i => i.id !== id));
    } catch (e) {
      setError(e.message);
    }
  };

  const openQuick = async item => {
    try {
      const res = await api.get(`/api/results/${item.result_id}`);
      setQuick({
        name: item.name || item.result_label || "Saved analysis",
        description: item.notes || `${res.label} — ${formatPct(res.confidence)} confidence`,
        result_id: item.result_id,
        ...res
      });
    } catch (e) {
      setError(e.message);
    }
  };

  if (!items) return <div className="animate-pulse space-y-3"><div className="h-16 rounded-xl bg-space-800/60" /></div>;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Saved analyses</h1>
        <p className="mt-1 text-sm text-slate-400">Pin valuable analyses to revisit them any time. Click a card for the full result summary.</p>
      </div>
      {error && <Alert type="error">{error}</Alert>}
      {items.length === 0 ? (
        <EmptyState
          icon={<FolderHeart className="h-10 w-10" />}
          title="Nothing saved yet"
          message="Open any analysis and press “Save analysis” to keep it here."
          action={<Link to="/results" className="btn-primary">Browse your results</Link>}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map(s => (
            <div key={s.id} className="card group p-4 transition hover:border-accent/50">
              <div className="flex items-start justify-between gap-2">
                <button
                  onClick={() => openQuick(s)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="truncate font-semibold text-slate-100 group-hover:text-accent-soft">
                    {s.name || s.result_label || "Analysis"}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    {s.result_label && <Badge color="slate">{s.result_label}</Badge>}
                    {formatPct(s.confidence)} confidence
                  </div>
                  {s.notes && <p className="mt-2 text-sm text-slate-400">{s.notes}</p>}
                </button>
                <div className="flex gap-1 shrink-0">
                  {s.result_id && (
                    <Link to={`/results/${s.result_id}`} className="rounded p-1.5 text-slate-400 hover:text-accent" title="Open full result">
                      <ExternalLink className="h-4 w-4" />
                    </Link>
                  )}
                  <button onClick={() => remove(s.id)} className="rounded p-1.5 text-slate-500 hover:text-rose-400" title="Remove">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between">
                {s.simulated ? <SimulatedBadge simulated /> : <Badge color="green">Live</Badge>}
                <span className="flex items-center gap-1 text-xs text-slate-600 transition group-hover:text-accent">
                  Details <ChevronRight className="h-3 w-3" />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {quick && (
        <DataModal kind="quickview" data={quick} onClose={() => setQuick(null)} />
      )}
    </div>
  );
}