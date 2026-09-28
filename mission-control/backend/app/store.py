"""Mission Control - in-memory data store.

Holds missions, the satellite fleet, alerts and a rolling telemetry buffer.
The telemetry engine produces a deterministic, smooth pseudo-random walk so
the console has a believable live feed even in offline/demo mode.

Everything is intentionally process-local (no database dependency) so the
standalone folder runs with a single `python run.py`.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone

from . import config

# ---------------------------------------------------------------------------
# Fleet seed
# ---------------------------------------------------------------------------

SATELLITES = [
    {
        "id": "sa-07",
        "name": "SENTINEL-2A",
        "catalog": "NORAD 40697",
        "orbit": "LEO · Sun-Sync",
        "altitudeKm": 786.0,
        "inclinationDeg": 98.6,
        "status": "operational",
        "linkHealth": 99,
        "downlink": 420.0,
        "battery": 96,
        "instruments": ["MSI Optical", "Cloud masks"],
        "lastPass": "02:14 UTC",
    },
    {
        "id": "sa-09",
        "name": "SENTINEL-1B",
        "catalog": "NORAD 41321",
        "orbit": "LEO · Sun-Sync",
        "altitudeKm": 693.0,
        "inclinationDeg": 98.2,
        "status": "operational",
        "linkHealth": 97,
        "downlink": 388.0,
        "battery": 91,
        "instruments": ["C-Band SAR", "Cryosat RD"],
        "lastPass": "03:40 UTC",
    },
    {
        "id": "ge-17",
        "name": "GEOS-17",
        "catalog": "NORAD 47618",
        "orbit": "GEO · 0.0° N",
        "altitudeKm": 35786.0,
        "inclinationDeg": 0.1,
        "status": "operational",
        "linkHealth": 99,
        "downlink": 512.0,
        "battery": 98,
        "instruments": ["Earth Imager IR", "Lightning Mapper"],
        "lastPass": "Continuous",
    },
    {
        "id": "ms-03",
        "name": "MetSat-3",
        "catalog": "NORAD 45162",
        "orbit": "GEO · 93.5° E",
        "altitudeKm": 35790.0,
        "inclinationDeg": 0.0,
        "status": "operational",
        "linkHealth": 94,
        "downlink": 266.0,
        "battery": 84,
        "instruments": ["Visible", "IR Sounding"],
        "lastPass": "Continuous",
    },
    {
        "id": "cd-02",
        "name": "CONSTELL-D2",
        "catalog": "NORAD 54110",
        "orbit": "LEO · Polar",
        "altitudeKm": 582.0,
        "inclinationDeg": 97.5,
        "status": "calibrating",
        "linkHealth": 88,
        "downlink": 175.0,
        "battery": 72,
        "instruments": ["Optical", "AIS"],
        "lastPass": "01:52 UTC",
    },
    {
        "id": "nb-11",
        "name": "NIMBUS-11",
        "catalog": "NORAD 56603",
        "orbit": "LEO · Inclined",
        "altitudeKm": 714.0,
        "inclinationDeg": 53.0,
        "status": "standby",
        "linkHealth": 90,
        "downlink": 120.0,
        "battery": 79,
        "instruments": ["Altimetry", "GNSS-RO"],
        "lastPass": "04:12 UTC",
    },
]

# ---------------------------------------------------------------------------
# Alerts seed
# ---------------------------------------------------------------------------

_ALERTS = [
    {
        "severity": "high",
        "source": "Link Monitor",
        "title": "Downlink degradation on NIMBUS-11",
        "message": "X-band link margin dropped 4.1 dB during the 04:12 UTC pass. "
        "Switched to S-band backup; revisit on next horizon.",
    },
    {
        "severity": "medium",
        "source": "Thermal",
        "title": "Bus temperature drift on CONSTELL-D2",
        "message": "Payload bay trending +3.2 °C above nominal during imaging burst. "
        "Radiator loop adjusted; monitoring over next 6 h.",
    },
    {
        "severity": "low",
        "source": "Scheduler",
        "title": "Contention on GEOS-17 imaging window",
        "message": "Two high-priority targets overlap in a 6-minute window. "
        "Auto-rebalanced; METSAT-3 assigned the secondary target.",
    },
    {
        "severity": "info",
        "source": "Orbit Propagator",
        "title": "Station-keeping burn scheduled (MetSat-3)",
        "message": "East-west station-keeping burn queued for 19:20 UTC. "
        "Impact on imaging: none expected.",
    },
]


def _seed_alert(text_seed: str) -> str:
    return "alert-" + uuid.uuid5(uuid.NAMESPACE_URL, text_seed).hex[:12]


# ---------------------------------------------------------------------------
# Missions seed
# ---------------------------------------------------------------------------

_MISSIONS = [
    {
        "name": "Typhoon Belt SAR Sweep",
        "satellite": "SENTINEL-1B",
        "target": "PAC-7B · Tropical storm Corbin",
        "region": "Pacific Sector",
        "priority": "critical",
        "status": "in-progress",
        "progress": 62,
        "phase": "SAR pass · sweep 4/6",
        "eta": "ETA 02:12 UTC",
        "objective": "SAR wind retrieval across the storm corridor; "
        "narrow landfall window to ±42 km.",
        "owner": "C. Reyes",
        "created": "2026-09-22T01:05:00Z",
    },
    {
        "name": "Wildfire Index Refresh",
        "satellite": "SENTINEL-2A",
        "target": "Sector B9 · Dry corridor",
        "region": "Central Highlands",
        "priority": "high",
        "status": "queued",
        "progress": 0,
        "phase": "Queued behind priority 1",
        "eta": "ETA 06:30 UTC",
        "objective": "Soil-moisture gradient and thermal signature refresh "
        "ahead of forecast gust front.",
        "owner": "M. Iyer",
        "created": "2026-09-21T22:41:00Z",
    },
{
        "name": "Ocean Altimetry Cal Pass",
        "satellite": "NIMBUS-11",
        "target": "Equatorial band · Node 3",
        "region": "Pacific Sector",
        "priority": "normal",
        "status": "holding",
        "progress": 41,
        "phase": "Holding for link recovery",
        "eta": "ETA 08:15 UTC",
        "objective": "Sea-surface height calibration against buoy network 104.",
        "owner": "A. Sokol",
        "created": "2026-09-21T18:03:00Z",
    },
    {
        "name": "MetSat GEO Sounding Loop",
        "satellite": "MetSat-3",
        "target": "Indian Ocean disc",
        "region": "IO Corridor",
        "priority": "normal",
        "status": "in-progress",
        "progress": 78,
        "phase": "IR sounding · repeat 12/16",
        "eta": "ETA 01:50 UTC",
        "objective": "Six-hourly upper-air sounding loop for monsoon dynamics.",
        "owner": "P. Guha",
        "created": "2026-09-21T12:20:00Z",
    },
    {
        "name": "Constellation Imaging Burst",
        "satellite": "CONSTELL-D2",
        "target": "Typhoon outer band · twice daily",
        "region": "Pacific Sector",
        "priority": "normal",
        "status": "planned",
        "progress": 0,
        "phase": "Planned",
        "eta": "ETA 11:00 UTC",
        "objective": "High-revisit optical burst while the D2 pixel grid is "
        "being re-calibrated.",
        "owner": "C. Reyes",
        "created": "2026-09-22T00:12:00Z",
    },
]

MISSION_STATUS_ORDER = {
    "in-progress": 0,
    "holding": 1,
    "queued": 2,
    "planned": 3,
    "completed": 4,
    "aborted": 5,
}

# ---------------------------------------------------------------------------
# Store class
# ---------------------------------------------------------------------------


class MissionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        now = datetime.now(timezone.utc)
        self.missions: dict[str, dict] = {}
        self.satellites: dict[str, dict] = {s["id"]: dict(s) for s in SATELLITES}
        self.alerts: dict[str, dict] = {}
        self.telemetry: dict[str, deque] = {}
        self._tele_phase: dict[str, float] = {}

        for i, m in enumerate(_MISSIONS):
            mid = "mis-" + uuid.uuid5(uuid.NAMESPACE_URL, m["name"]).hex[:10]
            self.missions[mid] = {
                "id": mid,
                "name": m["name"],
                "code": "MC-" + str(10 + i).zfill(3),
                "satellite": m["satellite"],
                "target": m["target"],
                "region": m["region"],
                "priority": m["priority"],
                "status": m["status"],
                "progress": m["progress"],
                "phase": m["phase"],
                "eta": m["eta"],
                "objective": m["objective"],
                "owner": m["owner"],
                "createdAt": datetime.fromisoformat(m["created"].replace("Z", "+00:00")),
                "updatedAt": now,
            }

        for i, a in enumerate(_ALERTS):
            aid = _seed_alert(a["title"])
            self.alerts[aid] = {
                "id": aid,
                "severity": a["severity"],
                "source": a["source"],
                "title": a["title"],
                "message": a["message"],
                "createdAt": now - timedelta(minutes=12 * (i + 1)),
                "acknowledged": i > 1,
            }

        # Pre-fill one history sample per satellite so first requests are instant.
        for sid in self.satellites:
            self.telemetry[sid] = deque(maxlen=config.TELEMETRY_HISTORY)
            self._tele_phase[sid] = (hash(sid) % 360) * math.pi / 180
            self.push_telemetry(sid)

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    # -- missions ---------------------------------------------------------
    def list_missions(self) -> list[dict]:
        with self._lock:
            return sorted(
                self.missions.values(),
                key=lambda m: (MISSION_STATUS_ORDER.get(m["status"], 99), m["priority"]),
            )

    def get_mission(self, mid: str) -> dict | None:
        with self._lock:
            return self.missions.get(mid)

    def create_mission(self, payload: dict) -> dict:
        with self._lock:
            now = self.utcnow()
            mid = "mis-" + uuid.uuid4().hex[:10]
            count = len(self.missions) + 1
            mission = {
                "id": mid,
                "name": payload["name"],
                "code": "MC-" + str(100 + count).zfill(3),
                "satellite": payload["satellite"],
                "target": payload.get("target", "") or "TBD",
                "region": payload.get("region", "") or "Unassigned",
                "priority": payload.get("priority", "normal"),
                "status": "planned",
                "progress": 0,
                "phase": "Planned · awaiting go",
                "eta": "No ETA set",
                "objective": payload.get("objective", "") or "No objective recorded.",
                "owner": "Console",
                "createdAt": now,
                "updatedAt": now,
            }
            self.missions[mid] = mission
            return mission

    def update_mission(self, mid: str, patch: dict) -> dict | None:
        with self._lock:
            m = self.missions.get(mid)
            if m is None:
                return None
            for key, value in patch.items():
                if value is not None:
                    m[key] = value
            m["updatedAt"] = self.utcnow()
            return m

    def delete_mission(self, mid: str) -> bool:
        with self._lock:
            return self.missions.pop(mid, None) is not None

# -- satellites -------------------------------------------------------
    def list_satellites(self) -> list[dict]:
        with self._lock:
            return list(self.satellites.values())

    def get_satellite(self, sid: str) -> dict | None:
        with self._lock:
            return self.satellites.get(sid)

    # -- alerts -----------------------------------------------------------
    def list_alerts(self) -> list[dict]:
        with self._lock:
            unacked = [a for a in self.alerts.values() if not a["acknowledged"]]
            acked = [a for a in self.alerts.values() if a["acknowledged"]]
            return sorted(unacked, key=lambda a: a["createdAt"], reverse=True) + sorted(
                acked, key=lambda a: a["createdAt"], reverse=True
            )

    def set_ack(self, aid: str, acknowledged: bool) -> dict | None:
        with self._lock:
            a = self.alerts.get(aid)
            if a is None:
                return None
            a["acknowledged"] = acknowledged
            return a

    def push_alert(self, severity: str, source: str, title: str, message: str) -> dict:
        with self._lock:
            aid = _seed_alert(title + message[:24])
            alert = {
                "id": aid,
                "severity": severity,
                "source": source,
                "title": title,
                "message": message,
                "createdAt": self.utcnow(),
                "acknowledged": False,
            }
            self.alerts[aid] = alert
            return alert

    # -- telemetry --------------------------------------------------------
    def push_telemetry(self, sid: str) -> dict:
        """Advance one telemetry tick for a satellite (smooth random walk)."""
        with self._lock:
            sat = self.satellites.get(sid)
            history = self.telemetry.setdefault(
                sid, deque(maxlen=config.TELEMETRY_HISTORY)
            )
            phase = self._tele_phase.setdefault(sid, 0.0)
            phase += 0.22 + (hash(sid) % 7) / 40.0
            self._tele_phase[sid] = phase
            t = int(time.time())

            base_link = sat["downlink"] if sat else 300.0
            base_bat = sat["battery"] if sat else 90
            base_alt = sat["altitudeKm"] if sat else 700.0

            # Deterministic smooth walk: slow sine + tiny per-tick jitter.
            link = base_link + 24 * math.sin(phase) + 7 * math.sin(phase * 2.3)
            battery = base_bat + 2.5 * math.sin(phase * 0.6) - 0.4
            temp = 24 + 8 * math.sin(phase * 0.9) + 2 * math.sin(phase * 2.7)
            alt = base_alt + 1.2 * math.sin(phase * 0.3)
            signal = -82 + 9 * math.sin(phase * 0.8)
            data = max(0.0, (history[-1]["data"] if history else 0.0) + link * 0.36)

            sample = {
                "t": t,
                "link": round(max(0.0, link), 1),
                "battery": int(round(max(0, min(100, battery)))),
                "temp": round(temp, 1),
                "altitude": round(alt, 1),
                "signal": int(round(signal)),
                "data": round(data, 1),
            }
            history.append(sample)
            return sample

    def telemetry_snapshot(self, sid: str) -> dict | None:
        with self._lock:
            sat = self.satellites.get(sid)
            if sat is None:
                return None
            current = self.push_telemetry(sid)
            return {
                "satellite": sat["name"],
                "sampledAt": current["t"],
                "current": current,
                "history": list(self.telemetry[sid]),
            }


_store: MissionStore | None = None
_store_lock = threading.Lock()


def get_store() -> MissionStore:
    """Module-level singleton so routers and tests share one in-memory store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = MissionStore()
    return _store