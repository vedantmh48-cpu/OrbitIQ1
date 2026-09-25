import Logo from "./Logo.jsx";
import { Spinner } from "./ui.jsx";

/**
 * SatQuery AI authentication shell — the application entry experience.
 *
 * The app is login-first: this shell is the first thing an unauthenticated
 * visitor sees, so it stays deliberately minimal (brand, form, links). Product
 * explanation belongs on the public SatQuery AI website, not inside the app.
 */
export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="relative flex min-h-[100dvh] flex-col overflow-x-hidden">
      {/* Deep-space atmosphere: one soft glow, essentially no visual noise. */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-accent/[0.07] blur-[130px]" />
        <div className="absolute -bottom-32 -right-24 h-72 w-72 rounded-full bg-accent-deep/[0.08] blur-3xl" />
      </div>

      <main className="relative flex flex-1 items-center justify-center px-4 py-10 sm:px-6 sm:py-14">
        <div className="w-full max-w-[26rem] animate-fade-up">
          <div className="mb-6 flex justify-center">
            <Logo size={38} />
          </div>

          <div className="card relative overflow-hidden p-6 sm:p-8">
            <div
              aria-hidden="true"
              className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent"
            />
            <header>
              <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">{title}</h1>
              {subtitle && <p className="mt-1.5 text-sm text-slate-400">{subtitle}</p>}
            </header>
            <div className="mt-6">{children}</div>
          </div>

          {footer && <div className="mt-5 text-center text-sm text-slate-400">{footer}</div>}
        </div>
      </main>
    </div>
  );
}

/**
 * Session-restore / route-boot splash. Shown while the stored session is being
 * validated so authenticated users never bounce through the login screen.
 */
export function SessionBootScreen({ label = "Restoring session…" }) {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-6 px-4">
      <Logo size={38} className="justify-center" />
      <Spinner className="h-6 w-6" label={label} />
    </div>
  );
}