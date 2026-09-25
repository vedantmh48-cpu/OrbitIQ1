"""Auth store layer for the v1 auth vertical slice.

Two interchangeable backends behind one interface:

* **PostgreSQL (PostGIS)** via ``psycopg`` when reachable - the canonical
  production store with real ``users`` / ``sessions`` / ``email_verifications``
  tables.
* The **legacy document store** (MongoDB / local JSON) as a fully functional
  fallback so the app runs out-of-the-box without Postgres installed.

Selection is driven by ``settings.AUTH_STORE`` (``auto`` | ``postgres`` |
``compat``) and mirrors the project's auto-detect storage philosophy.
"""
from __future__ import annotations

import threading
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Union

from .config import settings
from .storage import datetime_now, get_db, new_id

# ---------------------------------------------------------------------------
# Account / organization constants
# ---------------------------------------------------------------------------

ACCOUNT_STUDENT = "student"
ACCOUNT_RESEARCHER = "researcher"
ACCOUNT_GIS_ANALYST = "gis_analyst"
ACCOUNT_ORGANIZATION = "organization"
ACCOUNT_TYPES = (
    ACCOUNT_STUDENT,
    ACCOUNT_RESEARCHER,
    ACCOUNT_GIS_ANALYST,
    ACCOUNT_ORGANIZATION,
)

GOV_ORG_TYPES = ("government", "defense")
ORG_TYPES = ("government", "defense", "private")

# Inactivity options exposed in the UI (minutes). Government/Defense tiers
# are clamped by the backend so a "Never" option is never available to them.
INACTIVITY_OPTIONS = (5, 15, 30, 60)


def is_gov(account_type: str, org_type: str | None = None) -> bool:
    return (
        account_type == ACCOUNT_ORGANIZATION
        and (org_type or "").strip().lower() in GOV_ORG_TYPES
    )


def inactivity_options_for(account_type: str, org_type: str | None = None) -> list[int]:
    opts = list(INACTIVITY_OPTIONS)
    if is_gov(account_type, org_type):
        cap = settings.GOV_MAX_INACTIVITY_TIMEOUT_MINUTES
        opts = [o for o in opts if o <= cap]
    return opts or [5]


def clamp_inactivity_minutes(account_type: str, minutes: int, org_type: str | None = None) -> int:
    opts = inactivity_options_for(account_type, org_type)
    best = min(opts)
    for o in opts:
        if abs(o - minutes) < abs(best - minutes):
            best = o
    return best


AuthStoreLike = Union["CompatAuthStore", "PostgresAuthStore"]


# ---------------------------------------------------------------------------
# User record helpers
# ---------------------------------------------------------------------------


def normalize_user(raw: dict | None) -> dict | None:
    """Coerce a stored user record (any backend) into a canonical dict."""
    if not raw:
        return None
    user = dict(raw)
    user["id"] = user.get("id") or user.get("user_id") or user.get("_id")
    if not user.get("id"):
        return None
    user["password_hash"] = user.get("password_hash") or user.get("password", "")
    user["account_type"] = user.get("account_type", ACCOUNT_STUDENT)
    user["role"] = user.get("role", "user")
    user.setdefault("org_type", None)
    user.setdefault("active", True)
    user.setdefault("email_verified", False)
    user.setdefault("mfa_enabled", False)
    user.setdefault("mfa_required", False)
    user.setdefault("mfa_secret", None)
    if user["mfa_required"] and is_gov(user["account_type"], user.get("org_type")):
        pass  # mfa_required forced for gov/defense at registration
    raw_timeout = user.get("inactivity_timeout_minutes")
    try:
        timeout = int(raw_timeout) if raw_timeout not in (None, "", 0) else settings.DEFAULT_INACTIVITY_TIMEOUT_MINUTES
    except (TypeError, ValueError):
        timeout = settings.DEFAULT_INACTIVITY_TIMEOUT_MINUTES
    user["inactivity_timeout_minutes"] = clamp_inactivity_minutes(
        user["account_type"], timeout, user.get("org_type")
    )
    if not user.get("profile"):
        user["profile"] = {}
    if not user.get("settings"):
        user["settings"] = {}
    user.setdefault("password_changed_at", None)
    return user


