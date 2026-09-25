"""Satellite data providers.

* ``DemoProvider`` serves the seeded demo catalog (instant, offline, clearly
  labelled simulated).
* ``StacProvider`` is a real, key-free STAC client (Earth Search / AWS) that can
  retrieve genuine Sentinel-1/2 scene metadata for later processing when the
  optional geo/raster stack (rasterio, GDAL) is installed.
* Sentinel/Landsat sub-classes wire credential-based catalogs once keys exist.

The pipeline prefers real providers when configured, otherwise falls back to
demo datasets and never presents them as real observations.
"""
from __future__ import annotations

import httpx
from typing import Optional

from ..config import settings

STAC_ENDPOINT = "https://earth-search.aws.element84.com/v1/search"
_COLLECTIONS = {"sentinel-2-l2a": "Sentinel-2", "sentinel-1-grd": "Sentinel-1"}


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    id = "base"
    label = "Base"

    def available(self) -> bool:
        raise NotImplementedError

    def search(self, bbox: dict, start: str, end: str, data_type: str, limit: int = 40) -> dict:
        """Return {"scenes": [..], "note": str, "real": bool}."""
        raise NotImplementedError


class DemoProvider(BaseProvider):
    """Serves the pre-seeded simulated catalog. Always available."""

    id = "demo"
    label = "Demo (simulated)"

    def __init__(self, db):
        self.db = db

    def available(self) -> bool:
        return True

    def search(self, bbox, start, end, data_type, limit=40) -> dict:
        scenes = self.db.find("datasets", {"source": "DEMO"})
        if data_type and data_type.lower() not in ("any", ""):
            scenes = [s for s in scenes if s.get("data_type", "").lower() == data_type.lower()]
        matched = [s for s in scenes if _bbox_fits(s.get("bbox"), bbox)]
        return {
            "scenes": matched[:limit],
            "note": "Demo simulated data catalog (clearly labelled, not real imagery).",
            "real": False,
        }
class StacProvider(BaseProvider):
    """Real STAC search over AWS Earth Search (Sentinel-1/2, key-free)."""

    id = "stac"
    label = "Sentinel (STAC / Earth Search)"

    def __init__(self, endpoint: str = STAC_ENDPOINT, timeout: float = 20.0):
        self.endpoint = endpoint
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout, headers={"Content-Type": "application/json"})
        return self._client

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=8) as c:
                r = c.get(self.endpoint.replace("/search", ""), headers={"Accept": "application/json"})
                return r.status_code == 200
        except Exception:
            return False

    def search(self, bbox, start, end, data_type, limit=40) -> dict:
        collections = ["sentinel-2-l2a"]
        if str(data_type).upper() in ("SAR", "ANY", ""):
            collections.append("sentinel-1-grd")
        body = {
            "collections": collections,
            "bbox": [bbox["min_lng"], bbox["min_lat"], bbox["max_lng"], bbox["max_lat"]],
            "datetime": f"{start or '2015-01-01'}T00:00:00Z/{end or '2030-01-01'}T00:00:00Z",
            "limit": min(limit, 100),
        }
        try:
            r = self._get_client().post(self.endpoint, json=body)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            raise ProviderError(f"STAC search failed: {exc}") from exc
        scenes = []
        for f in data.get("features", [])[:limit]:
            props = f.get("properties", {})
            scenes.append(
                {
                    "id": f.get("id"),
                    "satellite": _COLLECTIONS.get(f.get("collection", ""), f.get("collection", "")),
                    "date": (props.get("datetime") or "")[:10],
                    "cloud_cover": props.get("eo:cloud_cover"),
                    "data_type": "SAR" if f.get("collection") == "sentinel-1-grd" else "Optical",
                    "geometry": f.get("geometry"),
                    "bbox": f.get("bbox"),
                    "real": True,
                    "note": "Real satellite scene metadata retrieved via public STAC.",
                }
            )
        return {"scenes": scenes, "note": "Real Sentinel open-data catalog (metadata search).", "real": True}
class SentinelHubProvider(BaseProvider):
    """Credential-based Sentinel (Copernicus) provider -- interface ready.

    Enable by setting SENTINEL_CLIENT_ID / SENTINEL_CLIENT_SECRET. Without these
    the provider reports itself as unavailable and the pipeline uses demo data.
    """

    id = "sentinel"
    label = "Sentinel (Copernicus Data Space)"

    def available(self) -> bool:
        return bool(settings.SENTINEL_CLIENT_ID and settings.SENTINEL_CLIENT_SECRET)

    def search(self, bbox, start, end, data_type, limit=40) -> dict:
        if not self.available():
            raise ProviderError("Sentinel credentials not configured (SENTINEL_CLIENT_ID/SECRET).")
        url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        poly = (
            f"POLYGON(({bbox['min_lng']} {bbox['min_lat']},{bbox['max_lng']} {bbox['min_lat']},"
            f"{bbox['max_lng']} {bbox['max_lat']},{bbox['min_lng']} {bbox['max_lat']},"
            f"{bbox['min_lng']} {bbox['min_lat']}))"
        )
        params = {
            "$filter": (
                f"ContentDate/Start gt {start}T00:00:00Z and "
                f"ContentDate/Start lt {end}T23:59:59Z and "
                f"OData.CSC.Intersects(area=geography'SRID=4326;{poly}')"
            ),
            "$top": limit,
        }
        with httpx.Client(timeout=30) as c:
            r = c.get(url, params=params, auth=(settings.SENTINEL_CLIENT_ID, settings.SENTINEL_CLIENT_SECRET))
            r.raise_for_status()
        return {
            "scenes": r.json().get("value", []),
            "note": "Real Copernicus Data Space catalog results.",
            "real": True,
        }


