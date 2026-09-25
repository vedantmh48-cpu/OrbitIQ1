"""Verify deterministic rasters + live climate time-series path."""
from app.geo import _field_value

# Same inputs must produce identical values (reproducibility).
a = _field_value(42, 9.5, 76.5)
b = _field_value(42, 9.5, 76.5)
assert a == b, (a, b)
assert 0.0 <= a <= 1.0
print("deterministic field OK:", round(a, 5))

# The old builtin-hash was non-deterministic across runs; the seeded demo
# rasters must now be byte-for-byte reproducible across processes.
import subprocess
import sys

code = "from app.geo import _field_value; print(_field_value(42, 9.5, 76.5))"
r1 = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
r2 = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".")
assert r1.stdout == r2.stdout, (r1.stdout, r2.stdout)
print("cross-process reproducibility OK:", r1.stdout.strip())

# Live climate pipeline: fetch_climate returns real series when reachable.
from app.services import realtime

data = realtime.fetch_climate(19.076, 72.8777)
print("climate series points:", len(data.get("series", [])), "real:", data.get("real"))

# _time_series with live data honors the real flag
from app.services.processing import _time_series

ds = {
    "id": "live_climate_archive",
    "name": "Historical climate archive",
    "source": "REAL",
    "observed_at": "2026-01-01T00:00:00+00:00",
    "data_type": "Time-Series",
    "series": [{"date": "2026-06-01", "value": 30.0},
               {"date": "2026-06-02", "value": 31.0},
               {"date": "2026-06-03", "value": 29.5}],
}
out = _time_series(ds, {"date_start": None, "date_end": None}, {"live_series": []})
assert out["metadata"]["simulated"] is False, out["metadata"]
assert out["charts"]["timeseries"], out["charts"]
print("live time-series simulated=False OK, points:", out["stats"]["points"])
print("ALL ACCURACY CHECKS OK")