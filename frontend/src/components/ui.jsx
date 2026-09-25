export function Spinner({ className = "h-5 w-5", label = "" }) {
  return (
    <span className="inline-flex items-center gap-2">
      <svg className={`animate-spin text-accent ${className}`} viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
        <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {label && <span className="text-sm text-slate-400">{label}</span>}
    </span>
  );
}

export function Button({ children, loading, variant = "primary", className = "", ...props }) {
  const styles =
    variant === "primary"
      ? "btn-primary"
      : variant === "ghost"
      ? "btn-ghost"
      : variant === "danger"
      ? "btn-danger"
      : "btn border border-space-600 text-slate-300 hover:text-accent hover:border-accent";
  return (
    <button className={`${styles} ${className}`} disabled={loading || props.disabled} {...props}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Skeleton({ className = "", lines = 1 }) {
  if (lines <= 1) return <div className={`skeleton ${className}`} />;
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-4" />
      ))}
    </div>
  );
}

export function Card({ children, className = "", hover = false }) {
  return <div className={`card p-5 ${hover ? "transition hover:border-accent/50 hover:-translate-y-0.5" : ""} ${className}`}>{children}</div>;
}

export function StatCard({ label, value, sub, icon, accent = "text-accent", className = "" }) {
  return (
    <div className={`card p-4 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</span>
        {icon && (
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 ${accent}`}>
            {icon}
          </span>
        )}
      </div>
      <div className="mt-1.5 text-2xl font-bold text-white">{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function EmptyState({ icon, title, message, action, className = "" }) {
  return (
    <div className={`card flex flex-col items-center justify-center px-6 py-14 text-center ${className}`}>
      {icon && (
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-space-700 bg-accent/5 text-slate-500">
          {icon}
        </div>
      )}
      <h3 className="text-base font-semibold text-slate-200">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Badge({ children, color = "accent" }) {
  const map = {
    accent: "border-accent/40 text-accent bg-accent/10",
    green: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
    amber: "border-amber-500/40 text-amber-400 bg-amber-500/10",
    red: "border-rose-500/40 text-rose-400 bg-rose-500/10",
    slate: "border-space-600 text-slate-400 bg-space-800/60"
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${map[color] || map.accent}`}>
      {children}
    </span>
  );
}

export function SimulatedBadge({ simulated = true }) {
  if (!simulated) return <Badge color="green">Real catalogue</Badge>;
  return <Badge color="amber">⚠ Demo / simulated</Badge>;
}

export function Alert({ type = "error", title, children }) {
  const styles = {
    error: "border-rose-500/40 bg-rose-500/10 text-rose-300",
    warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    info: "border-accent/40 bg-accent/10 text-accent-soft",
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
  };
  const icons = { error: "✕", warn: "!", info: "ⓘ", success: "✓" };
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${styles[type]}`}>
      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-xs font-bold">{icons[type]}</span>
      <div className="min-w-0">
        {title && <div className="mb-0.5 font-semibold">{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function SectionTitle({ icon, children, className = "" }) {
  return (
    <div className={`mb-3 flex items-center gap-2 text-sm font-semibold text-accent ${className}`}>
      {icon}
      <span>{children}</span>
    </div>
  );
}

export function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-300">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${
          checked ? "bg-accent-deep" : "bg-space-700"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
            checked ? "left-[22px]" : "left-0.5"
          }`}
        />
      </button>
      {label && <span>{label}</span>}
    </label>
  );
}