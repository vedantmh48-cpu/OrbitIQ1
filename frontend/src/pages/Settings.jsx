import { useEffect, useState } from "react";
import { User, KeyRound, Palette, Map as MapIcon, Bell, Code2, Trash2, MonitorSmartphone, ShieldCheck, Timer } from "lucide-react";
import { api } from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import { useTheme } from "../context/ThemeContext.jsx";
import * as authApi from "../api/auth";
import { computeIdleConfig, useAuthStore } from "../store/authStore";
import { Alert, Button, Card, Toggle } from "../components/ui.jsx";
import PasswordChangeModal from "../components/auth/PasswordChangeModal";
import ActiveSessionsCard from "../components/auth/ActiveSessionsCard";
import MfaSetupModal from "../components/auth/MfaSetupModal";

const TABS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "password", label: "Password & security", icon: KeyRound },
  { id: "mfa", label: "Two-factor", icon: ShieldCheck },
  { id: "sessions", label: "Sessions & devices", icon: MonitorSmartphone },
  { id: "theme", label: "Appearance", icon: Palette },
  { id: "map", label: "Map preferences", icon: MapIcon },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "api", label: "API configuration", icon: Code2 },
  { id: "danger", label: "Account", icon: Trash2 }
];

export default function Settings() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  const [tab, setTab] = useState("profile");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const flash = (ok, m) => {
    if (ok) setMsg(m); else setErr(m);
    setTimeout(() => { setMsg(""); setErr(""); }, 4000);
  };

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <p className="mt-1 text-sm text-slate-400">Manage your profile, security and platform preferences.</p>
      {msg && <div className="mt-4"><Alert type="success">{msg}</Alert></div>}
      {err && <div className="mt-4"><Alert type="error">{err}</Alert></div>}
      <div className="mt-6 grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${
                tab === t.id ? "bg-accent/10 text-accent" : "text-slate-400 hover:bg-space-800 hover:text-slate-200"
              }`}
            >
              <t.icon className="h-4 w-4" /> {t.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0">
          {tab === "profile" && <ProfileTab user={user} flash={flash} />}
          {tab === "password" && <PasswordTab flash={flash} user={user} />}
          {tab === "mfa" && <MfaTab flash={flash} user={user} />}
          {tab === "sessions" && <ActiveSessionsCard />}
          {tab === "theme" && <ThemeTab theme={theme} setTheme={setTheme} flash={flash} />}
          {tab === "map" && <MapTab flash={flash} />}
          {tab === "notifications" && <NotificationsTab flash={flash} />}
          {tab === "api" && <ApiTab />}
          {tab === "danger" && <DangerTab flash={flash} />}
        </div>
      </div>
    </div>
  );
}

function ProfileTab({ user, flash }) {
  const [form, setForm] = useState({ name: user?.name || "", email: user?.email || "" });
  const [saving, setSaving] = useState(false);
  const submit = async e => {
    e.preventDefault();
    setSaving(true);
    try { await api.put("/api/users/me", form); flash(true, "Profile updated."); }
    catch (e2) { flash(false, e2.message); }
    finally { setSaving(false); }
  };
  return (
    <Card>
      <h2 className="text-lg font-semibold text-white">Profile</h2>
      <form onSubmit={submit} className="mt-4 space-y-4">
        <div>
          <label className="label">Full name</label>
          <input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <div>
          <label className="label">Email</label>
          <input type="email" className="input" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        </div>
        <div>
          <label className="label">Role</label>
          <input className="input capitalize" value={user?.role || "user"} disabled />
        </div>
        <Button type="submit" loading={saving}>Save changes</Button>
      </form>
    </Card>
  );
}

function PasswordTab({ flash, user }) {
  const [modalOpen, setModalOpen] = useState(false);
  const refreshUser = useAuthStore(s => s.refreshUser);
  const config = computeIdleConfig(user);
  const [timeoutValue, setTimeoutValue] = useState(config.timeoutMinutes);
  const [savingTimeout, setSavingTimeout] = useState(false);

  const saveTimeout = async () => {
    setSavingTimeout(true);
    try {
      const res = await authApi.setInactivityTimeout(timeoutValue);
      setTimeoutValue(res.inactivity_timeout_minutes);
      await refreshUser();
      flash(true, `Auto-logout set to ${res.inactivity_timeout_minutes} minutes of inactivity.`);
    } catch (e2) { flash(false, e2.message); }
    finally { setSavingTimeout(false); }
  };

  return (
    <>
      <Card>
        <h2 className="text-lg font-semibold text-white">Password & security</h2>
        <p className="mt-1 text-sm text-slate-400">
          Changing your password re-verifies your identity with an e-mailed code
          and signs out every other device.
        </p>
        <div className="mt-5">
          <Button onClick={() => setModalOpen(true)}>
            <KeyRound className="mr-2 h-4 w-4" /> Change password
          </Button>
        </div>
      </Card>

      <div className="mt-4">
        <Card>
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-accent/40 bg-accent/10 text-accent">
              <Timer className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="text-base font-semibold text-white">Auto-logout after inactivity</h3>
              <p className="mt-1 text-sm text-slate-400">
                {config.governmentTier
                  ? "Your organization tier is clamped to a 15-minute maximum. A “Never” option is not available."
                  : "You’ll be signed out automatically after the selected idle period."}
                {" "}You’ll get a warning 60 seconds before.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <select
                  className="input w-44"
                  value={timeoutValue}
                  onChange={e => setTimeoutValue(Number(e.target.value))}
                >
                  {config.selectableOptions.map(min => (
                    <option key={min} value={min}>{min} minute{min === 1 ? "" : "s"}</option>
                  ))}
                </select>
                <Button loading={savingTimeout} onClick={saveTimeout}>Save</Button>
              </div>
              {config.governmentTier && (
                <p className="mt-2 text-xs text-amber-400">
                  ⚠ Government / Defense policy: maximum {config.maxTimeoutMinutes} minutes, minimum option {Math.min(...config.selectableOptions)} minutes.
                </p>
              )}
            </div>
          </div>
        </Card>
      </div>

      <PasswordChangeModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
function MfaTab({ flash, user }) {
  const [setupOpen, setSetupOpen] = useState(false);
  const [disableCode, setDisableCode] = useState("");
  const [busy, setBusy] = useState(false);
  const mfaEnabled = !!user?.mfa_enabled;
  const mfaRequired = !!user?.mfa_required;
  const refreshUser = useAuthStore(s => s.refreshUser);

  const disable = async e => {
    e.preventDefault();
    setBusy(true);
    try {
      await authApi.mfaDisable({ code: disableCode });
      setDisableCode("");
      await refreshUser();
      flash(true, "Two-factor authentication disabled.");
    } catch (e2) { flash(false, e2.message); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Card>
        <div className="flex items-center gap-3">
          <span className={`flex h-11 w-11 items-center justify-center rounded-xl border ${
            mfaEnabled ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400" : "border-space-700 bg-space-800/60 text-slate-400"
          }`}>
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-white">Two-factor authentication</h2>
            <p className="mt-0.5 text-sm text-slate-400">
              {mfaEnabled ? "Enabled — sign-ins require an authenticator code." : "Not enabled."}
              {mfaRequired && (
                <span className="ml-2 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">
                  Required for your tier
                </span>
              )}
            </p>
          </div>
        </div>

        {!mfaEnabled ? (
          <div className="mt-5">
            <Button onClick={() => setSetupOpen(true)}>
              <ShieldCheck className="mr-2 h-4 w-4" /> Set up two-factor authentication
            </Button>
          </div>
        ) : (
          <form onSubmit={disable} className="mt-5 space-y-3">
            <p className="text-sm text-slate-400">
              Enter your current authenticator code to disable two-factor authentication.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="label">Authenticator code</label>
                <input
                  type="text" inputMode="numeric" maxLength={6}
                  className="input w-44 text-center tracking-[0.3em]"
                  value={disableCode}
                  onChange={e => setDisableCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="••••••" required
                />
              </div>
              <Button type="submit" variant="danger" loading={busy}>Disable MFA</Button>
            </div>
          </form>
        )}
      </Card>

      <MfaSetupModal
        open={setupOpen}
        mode="settings"
        onClose={() => setSetupOpen(false)}
        onCompleted={() => {
          refreshUser().catch(() => undefined);
          flash(true, "Two-factor authentication enabled.");
        }}
      />
    </>
  );
}

function ThemeTab({ theme, setTheme, flash }) {
  return (
    <Card>
      <h2 className="text-lg font-semibold text-white">Appearance</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {["dark", "light"].map(t => (
          <button key={t} onClick={async () => { await setTheme(t); flash(true, "Theme changed."); }}
            className={`card p-4 text-left transition hover:border-accent/60 ${theme === t ? "!border-accent" : ""}`}>
            <div className="font-semibold text-slate-100 capitalize">{t} mode</div>
            <div className="mt-1 text-xs text-slate-500">{t === "dark" ? "Space-inspired geospatial dark" : "Clean light interface"}</div>
          </button>
        ))}
      </div>
    </Card>
  );
}

function MapTab({ flash }) {
  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-lg font-semibold text-white">Map preferences</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="label">Default base layer</label>
            <select className="input" defaultValue="dark">
              <option value="dark">Dark basemap</option>
              <option value="satellite">Satellite basemap</option>
              <option value="streets">Streets basemap</option>
            </select>
          </div>
          <div>
            <label className="label">Show query AOI boundary</label>
            <select className="input" defaultValue="yes">
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <AssignButton label="Save map settings" flash={flash} payload={{ map_preferences: { base_layer: "dark" } }} />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-white">Default data source</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="label">Default satellite source</label>
            <select className="input" defaultValue="demo">
              <option value="demo">Demo (simulated)</option>
              <option value="sentinel">Sentinel (Copernicus)</option>
              <option value="landsat">Landsat (USGS)</option>
              <option value="stac">STAC Earth Search</option>
            </select>
          </div>
          <AssignButton label="Save defaults" flash={flash} payload={{ default_satellite_source: "demo", default_data_type: "any" }} />
        </div>
      </Card>
    </div>
  );
}

function AssignButton({ label, flash, payload }) {
  const [saving, setSaving] = useState(false);
  const click = async () => {
    setSaving(true);
    try { await api.put("/api/users/settings", payload); flash(true, "Preferences saved."); }
    catch (e2) { flash(false, e2.message); }
    finally { setSaving(false); }
  };
  return <Button onClick={click} loading={saving}>{label}</Button>;
}

function NotificationsTab({ flash }) {
  const [prefs, setPrefs] = useState({ email_summary: true, job_updates: true, weekly_digest: false });
  const save = async () => {
    try { await api.put("/api/users/settings", { notifications: prefs }); flash(true, "Notification preferences saved."); }
    catch (e2) { flash(false, e2.message); }
  };
  const rows = [
    ["email_summary", "Email summary after each analysis"],
    ["job_updates", "Live job-progress notifications"],
    ["weekly_digest", "Weekly digest of saved analyses"]
  ];
  return (
    <Card>
      <h2 className="text-lg font-semibold text-white">Notifications</h2>
      <div className="mt-4 space-y-3">
        {rows.map(([k, label]) => (
          <label key={k} className="flex items-center gap-3 text-sm text-slate-300">
            <input type="checkbox" className="h-4 w-4 accent-cyan-500" checked={prefs[k]}
              onChange={e => setPrefs(p => ({ ...p, [k]: e.target.checked }))} />
            {label}
          </label>
        ))}
      </div>
      <div className="mt-4"><Button onClick={save}>Save preferences</Button></div>
    </Card>
  );
}

function ApiTab() {
  return (
    <Card>
      <h2 className="text-lg font-semibold text-white">API configuration</h2>
      <p className="mt-2 text-sm text-slate-400">
        SatQuery AI ships with a demo catalogue needing no keys. To enable real
        provider data, set credentials in the backend&apos;s <code className="text-accent">.env</code> and restart the API.
      </p>
      <div className="mt-4 rounded-lg border border-space-700 bg-space-850/60 p-4 font-mono text-xs text-slate-300">
        SENTINEL_CLIENT_ID=…<br />SENTINEL_CLIENT_SECRET=…<br />LANDSAT_API_KEY=…<br />DEMO_MODE=auto
      </div>
    </Card>
  );
}

function DangerTab({ flash }) {
  return (
    <Card>
      <h2 className="text-lg font-semibold text-rose-400">Delete account</h2>
      <p className="mt-2 text-sm text-slate-400">
        Permanently removes your queries, results, saved analyses and sessions. This cannot be undone.
      </p>
      <button
        className="btn mt-4 border border-rose-500/50 text-rose-400 hover:bg-rose-500/10"
        onClick={() => {
          if (window.confirm("Really delete your account? This cannot be undone.")) {
            api.del("/api/users/me").then(() => { window.location.href = "/"; })
              .catch(e2 => flash(false, e2.message));
          }
        }}
      >
        <Trash2 className="h-4 w-4" /> Delete my account
      </button>
    </Card>
  );
}