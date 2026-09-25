import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client.js";
import AuthLayout from "../components/AuthLayout.jsx";
import { Alert, Button } from "../components/ui.jsx";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [form, setForm] = useState({ new_password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const submit = async e => {
    e.preventDefault();
    setError("");
    if (form.new_password.length < 8) return setError("Password must be at least 8 characters.");
    if (form.new_password !== form.confirm_password) return setError("Passwords do not match.");
    setLoading(true);
    try {
      await api.post("/api/auth/reset-password", { token, ...form }, { auth: false });
      setDone(true);
      setTimeout(() => navigate("/login"), 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Set a new password"
      subtitle="Choose a strong, unique password."
      footer={<Link to="/login" className="font-semibold text-accent hover:text-accent-soft">Back to sign in</Link>}
    >
      {!token && (
        <div role="alert" aria-live="polite" className="mb-4">
          <Alert type="error">Missing or invalid reset token.</Alert>
        </div>
      )}
      {done ? (
        <div role="status">
          <Alert type="success" title="Password updated">You can now sign in with your new password.</Alert>
        </div>
      ) : (
        <form onSubmit={submit} noValidate aria-busy={loading} className="space-y-4">
          {error && (
            <div role="alert" aria-live="polite">
              <Alert type="error">{error}</Alert>
            </div>
          )}
          <div>
            <label className="label" htmlFor="reset-password">New password</label>
            <input
              id="reset-password" name="new_password" type="password" autoComplete="new-password"
              className="input" placeholder="Min 8 characters"
              value={form.new_password}
              onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
              disabled={loading} required
            />
          </div>
          <div>
            <label className="label" htmlFor="reset-confirm">Confirm new password</label>
            <input
              id="reset-confirm" name="confirm_password" type="password" autoComplete="new-password"
              className="input" placeholder="Repeat password"
              value={form.confirm_password}
              onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))}
              disabled={loading} required
            />
          </div>
          <Button type="submit" loading={loading} className="w-full" disabled={!token || loading}>Update password</Button>
        </form>
      )}
    </AuthLayout>
  );
}