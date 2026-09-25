import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout.jsx";
import RoleSelectionGate from "../components/auth/RoleSelectionGate";
import RegistrationForm from "../components/auth/RegistrationForms";
import OtpVerificationCard from "../components/auth/OtpVerificationCard";
import { useAuthStore } from "../store/authStore";
import { Alert } from "../components/ui.jsx";

export default function Register() {
  const navigate = useNavigate();
  const register = useAuthStore(s => s.register);
  const resendVerification = useAuthStore(s => s.resendVerification);
  const verifyEmail = useAuthStore(s => s.verifyEmail);
  const loading = useAuthStore(s => s.loading);

  const [role, setRole] = useState(null);
  const [step, setStep] = useState("gate"); // gate | form | otp
  const [email, setEmail] = useState("");
  const [demoCode, setDemoCode] = useState(undefined);
  const [error, setError] = useState("");

  const submit = async payload => {
    setError("");
    try {
      const res = await register(payload);
      setEmail(res.user.email);
      setDemoCode(res.demoCode);
      setStep("otp");
    } catch (err) {
      setError(err.message);
    }
  };

  const handleVerify = async code => {
    await verifyEmail(email, code);
    navigate("/dashboard", { replace: true });
  };

  const handleResend = async () => {
    try {
      const next = await resendVerification(email);
      if (next) setDemoCode(next);
      return next;
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <AuthLayout
      title={step === "gate" ? "Create your account" : step === "form" ? "Your details" : "Verify your email"}
      subtitle={
        step === "gate"
          ? "Choose the path that fits how you work with satellite data."
          : step === "form"
          ? "Tell us a little more about you."
          : "One last step before you can sign in."
      }
      footer={
        step === "otp" ? null : (
          <>
            Already have an account?{" "}
            <Link to="/login" className="font-semibold text-accent hover:text-accent-soft">Sign in</Link>
          </>
        )
      }
    >
      {error && (
        <div className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      {step === "gate" && (
        <RoleSelectionGate
          selected={role ?? undefined}
          onSelect={r => {
            setError("");
            setRole(r);
            setStep("form");
          }}
        />
      )}

      {step === "form" && role && (
        <RegistrationForm
          role={role}
          loading={loading}
          error={error}
          onSubmit={submit}
          onBack={() => setStep("gate")}
        />
      )}

      {step === "otp" && (
        <OtpVerificationCard
          email={email}
          demoCode={demoCode}
          onVerify={handleVerify}
          onResend={handleResend}
        />
      )}
    </AuthLayout>
  );
}