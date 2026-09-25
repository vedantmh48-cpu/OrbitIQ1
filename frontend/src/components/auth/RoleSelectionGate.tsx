/**
 * "Choose Your Path" role selection gate.
 * Presents the four SatQuery AI account types.
 */
import { Building2, FlaskConical, GraduationCap, Map } from "lucide-react";
import type { AccountType } from "../../types/auth";

export interface RoleGateOption {
  id: AccountType;
  label: string;
  description: string;
  icon: typeof GraduationCap;
  accent: string;
}

export const ROLE_OPTIONS: RoleGateOption[] = [
  {
    id: "student",
    label: "Student",
    description: "Coursework, capstone projects and academic exploration of satellite data.",
    icon: GraduationCap,
    accent: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30",
  },
  {
    id: "researcher",
    label: "Researcher",
    description: "Publish-grade analysis, reproducible pipelines and long-term study tracking.",
    icon: FlaskConical,
    accent: "text-violet-400 bg-violet-500/10 border-violet-500/30",
  },
  {
    id: "gis_analyst",
    label: "GIS Analyst",
    description: "Day-to-day geospatial work-flows, imagery layers and client deliverables.",
    icon: Map,
    accent: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  },
  {
    id: "organization",
    label: "Organization",
    description: "Teams, agencies and enterprises with admin-managed accounts and compliance controls.",
    icon: Building2,
    accent: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  },
];

export default function RoleSelectionGate({
  onSelect,
  selected,
}: {
  onSelect: (role: AccountType) => void;
  selected?: AccountType;
}) {
  return (
    <div>
      <p className="mb-5 text-sm text-slate-400">
        Choose the path that best describes how you’ll use SatQuery AI. Your
        account type shapes your workspace and security defaults.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {ROLE_OPTIONS.map(role => (
          <button
            key={role.id}
            type="button"
            onClick={() => onSelect(role.id)}
            aria-pressed={selected === role.id}
            className={`card group p-4 text-left transition hover:-translate-y-0.5 hover:border-accent/60 ${
              selected === role.id ? "!border-accent ring-1 ring-accent/30" : ""
            }`}
          >
            <div className={`flex h-11 w-11 items-center justify-center rounded-xl border ${role.accent}`}>
              <role.icon className="h-5 w-5" />
            </div>
            <div className="mt-3 font-semibold text-slate-100">{role.label}</div>
            <div className="mt-1 text-xs leading-relaxed text-slate-400">{role.description}</div>
            <div
              className={`mt-3 text-xs font-medium transition ${
                selected === role.id ? "text-accent" : "text-slate-500 group-hover:text-accent"
              }`}
            >
              {selected === role.id ? "✓ Selected" : "Choose →"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}