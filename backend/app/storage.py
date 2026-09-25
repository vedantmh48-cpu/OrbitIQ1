"""Storage layer.

Two interchangeable backends behind one interface:

* MongoDB (via pymongo) when a MongoDB server is reachable.
* A local JSON file store (`backend/data/local_db.json`) used as a fully
  functional fallback so the app runs out-of-the-box without any database
  service installed.

Collection names follow the domain model: users, queries, datasets, jobs,
results, saved_analyses, settings, sessions, contacts.
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from .config import settings

COLLECTIONS = [
    "users",
    "queries",
    "datasets",
    "jobs",
    "results",
    "saved_analyses",
    "settings",
    "sessions",
    "contacts",
    "email_verifications",
    "map_catalog",
    "uploads",
]


def new_id() -> str:
    return uuid.uuid4().hex


class LocalFileStore:
    """Thread-safe JSON-file store with a MongoDB-like document API.

    Writes are atomic (tmp-file + rename) with fallbacks for Windows/OneDrive
    file-locking quirks.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict[str, Any]] = {c: {} for c in COLLECTIONS}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                for c in COLLECTIONS:
                    self._data[c] = raw.get(c, {})
            except Exception:
                self._data = {c: {} for c in COLLECTIONS}

    def _save(self) -> None:
        import os
        import time as _time

        payload = json.dumps(self._data, indent=1, default=str, ensure_ascii=False)
        tmp = self.path.with_suffix(".json.tmp")
        for attempt in range(6):
            try:  # atomic path first
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, self.path)
                return
            except OSError:
                try:  # direct-write fallback (Windows/OneDrive locks)
                    with open(self.path, "w", encoding="utf-8") as fh:
                        fh.write(payload)
                    return
                except OSError:
                    _time.sleep(0.05 * (attempt + 1))
        # Worst case: keep the latest data in memory only (still functional
        # for this process) and surface a warning.
        print("[satquery] WARNING: could not persist local DB file (locked).")

    # --- CRUD -----------------------------------------------------------

    def insert(self, collection: str, doc: dict) -> str:
        doc = dict(doc)
        doc_id = doc.get("id") or new_id()
        doc["id"] = doc_id
        doc["created_at"] = doc.get("created_at", datetime_now())
        doc["updated_at"] = datetime_now()
        with self._lock:
            self._data[collection][doc_id] = doc
            self._save()
        return doc_id

    def find_one(self, collection: str, query: dict | None = None) -> dict | None:
        for doc in self.find(collection, query, limit=1):
            return doc
        return None

    def find(
        self,
        collection: str,
        query: dict | None = None,
        sort: list | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = query or {}
        with self._lock:
            docs = [dict(d) for d in self._data[collection].values()]
        matched = [d for d in docs if _matches(d, query)]
        if sort:
            for key, direction in reversed(sort):
                matched.sort(key=lambda d: d.get(key), reverse=(direction < 0))
        if limit is not None:
            matched = matched[:limit]
        return matched

    def count(self, collection: str, query: dict | None = None) -> int:
        return len(self.find(collection, query))

    def update(self, collection: str, doc_id: str, patch: dict) -> bool:
        patch = dict(patch)
        patch.pop("id", None)
        patch.pop("_id", None)
        patch["updated_at"] = datetime_now()
        with self._lock:
            doc = self._data[collection].get(doc_id)
            if doc is None:
                return False
            doc.update(patch)
            self._save()
        return True

    def delete(self, collection: str, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._data[collection]:
                return False
            del self._data[collection][doc_id]
            self._save()
        return True

    def upsert(self, collection: str, query: dict, doc: dict) -> str:
        existing = self.find_one(collection, query)
        if existing:
            self.update(collection, existing["id"], doc)
            return existing["id"]
        return self.insert(collection, doc)

    def clear(self, collection: str | None = None) -> None:
        with self._lock:
            keys = [collection] if collection else COLLECTIONS
            for c in keys:
                self._data[c] = {}
            self._save()
class MongoStore:
    """MongoDB backend exposing the same document API."""

    def __init__(self, client: Any, db_name: str):
        self._db = client[db_name]

    def insert(self, collection: str, doc: dict) -> str:
        doc = dict(doc)
        doc["_id"] = doc.pop("id", None) or new_id()
        doc["created_at"] = doc.get("created_at", datetime_now())
        doc["updated_at"] = datetime_now()
        self._db[collection].insert_one(doc)
        return doc["_id"]

    def find_one(self, collection: str, query: dict | None = None) -> dict | None:
        doc = self._db[collection].find_one(_mongo_query(query or {}))
        return _from_mongo(doc) if doc else None

    def find(
        self,
        collection: str,
        query: dict | None = None,
        sort: list | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        cur = self._db[collection].find(_mongo_query(query or {}))
        if sort:
            cur = cur.sort([(k, d) for k, d in sort])
        if limit is not None:
            cur = cur.limit(limit)
        return [_from_mongo(d) for d in cur]

    def count(self, collection: str, query: dict | None = None) -> int:
        return self._db[collection].count_documents(_mongo_query(query or {}))

    def update(self, collection: str, doc_id: str, patch: dict) -> bool:
        patch = {k: v for k, v in patch.items() if k not in ("id", "_id")}
        patch["updated_at"] = datetime_now()
        res = self._db[collection].update_one({"_id": doc_id}, {"$set": patch})
        return res.modified_count > 0 or res.matched_count > 0

    def delete(self, collection: str, doc_id: str) -> bool:
        return self._db[collection].delete_one({"_id": doc_id}).deleted_count > 0

    def upsert(self, collection: str, query: dict, doc: dict) -> str:
        doc = dict(doc)
        q = _mongo_query(query)
        existing = self._db[collection].find_one(q)
        if existing:
            patch = {k: v for k, v in doc.items() if k not in ("id", "_id")}
            patch["updated_at"] = datetime_now()
            self._db[collection].update_one(q, {"$set": patch})
            return existing["_id"]
        doc["_id"] = doc.pop("id", None) or new_id()
        doc["created_at"] = doc.get("created_at", datetime_now())
        doc["updated_at"] = datetime_now()
        self._db[collection].insert_one(doc)
        return doc["_id"]

    def clear(self, collection: str | None = None) -> None:
        keys = [collection] if collection else COLLECTIONS
        for c in keys:
            self._db[c].delete_many({})


def _matches(doc: dict, query: dict) -> bool:
    """Tiny query language: equality, $in, $ne, $or."""
    for key, cond in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
            continue
        value = doc.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and value not in cond["$in"]:
                return False
            if "$ne" in cond and value == cond["$ne"]:
                return False
            if "$exists" in cond and (value is not None) != bool(cond["$exists"]):
                return False
        elif value != cond:
            return False
    return True


def _mongo_query(query: dict) -> dict:
    """Map id-key lookups onto _id and route $or lists."""
    out: dict[str, Any] = {}
    for key, cond in query.items():
        if key == "$or":
            out["$or"] = [_mongo_query(sub) for sub in cond]
        elif key == "id":
            out["_id"] = cond
        else:
            out[key] = cond
    return out


def _from_mongo(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = doc.pop("_id")
    return doc


def datetime_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()
# ---------------------------------------------------------------------------
# Singleton connection
# ---------------------------------------------------------------------------

_db: Any = None
_initialized = False
_db_backend: str = "unknown"


def get_db():
    """Lazily build and return the shared store instance."""
    global _db, _initialized, _db_backend
    if _initialized:
        return _db
    mode = settings.DB_MODE
    if mode != "off":
        try:
            from pymongo import MongoClient

            client = MongoClient(
                settings.MONGO_URI,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000,
            )
            client.admin.command("ping")
            _db = MongoStore(client, settings.MONGO_DB)
            _db_backend = "mongodb"
            print(f"[satquery] storage backend: MongoDB ({settings.MONGO_DB})")
        except Exception as exc:
            if mode == "on":
                raise RuntimeError(
                    f"MongoDB required (DB_MODE=on) but unreachable: {exc}"
                ) from exc
            print(
                f"[satquery] MongoDB unreachable ({exc}) - using local JSON store."
            )
            _db_backend = "local-json"
    else:
        _db_backend = "local-json"
        print("[satquery] DB_MODE=off - using local JSON store.")
    if _db is None:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _db = LocalFileStore(settings.LOCAL_DB_FILE)
    _initialized = True
    return _db


def get_db_backend() -> str:
    get_db()
    return _db_backend


def reset_db_for_tests():
    """Re-initialise the store (used by the pytest suite)."""
    global _db, _initialized
    _db = None
    _initialized = False