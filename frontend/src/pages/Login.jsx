import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthStepRequired } from "../api/auth";
import AuthLayout from "../components/AuthLayout.jsx";
import OtpVerificationCard from "../components/auth/OtpVerificationCard";
import MfaSetupModal from "../components/auth/MfaSetupModal";
import { useAuthStore } from "../store/authStore";
import { Alert, Button } from "../components/ui.jsx";

// Kept intentionally permissive: the backend remains the authority on whether
// an address exists — this only catches obvious typos before a network round-trip.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/dashboard";
  const login = useAuthStore(s => s.login);
  const completeMfa = useAuthStore(s => s.completeMfa);
  const resendVerification = useAuthStore(s => s.resendVerification);
  const loading = useAuthStore(s => s.loading);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("form"); // form | verify_email | mfa
  const [mfaToken, setMfaToken] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [setupMfaOpen, setSetupMfaOpen] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [mfaFieldError, setMfaFieldError] = useState("");
  const [verifyDemo, setVerifyDemo] = useState(undefined);

  const clearFieldError = field =>
    setFieldErrors(prev => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });

  const validateCredentials = () => {
    const problems = {};
    if (!email.trim()) problems.email = "Enter your email address.";
    else if (!EMAIL_RE.test(email.trim())) problems.email = "Enter a valid email address.";
    if (!password) problems.password = "Enter your password.";
    return problems;
  };

  const submit = async e => {
    e.preventDefault();
    if (loading) return; // ignore double submits while a request is in flight
    setError("");
    const problems = validateCredentials();
    setFieldErrors(problems);
    if (Object.keys(problems).length) return;
    try {
      await login({ email: email.trim(), password });
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof AuthStepRequired) {
        const res = err.body;
        if (res && res.mfa_setup_required) {
          setError("");
          setSetupMfaOpen(true);
          return;
        }
        if (res && res.mfa_required) {
          setMfaToken(res.mfa_token);
          setMode("mfa");
          return;
        }
      }
      if (err.code === "EMAIL_NOT_VERIFIED") {
        setMode("verify_email");
        setError("");
        return;
      }
      setError(err.message);
    }
  };

  const submitMfa = async e => {
    e.preventDefault();
    if (loading) return; // ignore double submits while a request is in flight
    setError("");
    setMfaFieldError("");
    if (!/^\d{6}$/.test(mfaCode)) return setMfaFieldError("Enter the 6-digit code from your authenticator app.");
    try {
      await completeMfa(mfaToken, mfaCode);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleVerify = async code => {
    await verifyEmailFromVerification(code);
  };

  // Verification of an existing account (pre-registration flow): the code
  // verifies the account and the backend issues a fresh session.
  const verifyEmailFromVerification = async code => {
    const state = useAuthStore.getState();
    await state.verifyEmail(email, code);
    navigate(from, { replace: true });
  };

  const handleResend = async () => {
    try {
      const next = await resendVerification(email);
      if (next) setVerifyDemo(next);
      return next;
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <AuthLayout
      title={
        mode === "form" ? "Welcome back" : mode === "verify_email" ? "Verify your email" : "Two-factor authentication"
      }
      subtitle={
        mode === "form"
          ? "Access your SatQuery AI workspace."
          : mode === "verify_email"
          ? "Enter the 6-digit code we sent to your inbox."
          : "Enter the code from your authenticator app."
      }
    >
      {error && (
        <div id="login-error" role="alert" aria-live="polite" className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      {mode === "form" && (
        <>
          <form onSubmit={submit} noValidate aria-busy={loading} className="space-y-4">
            <div>
              <label className="label" htmlFor="login-email">Email</label>
              <input
                id="login-email" name="email" type="email" inputMode="email" autoComplete="email" autoFocus
                className="input" placeholder="you@example.com" value={email}
                onChange={e => { setEmail(e.target.value); clearFieldError("email"); }}
                aria-invalid={fieldErrors.email ? true : undefined}
                aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
                disabled={loading} required
              />
              {fieldErrors.email && (
                <p id="login-email-error" className="mt-1.5 text-xs text-rose-400">{fieldErrors.email}</p>
              )}
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between gap-3">
                <label className="label !mb-0" htmlFor="login-password">Password</label>
                <Link to="/forgot-password" className="text-xs font-medium text-accent hover:text-accent-soft">
                  Forgot password?
                </Link>
              </div>
              <input
                id="login-password" name="password" type="password" autoComplete="current-password"
                className="input" placeholder="••••••••" value={password}
                onChange={e => { setPassword(e.target.value); clearFieldError("password"); }}
                aria-invalid={fieldErrors.password ? true : undefined}
                aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
                disabled={loading} required
              />
              {fieldErrors.password && (
                <p id="login-password-error" className="mt-1.5 text-xs text-rose-400">{fieldErrors.password}</p>
              )}
            </div>

            <Button type="submit" loading={loading} disabled={loading} className="w-full">Sign in</Button>
          </form>

          {/* Secondary action: account creation lives inside the auth card so the
              entry screen offers exactly two clearly separated choices. */}
          <section aria-labelledby="create-account-heading" className="mt-6 border-t border-space-700/60 pt-5 text-center">
            <h2
              id="create-account-heading"
              className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
            >
              New to SatQuery AI?
            </h2>
            <Link to="/register" className="btn-ghost mt-3 w-full">Create account</Link>
          </section>
        </>
      )}

      {mode === "verify_email" && (
        <OtpVerificationCard
          email={email}
          demoCode={verifyDemo}
          onVerify={handleVerify}
          onResend={handleResend}
          onCancel={() => setMode("form")}
        />
      )}

      {mode === "mfa" && (
        <>
          <form onSubmit={submitMfa} noValidate aria-busy={loading} className="space-y-4">
            <div>
              <label className="label" htmlFor="login-mfa">Authenticator code</label>
              <input
                id="login-mfa" name="one-time-code" type="text" inputMode="numeric" pattern="[0-9]*"
                maxLength={6} autoComplete="one-time-code" autoFocus
                className="input text-center text-lg font-semibold tracking-[0.3em]"
                value={mfaCode}
                onChange={e => { setMfaCode(e.target.value.replace(/\D/g, "")); setMfaFieldError(""); }}
                aria-invalid={mfaFieldError ? true : undefined}
                aria-describedby={mfaFieldError ? "login-mfa-error" : undefined}
                placeholder="••••••" disabled={loading} required
              />
              {mfaFieldError && (
                <p id="login-mfa-error" className="mt-1.5 text-xs text-rose-400">{mfaFieldError}</p>
              )}
            </div>
            <Button type="submit" loading={loading} disabled={loading} className="w-full">Verify & sign in</Button>
          </form>

          <div className="mt-6 border-t border-space-700/60 pt-4 text-center">
            <button
              type="button"
              onClick={() => { setMfaFieldError(""); setError(""); setMode("form"); }}
              className="text-xs font-medium text-slate-400 transition hover:text-accent"
            >
              Back to sign in
            </button>
          </div>
        </>
      )}

      <MfaSetupModal
        open={setupMfaOpen}
        mode="login"
        mfaToken={useAuthStore.getState().mfaStep?.mfaToken}
        onCompleted={() => navigate(from, { replace: true })}
      />
    </AuthLayout>
  );
}