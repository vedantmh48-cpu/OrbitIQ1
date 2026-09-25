#!/usr/bin/env python3
"""SatQuery AI / SatQuery AI - single-command developer launcher.

    python run.py

Starts BOTH the FastAPI backend and the Vite frontend together and stops them
both on Ctrl+C:

    Backend API   -> http://localhost:8000   (Swagger docs at /docs)
    Frontend app  -> http://localhost:5173   (proxies /api and /ws to 8000)

Every section of the app - Dashboard, Weather Forecast, Calamity Prediction,
Results, History, Datasets, GeoTools, Saved and Settings - is reachable from
this one command.

Usage:
    python run.py                 start backend + frontend
    python run.py --backend-only  start only the API server
    python run.py --port 8001     change the backend port
    python run.py --reload        auto-restart the backend on code changes
    python run.py --reuse         keep/reuse existing servers on the ports
                                  (default: previous python/node dev instances
                                  on ports 8000/5173 are stopped first so the
                                  freshly started servers always run the
                                  current code)
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    print(f"[satquery] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[satquery] ! {message}", flush=True)


def error(message: str) -> None:
    print(f"\n[satquery] ERROR: {message}", flush=True)


def port_busy(port: int) -> bool:
    """True when something is already listening on ``port``.

    Probes IPv4 and IPv6 loopback because services (e.g. Vite) may bind to
    either family.
    """
    for host in ("127.0.0.1", "::1"):
        try:
            sock = socket.socket(
                socket.AF_INET6 if ":" in host else socket.AF_INET,
                socket.SOCK_STREAM,
            )
        except OSError:
            continue
        with sock:
            sock.settimeout(0.6)
            if sock.connect_ex((host, port)) == 0:
                return True
    return False


def find_listener_pids(port: int) -> list[int]:
    """Return OS PIDs currently LISTENING on ``port`` (best effort)."""
    pids: set[int] = set()
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=20
            ).stdout or ""
            for line in out.splitlines():
                cols = line.split()
                if len(cols) < 5 or cols[0] not in ("TCP", "UDP"):
                    continue
                if not cols[1].endswith(f":{port}"):
                    continue
                if "LISTENING" in line:
                    try:
                        pids.add(int(cols[4]))
                    except ValueError:
                        pass
        else:
            for probe in (
                ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                ["fuser", f"{port}/tcp"],
            ):
                try:
                    out = subprocess.run(
                        probe, capture_output=True, text=True, timeout=10
                    )
                    if out.returncode == 0:
                        for tok in (out.stdout or "").split():
                            try:
                                pids.add(int(tok))
                            except ValueError:
                                pass
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return sorted(pids)


def process_basename(pid: int) -> str:
    """Best-effort process image name for a PID ('' when unknown)."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15,
            ).stdout or ""
            for line in out.splitlines():
                parts = line.split('","')
                if len(parts) >= 2:
                    return parts[0].strip('"').lower()
        else:
            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True, text=True, timeout=10,
            ).stdout or ""
            return out.strip().lower()
    except Exception:
        pass
    return ""


def stop_pids(pids: list[int]) -> None:
    """Force-terminate the given process tree(s), best effort."""
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True, text=True, timeout=15,
                )
            elif hasattr(os, "kill"):
                os.kill(pid, getattr(os, "SIGKILL", 15))
        except Exception:
            pass


def http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for(url: str, name: str, seconds: float = 90.0) -> bool:
    log(f"waiting for {name} at {url} ...")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if http_ok(url):
            log(f"{name} is up at {url}")
            return True
        time.sleep(0.6)
    return False


def find_python() -> str | None:
    """Return an interpreter that can import the backend app.

    Prefers the project venv (``.venv``) so ``python run.py`` works even when
    the system Python has no dependencies installed.
    """
    candidates: list[str] = []
    venv = ROOT / ".venv"
    if os.name == "nt":
        venv_py = venv / "Scripts" / "python.exe"
    else:
        venv_py = venv / "bin" / "python"
    candidates.append(str(venv_py) if venv_py.exists() else None)
    candidates.append(sys.executable)

    probe = "import fastapi, uvicorn, httpx; import app.main"
    for py in dict.fromkeys(c for c in candidates if c):
        try:
            result = subprocess.run(
                [py, "-c", probe],
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                timeout=90,
            )
            if result.returncode == 0:
                return py
        except Exception:
            continue
    return None


