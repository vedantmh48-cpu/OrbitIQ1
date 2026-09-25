/**
 * Role-specific registration forms for the four OrbitIQ account types.
 */
import { useMemo, useState } from "react";
import { ChevronLeft } from "lucide-react";
import type { AccountType, OrgType, RegistrationPayload } from "../../types/auth";
import { Alert, Button } from "../ui";
import { ROLE_OPTIONS } from "./RoleSelectionGate";

export interface RegistrationFormProps {
  role: AccountType;
  loading?: boolean;
  error?: string;
  onSubmit: (payload: RegistrationPayload) => void;
  onBack: () => void;
}

interface FieldDef {
  name: string;
  label: string;
  type: "text" | "email" | "password" | "number";
  placeholder?: string;
  required?: boolean;
  min?: number;
  max?: number;
  hint?: string;
}

const FIELD_DEFS: Record<AccountType, FieldDef[]> = {
  student: [
    { name: "full_name", label: "Full name", type: "text", placeholder: "Ada Lovelace", required: true },
    { name: "email", label: "Email", type: "email", placeholder: "you@university.edu", required: true },
    { name: "institution", label: "Institution / College", type: "text", placeholder: "Geospatial University", required: true },
    { name: "course", label: "Course", type: "text", placeholder: "B.Sc. Remote Sensing", required: true },
    { name: "year_of_study", label: "Year of study", type: "number", min: 1, max: 10, required: true },
    { name: "password", label: "Password", type: "password", placeholder: "Min 8 characters", required: true },
    { name: "confirm_password", label: "Confirm password", type: "password", placeholder: "Repeat password", required: true },
  ],
  researcher: [
    { name: "full_name", label: "Full name", type: "text", placeholder: "Dr. Ada Grace", required: true },
    { name: "email", label: "Email", type: "email", placeholder: "you@institution.org", required: true },
    { name: "institution", label: "Institution", type: "text", placeholder: "National Geospatial Lab", required: true },
    { name: "research_field", label: "Research field", type: "text", placeholder: "Land-cover change detection", required: true },
    { name: "orcid", label: "ORCID ID (optional)", type: "text", placeholder: "0000-0002-0000-0000" },
    { name: "profile_link", label: "Profile link (optional)", type: "text", placeholder: "https://scholar.example/alice" },
    { name: "password", label: "Password", type: "password", placeholder: "Min 8 characters", required: true },
    { name: "confirm_password", label: "Confirm password", type: "password", placeholder: "Repeat password", required: true },
  ],
  gis_analyst: [
    { name: "full_name", label: "Full name", type: "text", placeholder: "Grace Hopper", required: true },
    { name: "email", label: "Email", type: "email", placeholder: "you@employer.com", required: true },
    { name: "employer", label: "Employer", type: "text", placeholder: "Terra Mapping Co.", required: true },
    { name: "job_title", label: "Job title", type: "text", placeholder: "Senior GIS Analyst", required: true },
    { name: "years_experience", label: "Years of experience", type: "number", min: 0, max: 80, required: true },
    { name: "primary_tools", label: "Primary GIS tools", type: "text", placeholder: "QGIS, ArcGIS Pro, GDAL, Leaflet", required: true },
    { name: "password", label: "Password", type: "password", placeholder: "Min 8 characters", required: true },
    { name: "confirm_password", label: "Confirm password", type: "password", placeholder: "Repeat password", required: true },
  ],
  organization: [
    { name: "org_name", label: "Organization name", type: "text", placeholder: "State Mapping Agency", required: true },
    {
      name: "org_type",
      label: "Organization type",
      type: "text",
      required: true,
      hint: "Government/Defense enrollments enforce MFA and a 15-minute inactivity cap.",
    },
    { name: "official_domain", label: "Official domain", type: "text", placeholder: "agency.gov", required: true },
    { name: "admin_name", label: "Admin name", type: "text", placeholder: "Full name of the account admin", required: true },
    { name: "admin_email", label: "Admin email", type: "email", placeholder: "admin@agency.gov", required: true },
    { name: "team_size", label: "Team size", type: "number", min: 1, max: 1000000, required: true },
    { name: "intended_use", label: "Intended use", type: "text", placeholder: "Describe your agency's use cases", required: true },
    { name: "password", label: "Password", type: "password", placeholder: "Min 8 characters", required: true },
    { name: "confirm_password", label: "Confirm password", type: "password", placeholder: "Repeat password", required: true },
  ],
};
/** Browser autofill hints, keyed by field name. */
const AUTOCOMPLETE: Record<string, string> = {
  full_name: "name",
  admin_name: "name",
  email: "email",
  admin_email: "email",
  password: "new-password",
  confirm_password: "new-password",
};