def user_public(user: dict) -> dict:
    """Safe user payload returned to the client."""
    profile = user.get("profile") or {}
    public_profile = dict(profile)
    # Never leak MFA/OTP secrets.
    return {
        "id": user["id"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "account_type": user.get("account_type", ACCOUNT_STUDENT),
        "org_type": user.get("org_type"),
        "active": user.get("active", True),
        "email_verified": user.get("email_verified", False),
        "mfa_enabled": user.get("mfa_enabled", False),
        "mfa_required": user.get("mfa_required", False),
        "inactivity_timeout_minutes": user.get("inactivity_timeout_minutes"),
        "password_changed_at": user.get("password_changed_at"),
        "profile": public_profile,
        "settings": user.get("settings") or {},
        "created_at": user.get("created_at"),
    }


# ---------------------------------------------------------------------------
# CompatAuthStore - legacy document store (MongoDB / local JSON)
# ---------------------------------------------------------------------------


class CompatAuthStore:
    """Auth records persisted through the existing document store.

    Uses the same collections the rest of the application reads so demo users
    and v1 users coexist transparently.
    """

    name = "compat"

    def __init__(self, db: Any):
        self._db = db

    # --- users ------------------------------------------------------------

    def create_user(self, payload: dict) -> dict:
        doc = dict(payload)
        doc["id"] = doc.get("id") or new_id()
        doc.setdefault("role", "user")
        doc.setdefault("active", True)
        doc.setdefault("email_verified", False)
        doc.setdefault("mfa_enabled", False)
        doc.setdefault("mfa_required", False)
        doc.setdefault("mfa_secret", None)
        doc.setdefault("account_type", ACCOUNT_STUDENT)
        doc.setdefault("org_type", None)
        doc.setdefault("profile", {})
        doc.setdefault("settings", {})
        doc["password_changed_at"] = doc.get("password_changed_at") or datetime_now()
        if not doc.get("inactivity_timeout_minutes"):
            doc["inactivity_timeout_minutes"] = settings.DEFAULT_INACTIVITY_TIMEOUT_MINUTES
        self._db.insert("users", doc)
        return normalize_user(self._db.find_one("users", {"id": doc["id"]}))

    def get_user_by_email(self, email: str) -> dict | None:
        return normalize_user(
            self._db.find_one("users", {"email": (email or "").strip().lower()})
        )

    def get_user(self, user_id: str) -> dict | None:
        return normalize_user(self._db.find_one("users", {"id": user_id}))

    def update_user(self, user_id: str, patch: dict) -> dict | None:
        safe = {k: v for k, v in patch.items() if k not in ("id", "_id", "created_at")}
        self._db.update("users", user_id, safe)
        return normalize_user(self._db.find_one("users", {"id": user_id}))

    def delete_user(self, user_id: str) -> None:
        self._db.delete("users", user_id)

    # --- email verifications ----------------------------------------------

    def create_email_verification(self, user_id: str, purpose: str, code: str, ttl_minutes: int | None = None) -> dict:
        expires = (
            datetime.now(timezone.utc)
            + timedelta(minutes=ttl_minutes or settings.AUTH_OTP_TTL_MINUTES)
        ).isoformat()
        self._db.insert(
            "email_verifications",
            {
                "user_id": user_id,
                "purpose": purpose,
                "code_hash": _hash_verification_code(code),
                "expires_at": expires,
                "consumed": False,
                "created_at": datetime_now(),
            },
        )
        return {"expires_at": expires}

    def consume_email_verification(self, user_id: str, purpose: str, code: str) -> str:
        code_hash = _hash_verification_code(code)
        candidates = sorted(
            self._db.find("email_verifications", {"user_id": user_id, "purpose": purpose}),
            key=lambda d: d.get("created_at") or "",
            reverse=True,
        )
        for row in candidates:
            expires = row.get("expires_at")
            if row.get("consumed"):
                continue
            if expires and _parse_iso(expires) < datetime.now(timezone.utc):
                self._db.update("email_verifications", row["id"], {"consumed": True})
                continue
            if row.get("code_hash") == code_hash:
                self._db.update("email_verifications", row["id"], {"consumed": True})
                return "ok"
            return "invalid"
        return "not_found"

    # --- sessions ---------------------------------------------------------

    def create_session(
        self,
        user_id: str,
        refresh_token_hash: str,
        device_label: str,
        ip_address: str,
        expires_at: str,
    ) -> dict:
        session_id = str(uuid.uuid4())
        self._db.insert(
            "sessions",
            {
                "session_id": session_id,
                "user_id": user_id,
                "refresh_token_hash": refresh_token_hash,
                "device_label": device_label or "",
                "ip_address": ip_address or "",
                "created_at": datetime_now(),
                "last_seen_at": datetime_now(),
                "expires_at": expires_at,
                "revoked": False,
            },
        )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        return self._db.find_one("sessions", {"session_id": session_id})

    def get_session_by_refresh_hash(self, refresh_token_hash: str) -> dict | None:
        return self._db.find_one("sessions", {"refresh_token_hash": refresh_token_hash})

    def get_user_sessions(self, user_id: str) -> list[dict]:
        return list(
            reversed(self._db.find("sessions", {"user_id": user_id}))
        )

    def update_session(self, session_id: str, patch: dict) -> dict | None:
        safe = {k: v for k, v in patch.items() if k not in ("session_id", "id")}
        session = self._db.find_one("sessions", {"session_id": session_id})
        if not session:
            return None
        self._db.update("sessions", session["id"], safe)
        return self.get_session(session_id)

    def revoke_session(self, session_id: str) -> bool:
        session = self._db.find_one("sessions", {"session_id": session_id})
        if not session:
            return False
        self._db.update("sessions", session["id"], {"revoked": True})
        return True

    def revoke_user_sessions_except(self, user_id: str, keep_session_id: str | None) -> int:
        count = 0
        for s in self._db.find("sessions", {"user_id": user_id}):
            if s.get("session_id") != keep_session_id and not s.get("revoked"):
                self._db.update("sessions", s["id"], {"revoked": True})
                count += 1
        return count

    def delete_user_sessions(self, user_id: str) -> int:
        count = 0
        for s in self._db.find("sessions", {"user_id": user_id}):
            self._db.delete("sessions", s["id"])
            count += 1
        return count


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _hash_verification_code(code: str) -> str:
    import hashlib

    return hashlib.sha256(
        f"verify:{settings.JWT_SECRET}:{code}".encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# PostgresAuthStore - PostgreSQL / PostGIS backend
# ---------------------------------------------------------------------------

_PG_THREAD = threading.local()
_PG_SCHEMA_READY = False
_PG_SCHEMA_LOCK = threading.Lock()


class PostgresAuthStore:
    """Auth records persisted in PostgreSQL (psycopg v3) with PostGIS.

    Tables: ``users``, ``sessions``, ``email_verifications``. PostGIS is
    enabled when available (used by sibling geospatial modules); auth itself
    only needs plain SQL.
    """

    name = "postgres"

    def __init__(self, dsn: str = ""):
        self._dsn = dsn or settings.POSTGRES_DSN
        self._bootstrap()

    # --- connection -------------------------------------------------------

    def _conn(self):
        import psycopg

        conn = getattr(_PG_THREAD, "conn", None)
        if conn is None or conn.closed:
            conn = psycopg.connect(self._dsn, connect_timeout=3)
            conn.autocommit = True
            _PG_THREAD.conn = conn
        return conn

    def _bootstrap(self) -> None:
        global _PG_SCHEMA_READY
        if _PG_SCHEMA_READY:
            return
        with _PG_SCHEMA_LOCK:
            if _PG_SCHEMA_READY:
                return
            conn = self._conn()
            cur = conn.cursor()
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            except Exception:
                pass  # PostGIS optional - auth works without it
            cur.execute(self.SCHEMA_SQL)
            conn.commit()
            _PG_SCHEMA_READY = True

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        account_type TEXT NOT NULL DEFAULT 'student',
        org_type TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        email_verified BOOLEAN NOT NULL DEFAULT FALSE,
        mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        mfa_required BOOLEAN NOT NULL DEFAULT FALSE,
        mfa_secret TEXT,
        inactivity_timeout_minutes INT NOT NULL DEFAULT 15,
        password_changed_at TIMESTAMPTZ,
        profile JSONB NOT NULL DEFAULT '{}',
        settings JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        refresh_token_hash TEXT NOT NULL UNIQUE,
        device_label TEXT NOT NULL DEFAULT '',
        ip_address TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ NOT NULL,
        revoked BOOLEAN NOT NULL DEFAULT FALSE
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    CREATE TABLE IF NOT EXISTS email_verifications (
        verification_id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        purpose TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        consumed BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_email_verify_user
        ON email_verifications(user_id, purpose, created_at DESC);
    """

    @staticmethod
    def _dict_from_row(row, keys) -> dict:
        return {k: v for k, v in zip(keys, row) if k != "_unused"}

    USER_KEYS = [
        "id",
        "name",
        "email",
        "password_hash",
        "role",
        "account_type",
        "org_type",
        "active",
        "email_verified",
        "mfa_enabled",
        "mfa_required",
        "mfa_secret",
        "inactivity_timeout_minutes",
        "password_changed_at",
        "profile",
        "settings",
        "created_at",
        "updated_at",
    ]

    # --- users ------------------------------------------------------------

    def create_user(self, payload: dict) -> dict:
        user_id = str(uuid.uuid4())
        password_changed = payload.get("password_changed_at")
        if isinstance(password_changed, str):
            try:
                password_changed = datetime.fromisoformat(password_changed)
            except ValueError:
                password_changed = None
        if password_changed is None:
            password_changed = datetime.now(timezone.utc)
        keys = [
            "name",
            "email",
            "password_hash",
            "role",
            "account_type",
            "org_type",
            "active",
            "email_verified",
            "mfa_enabled",
            "mfa_required",
            "mfa_secret",
            "inactivity_timeout_minutes",
            "profile",
            "settings",
            "password_changed_at",
        ]
        vals = [
            payload.get("name", ""),
            (payload.get("email") or "").strip().lower(),
            payload.get("password_hash", ""),
            payload.get("role", "user"),
            payload.get("account_type", ACCOUNT_STUDENT),
            payload.get("org_type"),
            bool(payload.get("active", True)),
            bool(payload.get("email_verified", False)),
            bool(payload.get("mfa_enabled", False)),
            bool(payload.get("mfa_required", False)),
            payload.get("mfa_secret"),
            int(payload.get("inactivity_timeout_minutes") or settings.DEFAULT_INACTIVITY_TIMEOUT_MINUTES),
            json.dumps(payload.get("profile") or {}),
            json.dumps(payload.get("settings") or {}),
            password_changed,
        ]
        now = datetime.now(timezone.utc)
        cur = self._conn().cursor()
        cur.execute(
            """
            INSERT INTO users (id, name, email, password_hash, role, account_type,
                org_type, active, email_verified, mfa_enabled, mfa_required,
                mfa_secret, inactivity_timeout_minutes, profile, settings,
                password_changed_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, *vals, now, now),
        )
        return normalize_user(self.get_user(user_id))

    def get_user_by_email(self, email: str) -> dict | None:
        cur = self._conn().cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", [(email or "").strip().lower()])
        row = cur.fetchone()
        return normalize_user(self._dict_from_row(row, self.USER_KEYS)) if row else None

    def get_user(self, user_id: str) -> dict | None:
        cur = self._conn().cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", [user_id])
        row = cur.fetchone()
        return normalize_user(self._dict_from_row(row, self.USER_KEYS)) if row else None

    def update_user(self, user_id: str, patch: dict) -> dict | None:
        cols, vals = [], []
        for key, value in patch.items():
            if key in ("id", "_id", "created_at") or key not in self.USER_KEYS:
                continue
            cols.append(f"{key} = %s")
            if key in ("profile", "settings"):
                vals.append(json.dumps(value))
            elif key == "password_changed_at" and isinstance(value, str):
                try:
                    vals.append(datetime.fromisoformat(value))
                except ValueError:
                    vals.append(value)
            elif key == "inactivity_timeout_minutes":
                vals.append(int(value))
            else:
                vals.append(value)
        if cols:
            cur = self._conn().cursor()
            cur.execute(
                f"UPDATE users SET {', '.join(cols)}, updated_at = now() "
                f"WHERE id = %s",
                [*vals, user_id],
            )
        return normalize_user(self.get_user(user_id))

    def delete_user(self, user_id: str) -> None:
        cur = self._conn().cursor()
        cur.execute("DELETE FROM users WHERE id = %s", [user_id])

    # --- email verifications ----------------------------------------------

    def create_email_verification(self, user_id: str, purpose: str, code: str, ttl_minutes: int | None = None) -> dict:
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=ttl_minutes or settings.AUTH_OTP_TTL_MINUTES
        )
        cur = self._conn().cursor()
        cur.execute(
            """
            INSERT INTO email_verifications (verification_id, user_id, purpose,
                code_hash, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), user_id, purpose, _hash_verification_code(code), expires),
        )
        return {"expires_at": expires.isoformat()}

    def consume_email_verification(self, user_id: str, purpose: str, code: str) -> str:
        code_hash = _hash_verification_code(code)
        cur = self._conn().cursor()
        cur.execute(
            """
            SELECT verification_id, expires_at, code_hash, consumed
            FROM email_verifications
            WHERE user_id = %s AND purpose = %s
            ORDER BY created_at DESC
            """,
            (user_id, purpose),
        )
        for row in cur.fetchall():
            vid, expires_at, stored_hash, consumed = row
            if consumed:
                continue
            if expires_at and expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                cur.execute(
                    "UPDATE email_verifications SET consumed = TRUE WHERE verification_id = %s", [vid]
                )
                continue
            if stored_hash == code_hash:
                cur.execute(
                    "UPDATE email_verifications SET consumed = TRUE WHERE verification_id = %s", [vid]
                )
                return "ok"
            return "invalid"
        return "not_found"

    # --- sessions ---------------------------------------------------------

    SESSION_KEYS = [
        "session_id",
        "user_id",
        "refresh_token_hash",
        "device_label",
        "ip_address",
        "created_at",
        "last_seen_at",
        "expires_at",
        "revoked",
    ]

    def _session_from_row(self, row) -> dict | None:
        return self._dict_from_row(row, self.SESSION_KEYS) if row else None

    def create_session(
        self,
        user_id: str,
        refresh_token_hash: str,
        device_label: str,
        ip_address: str,
        expires_at: str,
    ) -> dict:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        try:
            expires_dt = datetime.fromisoformat(expires_at)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            expires_dt = now + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)
        cur = self._conn().cursor()
        cur.execute(
            """
            INSERT INTO sessions (session_id, user_id, refresh_token_hash,
                device_label, ip_address, created_at, last_seen_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (session_id, user_id, refresh_token_hash, device_label, ip_address, now, now, expires_dt),
        )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict | None:
        cur = self._conn().cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id = %s", [session_id])
        return self._session_from_row(cur.fetchone())

    def get_session_by_refresh_hash(self, refresh_token_hash: str) -> dict | None:
        cur = self._conn().cursor()
        cur.execute("SELECT * FROM sessions WHERE refresh_token_hash = %s", [refresh_token_hash])
        return self._session_from_row(cur.fetchone())

    def get_user_sessions(self, user_id: str) -> list[dict]:
        cur = self._conn().cursor()
        cur.execute(
            "SELECT * FROM sessions WHERE user_id = %s ORDER BY created_at DESC", [user_id]
        )
        return [self._session_from_row(r) for r in cur.fetchall() if r]

    def update_session(self, session_id: str, patch: dict) -> dict | None:
        cols, vals = [], []
        for key, value in patch.items():
            if key in self.SESSION_KEYS and key != "session_id":
                cols.append(f"{key} = %s")
                vals.append(value)
        if cols:
            cur = self._conn().cursor()
            cur.execute(f"UPDATE sessions SET {', '.join(cols)} WHERE session_id = %s", [*vals, session_id])
        return self.get_session(session_id)

    def revoke_session(self, session_id: str) -> bool:
        cur = self._conn().cursor()
        cur.execute("UPDATE sessions SET revoked = TRUE WHERE session_id = %s", [session_id])
        return cur.rowcount > 0

    def revoke_user_sessions_except(self, user_id: str, keep_session_id: str | None) -> int:
        cur = self._conn().cursor()
        params: list[Any] = [user_id]
        sql = "UPDATE sessions SET revoked = TRUE WHERE user_id = %s"
        if keep_session_id:
            sql += " AND session_id <> %s"
            params.append(keep_session_id)
        sql += " AND revoked = FALSE"
        cur.execute(sql, params)
        return cur.rowcount

    def delete_user_sessions(self, user_id: str) -> int:
        cur = self._conn().cursor()
        cur.execute("DELETE FROM sessions WHERE user_id = %s", [user_id])
        return cur.rowcount


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Store selection
# ---------------------------------------------------------------------------

_store: AuthStoreLike = None  # type: ignore
_store_probe_done = False
_store_backend = "pending"


def _try_postgres() -> PostgresAuthStore | None:
    try:
        from psycopg import OperationalError  # noqa: F401

        store = PostgresAuthStore()
        # Force a connection so failures surface during probing.
        store.get_user("00000000-0000-0000-0000-000000000000")
        return store
    except Exception as exc:
        print(f"[satquery] PostgreSQL unreachable ({exc}) - using legacy auth store.")
        return None


def _get_store() -> AuthStoreLike:
    global _store, _store_probe_done, _store_backend
    if _store is not None:
        return _store
    if not _store_probe_done:
        _store_probe_done = True
        mode = settings.AUTH_STORE
        if mode == "postgres":
            store = _try_postgres()
            if store is None:
                raise RuntimeError(
                    "AUTH_STORE=postgres requires PostgreSQL (POSTGRES_DSN). "
                    "Set AUTH_STORE=compat to use the legacy store."
                )
            _store = store
            _store_backend = "postgres"
        elif mode == "compat":
            _store = CompatAuthStore(get_db())
            _store_backend = "compat"
        else:  # auto
            store = _try_postgres()
            if store is not None:
                _store = store
                _store_backend = "postgres"
            else:
                _store = CompatAuthStore(get_db())
                _store_backend = "compat"
        print(f"[satquery] auth store backend: {_store_backend}")
    return _store


def get_auth_store() -> AuthStoreLike:
    return _get_store()


def get_auth_store_backend() -> str:
    get_auth_store()
    return _store_backend


def reset_auth_store_for_tests() -> None:
    global _store, _store_probe_done, _store_backend
    _store = None
    _store_probe_done = False
    _store_backend = "pending"


# Legacy aliases used by profile/settings routes so they work for both backends.
def get_user(user_id: str) -> dict | None:
    return get_auth_store().get_user(user_id)


def update_user(user_id: str, patch: dict) -> dict | None:
    return get_auth_store().update_user(user_id, patch)