import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  FileSearch, History, Database, FolderHeart, Settings, BookOpen,
  LogOut, Menu, X, LayoutDashboard, Moon, Sun, Plus, ChevronLeft, Boxes,
  CloudSun, ShieldAlert, GitCompareArrows
} from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { useTheme } from "../context/ThemeContext.jsx";
import Logo from "./Logo.jsx";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, hint: "Ask and run analyses" },
  { to: "/weather", label: "Weather Forecast", icon: CloudSun, hint: "Real-time 7-day forecast" },
  { to: "/predictions", label: "Calamity Prediction", icon: ShieldAlert, hint: "Natural hazard risk engine" },
  { to: "/results", label: "Results", icon: FileSearch, hint: "Your analyses" },
  { to: "/history", label: "History", icon: History, hint: "Past queries" },
  { to: "/datasets", label: "Datasets", icon: Database, hint: "Catalogue & live feeds" },
  { to: "/geotools", label: "GeoTools", icon: Boxes, hint: "Spectral indices & GeoTIFF parsing" },
  { to: "/change-analysis", label: "Change Analysis", icon: GitCompareArrows, hint: "Date 1 vs Date 2 satellite comparison" },
  { to: "/saved", label: "Saved analyses", icon: FolderHeart, hint: "Pinned reports" },
  { to: "/howto", label: "How to Use", icon: BookOpen, hint: "Docs & workflows" },
  { to: "/settings", label: "Settings", icon: Settings, hint: "Preferences & security" }
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const ref = useRef(null);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const initials = (user?.name || "?").split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
  const current = NAV.find(n => location.pathname.startsWith(n.to));

  return (
    <div className="flex h-dvh overflow-hidden" ref={ref}>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/70 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r bg-space-900/95 backdrop-blur-xl transition-all duration-300 lg:static lg:translate-x-0 ${
          mobileOpen
            ? "translate-x-0"
            : collapsed
            ? "-translate-x-full lg:translate-x-0 lg:w-20"
            : "-translate-x-full lg:translate-x-0 lg:w-[248px]"
        } ${theme === "light" ? "!border-slate-300" : "border-space-700"}`}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b px-4">
          {collapsed && !mobileOpen ? (
            <div className="mx-auto py-3"><Logo size={30} withText={false} /></div>
          ) : (
            <Logo size={30} />
          )}
          <button className="rounded p-1 text-slate-400 hover:text-accent lg:hidden" onClick={() => setMobileOpen(false)}>
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="px-3 pt-3">
          <button
            onClick={() => navigate("/dashboard")}
            className="btn-primary w-full !justify-start !py-2.5 text-sm"
          >
            <Plus className="h-4 w-4" /> {collapsed && !mobileOpen ? "" : "New analysis"}
          </button>
        </div>

        <nav className="mt-2 flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.map(item => (
            <SidebarLink
              key={item.to}
              item={item}
              active={location.pathname.startsWith(item.to)}
              collapsed={collapsed && !mobileOpen}
            />
          ))}
        </nav>
{/* user card */}
        <div className="border-t p-3">
          <div className={`flex items-center gap-2.5 rounded-xl p-1.5 ${collapsed && !mobileOpen ? "justify-center" : ""}`}>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-deep text-xs font-bold text-space-950 shadow-lg shadow-accent/25">
              {initials}
            </div>
            {(!collapsed || mobileOpen) && (
              <>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-200">{user?.name}</div>
                  <div className="truncate text-[11px] capitalize text-slate-500">{user?.role || "analyst"}</div>
                </div>
                <button
                  onClick={logout}
                  className="rounded-lg p-2 text-slate-500 transition hover:bg-space-800 hover:text-rose-400"
                  title="Sign out"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b bg-space-900/70 px-3 backdrop-blur-xl sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <button className="rounded-lg p-2 text-slate-400 hover:bg-space-800 hover:text-accent lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu className="h-5 w-5" />
            </button>
            <button
              className="hidden rounded-lg p-2 text-slate-500 transition hover:bg-space-800 hover:text-accent lg:inline-flex"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setCollapsed(c => !c)}
            >
              <ChevronLeft className={`h-5 w-5 transition-transform ${collapsed ? "rotate-180" : ""}`} />
            </button>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-200">{current?.label || "OrbitIQ"}</div>
              <div className="hidden truncate text-[11px] text-slate-500 sm:block">{current?.hint || "Satellite intelligence platform"}</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-space-800 hover:text-accent"
              title="Toggle theme"
            >
              {theme === "dark"
                ? <Sun style={{ width: 18, height: 18 }} />
                : <Moon style={{ width: 18, height: 18 }} />}
            </button>
            <span className="hidden items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent sm:flex">
              <span className="h-1.5 w-1.5 animate-pulse-glow rounded-full bg-accent" />
              Demo data active
            </span>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-deep text-xs font-bold text-space-950">
              {initials}
            </div>
          </div>
        </header>

        <main className="relative flex-1 overflow-y-auto p-3 sm:p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

function SidebarLink({ item, active, collapsed }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      className={`nav-pill flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
        active ? "active" : "text-slate-400 hover:bg-space-800 hover:text-slate-200"
      } ${collapsed ? "justify-center !px-2" : ""}`}
      title={item.label}
    >
      <Icon className="h-5 w-5 shrink-0" />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </NavLink>
  );
}