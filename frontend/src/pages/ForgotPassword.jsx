import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import AuthLayout from "../components/AuthLayout.jsx";
import { Alert, Button } from "../components/ui.jsx";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async e => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/api/auth/forgot-password", { email }, { auth: false });
      setDone(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email you a secure reset link."
      footer={<Link to="/login" className="font-semibold text-accent hover:text-accent-soft">Back to sign in</Link>}
    >
      {error && (
        <div role="alert" aria-live="polite" className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}
      {done ? (
        <div className="space-y-4" role="status">
          <Alert type="success" title="Check your inbox">{done.message}</Alert>
          {done.demo_reset_link && (
            <div className="rounded-lg border border-space-700 bg-space-850/70 p-3 text-xs">
              <div className="mb-1 font-semibold text-slate-300">Demo mode reset link (email is not configured)</div>
              <a className="break-all text-accent hover:underline" href={done.demo_reset_link}>{done.demo_reset_link}</a>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={submit} noValidate aria-busy={loading} className="space-y-4">
          <div>
            <label className="label" htmlFor="forgot-email">Email</label>
            <input
              id="forgot-email" name="email" type="email" inputMode="email" autoComplete="email" autoFocus
              className="input" placeholder="you@example.com" value={email}
              onChange={e => setEmail(e.target.value)} disabled={loading} required
            />
          </div>
          <Button type="submit" loading={loading} disabled={loading} className="w-full">Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}