def npm_command() -> str | None:
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def stop_process(proc: subprocess.Popen) -> None:
    """Best-effort terminate then kill; works on Windows and POSIX."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    backend_only = "--backend-only" in argv or "--no-frontend" in argv
    reload_backend = "--reload" in argv or "reload" in argv
    backend_port = _arg_port(argv, "--port", os.getenv("PORT"), DEFAULT_BACKEND_PORT)
    frontend_port = _arg_port(argv, "--frontend-port", os.getenv("FRONTEND_PORT"), DEFAULT_FRONTEND_PORT)

    # ---- 0. Fresh-start previous dev instances -----------------------------
    # A server left over from an earlier session would otherwise be *reused*
    # by the port checks below and serve stale code (for example a backend
    # started before new routes were added). Stop previous python/node dev
    # instances on the target ports unless --reuse is passed.
    if "--reuse" not in argv:
        for port, allowed in (
            (backend_port, {"python", "python.exe"}),
            (frontend_port, {"node", "node.exe"}),
        ):
            if backend_only and port == frontend_port:
                continue
            listeners = [
                p for p in find_listener_pids(port) if process_basename(p) in allowed
            ]
            if listeners:
                log(f"stopping previous dev instance(s) on port {port}: {listeners}")
                stop_pids(listeners)
        time.sleep(0.8)

    # ---- 1. Python interpreter that can actually run the backend ----------
    python = find_python()
    if python is None:
        error(
            "Could not find a Python environment with the backend dependencies.\n"
            "  Setup:  cd backend && python -m venv .venv && "
            ".venv\\Scripts\\pip install -r requirements.txt\n"
            "  (or:   .venv/bin/pip install -r requirements.txt  on macOS/Linux)"
        )
        return 1
    log(f"using python: {python}")

    # ---- 2. Backend process ----------------------------------------------
    backend_proc: subprocess.Popen | None = None
    backend_url = f"http://127.0.0.1:{backend_port}"
    if port_busy(backend_port):
        if http_ok(f"{backend_url}/api/health", timeout=2.0):
            warn(f"Backend already running on port {backend_port} - reusing it.")
        else:
            error(f"Port {backend_port} is in use by another program. "
                  "Stop it, or pick a free port with --port 8001.")
            return 1
    if backend_proc is None and not port_busy(backend_port):
        cmd = [python, str(BACKEND_DIR / "run.py")]
        if reload_backend:
            cmd.append("--reload")
        log(f"starting backend: {' '.join(cmd)}")
        backend_proc = subprocess.Popen(
            cmd, cwd=str(BACKEND_DIR), stdout=None, stderr=None
        )

    # ---- 3. Frontend process (skipped in --backend-only mode) -------------
    frontend_proc: subprocess.Popen | None = None
    # ``localhost`` (not 127.0.0.1): Vite may bind only to the IPv6 loopback.
    frontend_url = f"http://localhost:{frontend_port}"
    if not backend_only:
        if not FRONTEND_DIR.exists():
            warn(f"Frontend folder not found ({FRONTEND_DIR}) - frontend skipped.")
        elif not (FRONTEND_DIR / "node_modules").exists():
            npm = npm_command()
            if npm is None:
                warn("Node.js/npm not found - skipping the frontend. "
                     "Install Node.js, then run `cd frontend && npm install && npm run dev`.")
            else:
                log("frontend dependencies missing - running `npm install` (first run only)")
                install = subprocess.run(
                    [npm, "install"], cwd=str(FRONTEND_DIR)
                )
                if install.returncode != 0:
                    warn("`npm install` failed - frontend will not start. Check your network.")
        if port_busy(frontend_port) and not frontend_proc:
            if http_ok(frontend_url, timeout=2.0):
                warn(f"Frontend already running on port {frontend_port} - reusing it.")
            else:
                error(f"Port {frontend_port} is in use by another program. "
                      f"Stop it, or pick a free port with --frontend-port 5174.")
                _shutdown(backend_proc, frontend_proc)
                return 1
        npm = npm_command()
        if npm and not port_busy(frontend_port):
            log(f"starting frontend: {npm} run dev -- --port {frontend_port} --strictPort")
            frontend_proc = subprocess.Popen(
                [npm, "run", "dev", "--", "--port", str(frontend_port), "--strictPort"],
                cwd=str(FRONTEND_DIR),
                stdout=None,
                stderr=None,
            )
        elif npm is None:
            warn("frontend skipped (npm not found); API + Swagger still available.")

    # ---- 4. Health checks -------------------------------------------------
    ok_backend = wait_for(f"{backend_url}/api/health", "backend API")
    ok_frontend = backend_only or (
        frontend_proc is not None and wait_for(frontend_url, "frontend")
    )

    if not ok_backend:
        error("The backend did not become healthy. See the traceback above.")
        _shutdown(backend_proc, frontend_proc)
        return 1
    if not backend_only and not ok_frontend and frontend_proc is not None:
        warn("The frontend took too long to start - it may still be compiling; "
             "refresh http://localhost:%d manually." % frontend_port)

    # ---- 5. Banner --------------------------------------------------------
    print("\n" + "=" * 64)
    print("  SatQuery AI / SatQuery AI - running")
    print("=" * 64)
    print(f"  Frontend app   -> http://localhost:{frontend_port}")
    print(f"  Backend API    -> http://localhost:{backend_port}   (Swagger: /docs)")
    if not backend_only:
        print("  Demo accounts  -> admin@satquery.ai / Admin@123   demo@satquery.ai / Demo@123")
    print("  Stop           -> press Ctrl+C\n")
    if os.name != "nt" and not backend_only:
        try:
            import webbrowser

            webbrowser.open_new_tab(frontend_url)
        except Exception:
            pass

    # ---- 6. Run until interrupted ----------------------------------------
    try:
        while True:
            if backend_proc is not None and backend_proc.poll() is not None:
                error(f"Backend exited unexpectedly (code {backend_proc.returncode}).")
                _shutdown(backend_proc, frontend_proc)
                return backend_proc.returncode if backend_proc.returncode else 1
            if frontend_proc is not None and frontend_proc.poll() is not None:
                if http_ok(frontend_url, timeout=2.0):
                    warn(f"Frontend process stopped, but an app is already answering "
                         f"on port {frontend_port} - reusing it.")
                else:
                    warn(f"Frontend exited unexpectedly (code {frontend_proc.returncode}).")
                frontend_proc = None
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()  # keep the console tidy
        log("stopping services ...")
    finally:
        _shutdown(backend_proc, frontend_proc)
    return 0


def _arg_port(argv: list[str], flag: str, env_value: str | None, default: int) -> int:
    if flag in argv:
        try:
            index = argv.index(flag)
            return int(argv[index + 1])
        except (IndexError, ValueError):
            pass
    try:
        return int(env_value) if env_value else default
    except (TypeError, ValueError):
        return default


def _shutdown(backend_proc: subprocess.Popen | None, frontend_proc: subprocess.Popen | None) -> None:
    for proc in (backend_proc, frontend_proc):
        if proc is not None:
            stop_process(proc)
    log("done.")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))