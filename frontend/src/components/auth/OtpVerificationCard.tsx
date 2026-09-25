/**
 * 6-digit OTP e-mail verification card.
 * Used right after registration and when a not-yet-verified account attempts
 * to sign in. In demo mode a server-provided code can be auto-filled.
 */
import { useEffect, useRef, useState } from "react";
import { MailCheck, RotateCw } from "lucide-react";
import { Alert, Button } from "../ui";

export interface OtpVerificationCardProps {
  email: string;
  purpose?: "register" | "password_change";
  demoCode?: string;
  resendCooldownSeconds?: number;
  onVerify: (code: string) => Promise<void>;
  onResend?: () => Promise<string | undefined>;
  onCancel?: () => void;
  message?: string;
}

const DIGITS = 6;

export default function OtpVerificationCard({
  email,
  demoCode,
  resendCooldownSeconds = 30,
  onVerify,
  onResend,
  onCancel,
  message,
}: OtpVerificationCardProps) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (demoCode) setCode(demoCode);
  }, [demoCode]);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  const startCooldown = () => {
    setCooldown(resendCooldownSeconds);
    timerRef.current = window.setInterval(() => {
      setCooldown(c => {
        if (c <= 1 && timerRef.current) window.clearInterval(timerRef.current);
        return Math.max(0, c - 1);
      });
    }, 1000);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!/^\d{6}$/.test(code)) return setError("Enter the 6-digit verification code.");
    setLoading(true);
    try {
      await onVerify(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    if (!onResend || cooldown > 0 || loading) return;
    setError("");
    try {
      const next = await onResend();
      if (next) setCode(next);
      startCooldown();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend the code.");
    }
  };

  return (
    <div className="text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/40 bg-accent/10 text-accent">
        <MailCheck className="h-6 w-6" />
      </span>
      <h3 className="mt-4 text-lg font-semibold text-white">Verify your email</h3>
      <p className="mx-auto mt-1 max-w-sm text-sm text-slate-400">
        We sent a 6-digit code to <span className="font-medium text-slate-200">{email}</span>.
        {message ? ` ${message}` : ""}
      </p>

      {error && (
        <div role="alert" aria-live="polite" className="mt-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      <form onSubmit={submit} className="mt-5" noValidate>
        <div className="flex justify-center gap-2">
          {Array.from({ length: DIGITS }).map((_, i) => {
            const digit = code[i] ?? "";
            return (
              <input
                key={i}
                inputMode="numeric"
                maxLength={1}
                aria-label={`Verification code digit ${i + 1} of ${DIGITS}`}
                autoComplete={i === 0 ? "one-time-code" : "off"}
                className="h-12 w-10 rounded-lg border border-space-600 bg-space-850/80 text-center text-lg font-semibold text-white outline-none transition focus:border-accent"
                value={digit}
                onChange={e => {
                  const v = e.target.value.replace(/\D/g, "");
                  const next = code.slice(0, i) + v + code.slice(i + 1);
                  setCode(next.slice(0, DIGITS));
                  if (v) {
                    const el = document.querySelector<HTMLInputElement>(
                      `input[maxlength="1"]:nth-of-type(${i + 2})`
                    );
                    el?.focus();
                  }
                }}
                onKeyDown={e => {
                  if (e.key === "Backspace" && !digit) {
                    const el = document.querySelector<HTMLInputElement>(
                      `input[maxlength="1"]:nth-of-type(${i})`
                    );
                    el?.focus();
                  }
                }}
                onPaste={e => {
                  const text = e.clipboardData.getData("text").replace(/\D/g, "");
                  if (text) {
                    e.preventDefault();
                    setCode(text.slice(0, DIGITS));
                  }
                }}
              />
            );
          })}
        </div>
        <Button type="submit" loading={loading} className="mt-5 w-full">
          Verify & continue
        </Button>
      </form>

      {(onResend || onCancel) && (
        <div className="mt-4 flex items-center justify-center gap-4 text-sm">
          {onResend && (
            <button
              type="button"
              disabled={cooldown > 0 || loading}
              onClick={resend}
              className="inline-flex items-center gap-1.5 font-medium text-accent transition hover:text-accent-soft disabled:cursor-not-allowed disabled:text-slate-500"
            >
              <RotateCw className="h-3.5 w-3.5" />
              {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
            </button>
          )}
          {onCancel && (
            <button type="button" onClick={onCancel} className="font-medium text-slate-400 transition hover:text-slate-200">
              Use a different email
            </button>
          )}
        </div>
      )}
    </div>
  );
}