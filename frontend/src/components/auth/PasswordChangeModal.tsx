/**
 * Password Change modal.
 *
 * Step 1 - Current + new password (current is re-verified server-side: 403 on
 *          failure, rate limited).
 * Step 2 - 6-digit OTP delivered to e-mail (purpose = password_change).
 * Step 3 - On OTP verification the backend updates `password_hash`,
 *          `password_changed_at` and revokes every other active session.
 */
import { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, X } from "lucide-react";
import * as authApi from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import { Alert, Button } from "../ui";
import OtpVerificationCard from "./OtpVerificationCard";

export interface PasswordChangeModalProps {
  open: boolean;
  onClose: () => void;
}

type Step = "form" | "otp" | "done";

export default function PasswordChangeModal({ open, onClose }: PasswordChangeModalProps) {
  const refreshUser = useAuthStore(s => s.refreshUser);
  const userEmail = useAuthStore(s => s.user?.email ?? "");
  const [step, setStep] = useState<Step>("form");
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [changeId, setChangeId] = useState("");
  const [demoCode, setDemoCode] = useState<string | undefined>(undefined);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    if (open) {
      setStep("form");
      setError("");
      setForm({ current_password: "", new_password: "", confirm_password: "" });
      setChangeId("");
      setDemoCode(undefined);
    }
  }, [open]);

  if (!open) return null;

  const submitForm = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (form.new_password.length < 8) return setError("New password must be at least 8 characters.");
    if (form.new_password !== form.confirm_password) return setError("New passwords do not match.");
    setLoading(true);
    try {
      const res = await authApi.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
        confirm_password: form.confirm_password,
      });
      setChangeId(res.password_change_id);
      setDemoCode(res.demo_code);
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the password change.");
    } finally {
      setLoading(false);
    }
  };

  const verifyOtp = async (code: string) => {
    setError("");
    setLoading(true);
    try {
      const res = await authApi.changePasswordVerify({ password_change_id: changeId, otp_code: code });
      setSuccessMessage(
        `${res.message} ${
          res.revoked_sessions > 0
            ? `(${res.revoked_sessions} other device${res.revoked_sessions === 1 ? "" : "s"} signed out).`
            : ""
        }`
      );
      setStep("done");
      refreshUser().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
      throw err;
    } finally {
      setLoading(false);
    }
  };
return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-space-950/70 px-4 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label="Change password" className="card w-full max-w-md p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-accent/40 bg-accent/10 text-accent">
              <KeyRound className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-white">Change password</h2>
              <p className="text-xs text-slate-400">
                Step {step === "form" ? "1" : step === "otp" ? "2" : "3"} of 3 · OTP verified
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-space-800 hover:text-white"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5">
          {error && (
            <div className="mb-4">
              <Alert type="error">{error}</Alert>
            </div>
          )}

          {step === "form" && (
            <form onSubmit={submitForm} className="space-y-4" noValidate>
              <div>
                <label className="label">Current password</label>
                <input
                  type="password"
                  className="input"
                  value={form.current_password}
                  onChange={e => setForm(f => ({ ...f, current_password: e.target.value }))}
                  required
                  autoComplete="current-password"
                />
              </div>
              <div>
                <label className="label">New password</label>
                <input
                  type="password"
                  className="input"
                  placeholder="Min 8 characters"
                  value={form.new_password}
                  onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
                  required
                  autoComplete="new-password"
                />
              </div>
              <div>
                <label className="label">Confirm new password</label>
                <input
                  type="password"
                  className="input"
                  value={form.confirm_password}
                  onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))}
                  required
                  autoComplete="new-password"
                />
              </div>
              <p className="rounded-lg border border-space-700 bg-space-850/60 px-3 py-2 text-xs text-slate-400">
                After OTP verification we’ll sign out every other device except this one.
              </p>
              <Button type="submit" loading={loading} className="w-full">
                Send verification code
              </Button>
            </form>
          )}

          {step === "otp" && (
            <OtpVerificationCard
              email={userEmail}
              purpose="password_change"
              demoCode={demoCode}
              onVerify={verifyOtp}
              onCancel={() => setStep("form")}
            />
          )}

          {step === "done" && (
            <div className="text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400">
                <CheckCircle2 className="h-7 w-7" />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-white">Password updated</h3>
              <p className="mt-1 text-sm text-slate-400">{successMessage}</p>
              <Button className="mt-6 w-full" onClick={onClose}>
                Done
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}