export default function RegistrationForm({
  role,
  loading,
  error,
  onSubmit,
  onBack,
}: RegistrationFormProps) {
  const defs = useMemo(() => FIELD_DEFS[role], [role]);
  const [form, setForm] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of defs) init[f.name] = "";
    if (role === "organization") init.org_type = "private";
    return init;
  });
  const [localError, setLocalError] = useState("");

  const set = (name: string) => (value: string) =>
    setForm(f => ({ ...f, [name]: value }));

  const buildPayload = (): RegistrationPayload | null => {
    const base = {
      password: form.password,
      confirm_password: form.confirm_password,
    };
    if (role === "student") {
      return {
        ...base,
        account_type: "student",
        full_name: form.full_name,
        email: form.email,
        institution: form.institution,
        course: form.course,
        year_of_study: Number(form.year_of_study),
      };
    }
    if (role === "researcher") {
      return {
        ...base,
        account_type: "researcher",
        full_name: form.full_name,
        email: form.email,
        institution: form.institution,
        research_field: form.research_field,
        orcid: form.orcid || undefined,
        profile_link: form.profile_link || undefined,
      };
    }
    if (role === "gis_analyst") {
      return {
        ...base,
        account_type: "gis_analyst",
        full_name: form.full_name,
        email: form.email,
        employer: form.employer,
        job_title: form.job_title,
        years_experience: Number(form.years_experience),
        primary_tools: form.primary_tools,
      };
    }
    return {
      ...base,
      account_type: "organization",
      org_name: form.org_name,
      org_type: form.org_type as OrgType,
      official_domain: form.official_domain,
      admin_name: form.admin_name,
      admin_email: form.admin_email,
      team_size: Number(form.team_size),
      intended_use: form.intended_use,
    };
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError("");
    if (form.password.length < 8) return setLocalError("Password must be at least 8 characters.");
    if (form.password !== form.confirm_password) return setLocalError("Passwords do not match.");
    const payload = buildPayload();
    if (!payload) return setLocalError("Something went wrong building your request.");
    onSubmit(payload);
  };

  const roleMeta = ROLE_OPTIONS.find(r => r.id === role);

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition hover:text-accent"
      >
        <ChevronLeft className="h-4 w-4" /> Choose another path
      </button>
      <div className="mb-5 flex items-center gap-3">
        <span className={`flex h-10 w-10 items-center justify-center rounded-xl border ${roleMeta?.accent ?? ""}`}>
          {roleMeta && <roleMeta.icon className="h-5 w-5" />}
        </span>
        <div>
          <div className="font-semibold text-slate-100">{roleMeta?.label}</div>
          <div className="text-xs text-slate-400">
            {role === "organization"
              ? "Government / Defense accounts enforce MFA + a 15 min inactivity cap."
              : "Create your account profile."}
          </div>
        </div>
      </div>

      {(error || localError) && (
        <div role="alert" aria-live="polite" className="mb-4">
          <Alert type="error">{localError || error}</Alert>
        </div>
      )}

      <form onSubmit={submit} className="space-y-4" noValidate aria-busy={loading}>
        {defs.map(field => {
          const fieldId = `reg-${field.name}`;
          const hintId = field.hint ? `${fieldId}-hint` : undefined;
          const passwordInvalid = field.type === "password" && localError ? true : undefined;
          if (role === "organization" && field.name === "org_type") {
            return (
              <div key={field.name}>
                <label className="label" htmlFor={fieldId}>{field.label}</label>
                <select
                  id={fieldId}
                  name={field.name}
                  className="input"
                  value={form.org_type}
                  onChange={e => set("org_type")(e.target.value)}
                  aria-describedby={hintId}
                  disabled={loading}
                >
                  <option value="government">Government</option>
                  <option value="defense">Defense</option>
                  <option value="private">Private</option>
                </select>
                {field.hint && <p id={hintId} className="mt-1 text-xs text-slate-500">{field.hint}</p>}
              </div>
            );
          }
          return (
            <div key={field.name}>
              <label className="label" htmlFor={fieldId}>{field.label}</label>
              <input
                id={fieldId}
                name={field.name}
                type={field.type}
                className="input"
                placeholder={field.placeholder}
                value={form[field.name] ?? ""}
                onChange={e => set(field.name)(e.target.value)}
                autoComplete={AUTOCOMPLETE[field.name]}
                aria-invalid={passwordInvalid}
                aria-describedby={hintId}
                min={field.min}
                max={field.max}
                disabled={loading}
                required={field.required}
              />
              {field.hint && <p id={hintId} className="mt-1 text-xs text-slate-500">{field.hint}</p>}
            </div>
          );
        })}
        <Button type="submit" loading={loading} disabled={loading} className="w-full">
          Create account
        </Button>
      </form>
    </div>
  );
}