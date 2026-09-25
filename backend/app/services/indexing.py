"""Spatial / temporal / semantic catalogue indexing for datasets.

Implements a lightweight multi-axis ranking used for data retrieval:

* spatial score  - bbox overlap between dataset and query AOI
* temporal score - temporal overlap between dataset and requested window
* semantic score - deterministic character-n-gram embedding + cosine over
                   dataset descriptions, name, tags vs. the query text

A real vector index (FAISS) or ML embedding model is used automatically when
the optional dependencies are installed; otherwise the deterministic index
keeps every search reproducible and explainable.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

from ..geo import bbox_overlap


# ---------------------------------------------------------------------------
# Deterministic semantic embedding
# ---------------------------------------------------------------------------

_VOCAB_SIZE = 512


def _trigrams(text: str) -> set[str]:
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    words = text.split()
    grams: set[str] = set()
    for w in words:
        padded = "  " + w + " "
        for i in range(len(padded) - 2):
            grams.add(padded[i : i + 3])
    return grams


def embed(text: str) -> list[float]:
    """Hash trigrams into a sparse unit vector."""
    vec = [0.0] * _VOCAB_SIZE
    for g in _trigrams(text):
        idx = int(hashlib.sha256(g.encode()).hexdigest()[:4], 16) % _VOCAB_SIZE
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _try_embed(text: str) -> list[float]:
    """Use an ML embedding model when available, else the deterministic one."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = getattr(_try_embed, "model", None)
        if model is None:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            _try_embed.model = model
        return model.encode(text, normalize_embeddings=True).tolist()
    except Exception:
        return embed(text)


class SemanticIndex:
    """In-memory semantic index over a set of dataset documents."""

    def __init__(self, documents: list[dict]):
        self.labels: list[str] = []
        self.vectors: list[list[float]] = []
        self.ids: list[str] = []
        self._faiss_index = None
        self._build(documents)

    def _build(self, documents: list[dict]) -> None:
        for doc in documents:
            text = " ".join(
                [
                    str(doc.get("name", "")),
                    str(doc.get("description", "")),
                    " ".join(doc.get("tags", [])),
                    str(doc.get("data_type", "")),
                ]
            )
            self.ids.append(doc["id"])
            self.vectors.append(_try_embed(text))
            self.labels.append(text)
        try:  # FAISS replaces brute-force search when installable
            import faiss  # type: ignore

            if self.vectors:
                import numpy as np

                mat = np.asarray(self.vectors, dtype="float32")
                idx = faiss.IndexFlatIP(mat.shape[1])
                idx.add(mat)
                self._faiss_index = idx
                self._faiss_matrix = mat
        except Exception:
            self._faiss_index = None

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        qv = _try_embed(query)
        if self._faiss_index is not None:
            import numpy as np

            scores, idxs = self._faiss_index.search(
                np.asarray([qv], dtype="float32"), min(top_k, len(self.ids))
            )
            hits = []
            for score, i in zip(scores[0], idxs[0]):
                if i < 0:
                    continue
                hits.append({"id": self.ids[i], "semantic_score": round(float(score), 4)})
            return hits
        scored = sorted(
            ((cosine(qv, v), i) for i, v in enumerate(self.vectors)),
            key=lambda kv: kv[0],
            reverse=True,
        )
        return [
            {"id": self.ids[i], "semantic_score": round(float(s), 4)}
            for s, i in scored[:top_k]
        ]
def _overlap_frac(a: dict, b: dict) -> float:
    """Fraction of query bbox overlapped by dataset bbox (0..1)."""
    if not bbox_overlap(a, b):
        return 0.0
    ox = min(a["max_lng"], b["max_lng"]) - max(a["min_lng"], b["min_lng"])
    oy = min(a["max_lat"], b["max_lat"]) - max(a["min_lat"], b["min_lat"])
    qw = max(a["max_lng"] - a["min_lng"], 1e-9)
    qh = max(a["max_lat"] - a["min_lat"], 1e-9)
    return min(1.0, (ox * oy) / (qw * qh))


def _temporal_overlap(ds: dict, start: str | None, end: str | None) -> float:
    if not start and not end:
        return 1.0
    ds_start = (ds.get("temporal") or {}).get("start", "1900-01-01")
    ds_end = (ds.get("temporal") or {}).get("end", "2100-01-01")
    qs = start or "1900-01-01"
    qe = end or "2100-01-01"
    if qe < ds_start or ds_end < qs:
        return 0.0
    return 1.0


def search_datasets(
    db,
    understanding: dict,
    limit: int = 8,
    semantic_index: SemanticIndex | None = None,
) -> list[dict]:
    """Rank datasets by spatial + temporal + semantic + type/phenomenon match."""
    datasets = db.find("datasets", {})
    if not datasets:
        return []
    query_bbox = understanding.get("bbox")
    query_text = understanding.get("query_text", "")
    dtype_q = (understanding.get("data_type") or "").lower()
    phenom_q = (understanding.get("phenomenon") or "").lower()

    semantic: dict[str, float] = {}
    if semantic_index is not None and query_text:
        for hit in semantic_index.search(query_text, top_k=limit * 3):
            semantic[hit["id"]] = hit["semantic_score"]

    scored: list[tuple[float, dict]] = []
    for ds in datasets:
        s = 0.0
        ds_dtype = (ds.get("data_type") or "").lower()
        ds_phens = [str(p).lower() for p in ds.get("phenomenons", [])]
        if dtype_q and dtype_q != "any":
            s += 2.0 if ds_dtype == dtype_q else 0.0
        if phenom_q and phenom_q in ds_phens:
            s += 1.5
        if query_bbox:
            s += 1.5 * _overlap_frac(query_bbox, ds.get("bbox") or query_bbox)
        tt = (ds.get("temporal") or {}).get("count", 0)
        if tt:
            s += 0.25 * min(1.0, tt / 40)
        s += 0.5 * _temporal_overlap(
            ds, understanding.get("date_start"), understanding.get("date_end")
        )
        s += 1.0 * semantic.get(ds["id"], 0.0)
        scored.append((round(s, 3), ds))

    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [ds for _, ds in scored[:limit]]