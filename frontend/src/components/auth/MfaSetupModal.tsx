/**
 * MFA (TOTP) setup modal.
 *
 * Works in two modes:
 *  - "settings": enrol TOTP from the Security Settings page.
 *  - "login": mandatory first-time enrolment for government/defense orgs;
 *    once enabled the pending login attempt is completed automatically.
 */
import { useEffect, useState } from "react";
import { Copy, KeyRound, ShieldCheck, X } from "lucide-react";
import * as authApi from "../../api/auth";
import { useAuthStore } from "../../store/authStore";
import type { User } from "../../types/auth";
import { Alert, Button } from "../ui";

export interface MfaSetupModalProps {
  open: boolean;
  mode?: "settings" | "login";
  mfaToken?: string;
  onClose?: () => void;
  onCompleted?: (user: User) => void;
}

export default function MfaSetupModal({
  open,
  mode = "settings",
  mfaToken,
  onClose,
  onCompleted,
}: MfaSetupModalProps) {
  const completeMfa = useAuthStore(s => s.completeMfa);
  const [secret, setSecret] = useState("");
  const [otpauthUrl, setOtpauthUrl] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSecret("");
    setOtpauthUrl("");
    setCode("");
    setError("");
    setDone(false);
    authApi
      .mfaSetup()
      .then(res => {
        setSecret(res.secret);
        setOtpauthUrl(res.otpauth_url);
      })
      .catch(err => setError(err instanceof Error ? err.message : "Could not start MFA setup."));
  }, [open]);

  if (!open) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!/^\d{6}$/.test(code)) return setError("Enter a 6-digit authenticator code.");
    setLoading(true);
    try {
      await authApi.mfaVerify({ code });
      if (mode === "login" && mfaToken) {
        const user = await completeMfa(mfaToken, code);
        onCompleted?.(user);
      } else {
        setDone(true);
        onCompleted?.(useAuthStore.getState().user as User);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const closable = mode === "settings";
return (
    <div className="fixed inset-0 z-[75] flex items-center justify-center bg-space-950/70 px-4 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label="Set up two-factor authentication" className="card w-full max-w-md p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400">
              <KeyRound className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-white">Two-factor authentication</h2>
              <p className="text-xs text-slate-400">
                {mode === "login" ? "Required for your organization tier" : "Enrol a TOTP app"}
              </p>
            </div>
          </div>
          {closable && !loading && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-space-800 hover:text-white"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        <div className="mt-5">
          {error && (
            <div className="mb-4">
              <Alert type="error">{error}</Alert>
            </div>
          )}

          {done ? (
            <div className="text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-400">
                <ShieldCheck className="h-7 w-7" />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-white">Two-factor enabled</h3>
              <p className="mt-1 text-sm text-slate-400">
                Your account now requires an authenticator code to sign in.
              </p>
              {closable && (
                <Button className="mt-6 w-full" onClick={onClose}>
                  Done
                </Button>
              )}
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4" noValidate>
              <div>
                <p className="text-sm text-slate-400">
                  Scan the QR code with your authenticator app, or enter the secret manually.
                </p>
                <div className="mt-3 rounded-xl border border-space-700 bg-space-850/60 p-4">
                  <div className="text-xs font-medium uppercase tracking-wider text-slate-500">
                    Setup key (Base32)
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <code className="break-all font-mono text-sm text-accent">{secret || "…"}</code>
                    <button
                      type="button"
                      onClick={copy}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-space-600 text-slate-400 transition hover:text-accent"
                      aria-label="Copy secret"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                  </div>
                  {otpauthUrl && (
                    <a
                      href={otpauthUrl}
                      className="mt-2 inline-block text-xs text-slate-500 underline underline-offset-2 hover:text-accent"
                    >
                      Open in authenticator
                    </a>
                  )}
                  {copied && <div className="mt-1 text-xs text-emerald-400">Copied!</div>}
                </div>
              </div>
              <div>
                <label className="label">6-digit authenticator code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  className="input text-center text-lg font-semibold tracking-[0.3em]"
                  value={code}
                  onChange={e => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="••••••"
                  required
                />
              </div>
              <Button type="submit" loading={loading} className="w-full">
                Enable two-factor authentication
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}