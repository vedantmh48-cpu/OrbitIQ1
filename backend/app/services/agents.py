"""Agentic AI layer: SAR, Optical, Temporal and Fusion agents.

Each agent turns a parsed user query plus candidate datasets into an explicit
*processing plan* (which datasets, which operations, which model, what
parameters). Plans are executed by the processing engine.

LangGraph-style orchestration is attempted when the optional `langgraph`
package is installed (used as a graph of deterministic nodes); otherwise a
native orchestrator produces identical plans -- keeping the pipeline fully
runnable offline while retaining a clean upgrade path to LLM agents.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field

_HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
_HAS_LANGCHAIN = importlib.util.find_spec("langchain_core") is not None


@dataclass
class PlanStep:
    op: str
    name: str
    params: dict = field(default_factory=dict)


class BaseAgent:
    id = "base"
    name = "Base Agent"
    model = "none"
    description = ""

    def plan(self, understanding: dict, datasets: list[dict]) -> dict:
        raise NotImplementedError


class SARAgent(BaseAgent):
    id = "sar"
    name = "SAR Agent"
    model = "sar-flood-watermask-v1 (demo deterministic model)"
    description = "Radar-based detection of water, change and ground motion; " \
                  "works through clouds and at night (Sentinel-1)."

    def plan(self, understanding, datasets):
        analysis = understanding.get("analysis_type") or "flood-mapping"
        steps = [PlanStep("flood-mapping", "SAR water mask with threshold segmentation")]
        if analysis == "change-detection":
            steps = [PlanStep("change-detection", "SAR intensity change between two dates")]
        elif analysis == "object-detection":
            steps = [PlanStep("object-detection", "Radar target detection (vessels/hard targets)")]
        elif analysis == "sar-backscatter":
            steps = [
                PlanStep("sar-backscatter", "SAR backscatter σ⁰ signature analysis (intensity, roughness, layover)"),
                PlanStep("flood-mapping", "Cross-check low-backscatter water mask from calibrated σ⁰"),
            ]
        return {
            "agent": self.id,
            "agent_name": self.name,
            "model": self.model,
            "description": self.description,
            "datasets_used": [d["id"] for d in datasets[:2]],
            "steps": [s.__dict__ for s in steps],
            "rationale": "Radar backscatter is reliable for flood/water mapping and "
                         "change detection regardless of cloud cover.",
        }


class OpticalAgent(BaseAgent):
    id = "optical"
    name = "Optical Agent"
    model = "optical-spectral-classifier-v1 (demo deterministic model)"
    description = "Visible/IR imagery for land cover, vegetation, burn scars and urban form."

    def plan(self, understanding, datasets):
        analysis = understanding.get("analysis_type") or "classification"
        steps = [PlanStep("classification", "Spectral band classification (land cover)")]
        if analysis == "change-detection":
            steps = [PlanStep("change-detection", "Multispectral before/after differencing")]
        elif analysis == "object-detection":
            steps = [PlanStep("object-detection", "Object detection from high-res optical bands")]
        elif analysis == "ndvi":
            steps = [
                PlanStep("ndvi", "Band-ratio NDVI = (NIR − RED) / (NIR + RED) vegetation health query"),
                PlanStep("ndwi", "Cross-check NDWI = (GREEN − NIR) / (GREEN + NIR) moisture signal"),
            ]
        elif analysis == "ndwi":
            steps = [
                PlanStep("ndwi", "Band-ratio NDWI = (GREEN − NIR) / (GREEN + NIR) surface-moisture query"),
                PlanStep("ndvi", "Cross-check NDVI vegetation response for consistency"),
            ]
        elif analysis == "ndbi":
            steps = [
                PlanStep("ndbi", "Band-ratio NDBI = (SWIR − NIR) / (SWIR + NIR) built-up index query"),
                PlanStep("ndwi", "Cross-check NDWI to separate bare soil from water shadow"),
            ]
        elif analysis == "ndvi" or understanding.get("phenomenon") == "crop":
            steps = [PlanStep("classification", "NDVI-based vegetation health zoning")]
        elif analysis == "image-search":
            steps = [PlanStep("image-search", "Scene catalogue retrieval by AOI and date")]
        return {
            "agent": self.id,
            "agent_name": self.name,
            "model": self.model,
            "description": self.description,
            "datasets_used": [d["id"] for d in datasets[:2]],
            "steps": [s.__dict__ for s in steps],
            "rationale": "Optical bands are best for spectral classification, NDVI, "
                         "NDWI, NDBI and urban/vegetation analyses.",
        }
class TemporalAgent(BaseAgent):
    id = "temporal"
    name = "Temporal Agent"
    model = "temporal-trend-lstm-v1 (demo deterministic regression)"
    description = "Time-series analysis over repeat satellite observations."

    def plan(self, understanding, datasets):
        steps = [PlanStep("time-series", "Temporal aggregation, trend and anomaly analysis")]
        return {
            "agent": self.id,
            "agent_name": self.name,
            "model": self.model,
            "description": self.description,
            "datasets_used": [d["id"] for d in datasets[:1]],
            "steps": [s.__dict__ for s in steps],
            "rationale": "The query emphasises temporal signals; trend and anomaly "
                         "statistics are computed across the full series.",
        }


class FusionAgent(BaseAgent):
    id = "fusion"
    name = "Fusion Agent"
    model = "fusion-ensemble-v1 (demo weighted consensus)"
    description = "Multi-sensor fusion combining SAR, optical, DEM and vector evidence."

    def plan(self, understanding, datasets):
        steps = [
            PlanStep("fusion", "Consensus fusion across co-registered layers (SAR + optical + DEM)"),
            PlanStep("flood-mapping", "Hydrological overlay using DEM lowlands"),
        ]
        return {
            "agent": self.id,
            "agent_name": self.name,
            "model": self.model,
            "description": self.description,
            "datasets_used": [d["id"] for d in datasets[:3]],
            "steps": [s.__dict__ for s in steps],
            "rationale": "Multiple sensors agree on the target, increasing confidence "
                         "and reducing single-sensor ambiguity.",
        }


AGENTS: dict[str, BaseAgent] = {
    agent.id: agent
    for agent in (SARAgent(), OpticalAgent(), TemporalAgent(), FusionAgent())
}


def route_agent(understanding: dict) -> BaseAgent:
    """Pick the agent recommended by the NLP layer."""
    agent_id = understanding.get("agent") or "optical"
    return AGENTS.get(agent_id, OpticalAgent())


def resolver_name() -> str:
    if _HAS_LANGGRAPH:
        return "langgraph"
    if _HAS_LANGCHAIN:
        return "langchain"
    return "native resolver (langgraph optional)"


def build_plan(understanding: dict, datasets: list[dict]) -> dict:
    """LangGraph-native plan when available; otherwise native fallback."""
    if _HAS_LANGGRAPH:
        try:
            from langgraph.graph import StateGraph, END  # type: ignore

            def node_route(state):
                agent = route_agent(understanding)
                return {"plan": agent.plan(understanding, datasets)}

            g = StateGraph(dict)
            g.add_node("route", node_route)
            g.add_edge("route", END)
            app = g.compile()
            return app.invoke({})["plan"]
        except Exception:
            pass
    agent = route_agent(understanding)
    return agent.plan(understanding, datasets)