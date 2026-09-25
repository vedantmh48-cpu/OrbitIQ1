"""Dataset routes: browse the catalogue and manage datasets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import get_current_user, require_analyst
from ..services.satellite import available_providers, get_provider
from ..storage import datetime_now, get_db

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class DatasetAdd(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    provider_id: str = "custom"
    data_type: str = Field(pattern=r"^(SAR|Optical|DEM|Vector|Time-Series|Tabular|Fusion)$")
    bbox: dict
    description: str = ""
    satellite: str = ""
    resolution: str = ""
    tags: list[str] = []
    series: list[dict] = []
    grid: dict = {}


@router.get("")
def list_datasets(
    data_type: str | None = None,
    location: str | None = None,
    phenomenon: str | None = None,
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.find("datasets", {})
    if data_type:
        rows = [d for d in rows if (d.get("data_type") or "").lower() == data_type.lower()]
    if phenomenon:
        rows = [d for d in rows if phenomenon.lower() in [str(p).lower() for p in d.get("phenomenons", [])]]
    if q:
        ql = q.lower()
        rows = [d for d in rows if ql in d.get("name", "").lower() or ql in d.get("description", "").lower()]
    rows = sorted(rows, key=lambda d: d.get("created_at", ""), reverse=True)[:limit]
    return rows


@router.get("/providers")
def providers(user: dict = Depends(get_current_user), db=Depends(get_db)):
    return available_providers(db)


@router.post("/ingest")
def ingest_dataset(
    body: DatasetAdd,
    user: dict = Depends(require_analyst),
    db=Depends(get_db),
):
    """Register a new dataset (modular provider adapter ingestion point)."""
    ds = body.model_dump()
    ds.update({
        "source": "USER",
        "simulated": body.grid.get("seed") is not None,
        "location": {"name": "", "country": ""},
        "created_at": datetime_now(),
        "provider_label": "Custom ingestion",
        "phenomenons": [],
        "temporal": {"start": "", "end": "", "count": len(ds.get("series", []))},
    })
    ds_id = db.insert("datasets", ds)
    return {"ok": True, "dataset": db.find_one("datasets", {"id": ds_id})}


@router.get("/search")
def search_provider(
    provider_id: str = "stac",
    min_lng: float = 68.0,
    min_lat: float = 6.0,
    max_lng: float = 98.0,
    max_lat: float = 38.0,
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    data_type: str = "Any",
    limit: int = 15,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Live catalogue search through a provider adapter (STAC default)."""
    bbox = {"min_lng": min_lng, "min_lat": min_lat, "max_lng": max_lng, "max_lat": max_lat}
    provider = get_provider(provider_id, db)
    if not provider.available():
        raise HTTPException(status_code=400, detail="Provider unavailable (configure keys in .env).")
    try:
        return provider.search(bbox, start, end, data_type, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Provider search failed: {exc}")


@router.get("/{dataset_id}")
def dataset_detail(
    dataset_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Full dataset detail incl. a lightweight map preview (fast, deterministic)."""
    ds = db.find_one("datasets", {"id": dataset_id})
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    out = {k: v for k, v in ds.items()}
    if ds.get("source") == "DEMO" and ds.get("grid"):
        try:
            from ..geo import _field_value, as_feature_collection, grid_cell_centers

            res = float((ds.get("grid") or {}).get("res_deg", 0.05))
            seed = int((ds.get("grid") or {}).get("seed", 42))
            bb = ds.get("bbox")
            features = []
            if bb:
                coarsened = max(res, 0.08)
                for lat, lng in grid_cell_centers(bb, coarsened):
                    if len(features) >= 400:
                        break
                    half = coarsened / 2.0
                    features.append(
                        {
                            "type": "Feature",
                            "properties": {
                                "lat": round(lat, 4),
                                "lng": round(lng, 4),
                                "value": round(_field_value(seed, lat, lng), 3),
                            },
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[
                                    [lng - half, lat - half], [lng + half, lat - half],
                                    [lng + half, lat + half], [lng - half, lat + half],
                                    [lng - half, lat - half],
                                ]],
                            },
                        }
                    )
            out["preview"] = as_feature_collection(
                features, {"title": f"Preview: {ds.get('name', '')}", "simulated": True}
            )
        except Exception:
            out["preview"] = None
    return out


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    user: dict = Depends(require_analyst),
    db=Depends(get_db),
):
    ds = db.find_one("datasets", {"id": dataset_id})
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if ds.get("source") == "DEMO":
        raise HTTPException(status_code=400, detail="Demo datasets cannot be deleted.")
    db.delete("datasets", dataset_id)
    return {"ok": True, "message": "Dataset removed."}