class LandsatProvider(BaseProvider):
    """USGS Landsat provider interface (requires LANDSAT_API_KEY)."""

    id = "landsat"
    label = "Landsat (USGS)"

    def available(self) -> bool:
        return bool(settings.LANDSAT_API_KEY)

    def search(self, bbox, start, end, data_type, limit=40) -> dict:
        if not self.available():
            raise ProviderError("Landsat API key not configured (LANDSAT_API_KEY).")
        url = "https://m2m.cr.usgs.gov/api/v2/json/scene/search"
        payload = {
            "apiKey": settings.LANDSAT_API_KEY,
            "datasetName": "landsat_ot_c2_l2",
            "spatialFilter": {
                "filterType": "mbr",
                "lowerLeft": {"longitude": bbox["min_lng"], "latitude": bbox["min_lat"]},
                "upperRight": {"longitude": bbox["max_lng"], "latitude": bbox["max_lat"]},
            },
            "temporalFilter": {
                "startDate": start or "2013-01-01",
                "endDate": end or "2030-01-01",
            },
            "maxResults": limit,
        }
        with httpx.Client(timeout=30) as c:
            r = c.post(url, json=payload)
            r.raise_for_status()
        return {
            "scenes": r.json().get("data", {}).get("results", []),
            "note": "Real USGS Landsat catalog results.",
            "real": True,
        }


_PROVIDER_FACTORIES = {
    "demo": lambda db: DemoProvider(db),
    "stac": lambda db: StacProvider(),
    "sentinel": lambda db: SentinelHubProvider(),
    "landsat": lambda db: LandsatProvider(),
    "realtime": lambda db: RealtimeProvider(),
}


class RealtimeProvider(BaseProvider):
    """Key-free real-time public APIs (USGS earthquakes, Open-Meteo weather)."""

    id = "realtime"
    label = "Realtime (USGS/Open-Meteo)"

    def available(self) -> bool:
        from . import realtime as _rt

        try:
            ov = _rt.fetch_overview()
            return bool(ov.get("real", True))
        except Exception:
            return False

    def search(self, bbox, start, end, data_type, limit=40) -> dict:
        from . import realtime as _rt

        quakes = _rt.fetch_earthquakes(hours=48, limit=limit)
        weather = _rt.fetch_weather()
        scenes = []
        for ev in quakes.get("events", []):
            if ev.get("lat") is None or ev.get("lng") is None:
                continue
            if bbox and not (
                bbox["min_lat"] <= ev["lat"] <= bbox["max_lat"]
                and bbox["min_lng"] <= ev["lng"] <= bbox["max_lng"]
            ):
                continue
            scenes.append({**ev, "satellite": "USGS seismic network",
                           "real": True, "data_type": "Vector"})
        for city in weather.get("cities", []):
            scenes.append({**city, "satellite": "Open-Meteo", "real": True,
                           "data_type": "Time-Series"})
        return {
            "scenes": scenes[:limit],
            "note": "Real-time observations from USGS + Open-Meteo.",
            "real": True,
        }


def get_provider(provider_id: str, db) -> BaseProvider:
    factory = _PROVIDER_FACTORIES.get(provider_id)
    if factory is None:
        raise ProviderError(f"Unknown provider: {provider_id}")
    return factory(db)


def available_providers(db) -> list[dict]:
    out = []
    for pid, factory in _PROVIDER_FACTORIES.items():
        try:
            p = factory(db)
            out.append({"id": pid, "label": p.label, "available": p.available()})
        except Exception as exc:
            out.append({"id": pid, "label": pid, "available": False})
    return out


def _bbox_fits(ds_bbox: dict | None, query_bbox: dict | None) -> bool:
    if not ds_bbox or not query_bbox:
        return True
    return not (
        ds_bbox["max_lng"] < query_bbox["min_lng"]
        or ds_bbox["min_lng"] > query_bbox["max_lng"]
        or ds_bbox["max_lat"] < query_bbox["min_lat"]
        or ds_bbox["min_lat"] > query_bbox["max_lat"]
    )