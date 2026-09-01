"""
Data Agent — the only agent in the pipeline with tool access.

It takes the Orchestrator's `QueryPlan` and, for each `FetchRequest`, calls
the existing MCP tools (`tools.call_tool`) — it never re-implements their
logic. Output is a strict `DataAgentResult`: structured series data, not
conversation text.

Untrusted content: `tools.get_series_metadata` already wraps the FRED `notes`
field via `security.wrap_untrusted_text`. This agent verifies that wrapping
survived and re-applies it defensively, so the provenance label can't be lost
in the hand-off to the Analysis Agent.

Errors are collected onto the result (`SeriesData.error`, `DataAgentResult.errors`),
never raised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import cost_tracker
import security
import tools
from agents.orchestrator import FetchRequest, QueryPlan

_WRAPPED_KEYS = {"untrusted_source", "untrusted_source_text", "note"}


@dataclass
class SeriesData:
    series_id: str
    title: str = ""
    units: str = ""
    frequency: str = ""
    start_date: str = ""
    end_date: str = ""
    observations: list[dict] = field(default_factory=list)  # [{"date","value"}, ...]
    metadata: dict = field(default_factory=dict)            # notes wrapped as untrusted
    error: str | None = None

    @property
    def observation_count(self) -> int:
        return len(self.observations)


@dataclass
class DataAgentResult:
    plan: QueryPlan
    series: list[SeriesData] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cost: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.series) and any(s.error is None for s in self.series)

    def series_by_id(self, series_id: str) -> SeriesData | None:
        return next((s for s in self.series if s.series_id == series_id), None)


def _ensure_wrapped_notes(metadata: dict) -> dict:
    """Guarantee metadata['notes'] is the labeled untrusted-data structure,
    whatever `get_series_metadata` handed back."""
    notes = metadata.get("notes")
    if isinstance(notes, dict) and set(notes) >= _WRAPPED_KEYS:
        return metadata
    metadata = dict(metadata)
    metadata["notes"] = security.wrap_untrusted_text(
        "fred_series_notes", notes if isinstance(notes, str) else ""
    )
    return metadata


def _fetch_one(req: FetchRequest) -> SeriesData:
    data = SeriesData(
        series_id=req.series_id,
        start_date=req.start_date,
        end_date=req.end_date,
        frequency=req.frequency,
    )

    if req.fetch_metadata:
        meta = tools.call_tool(
            "get_series_metadata", {"series_id": req.series_id}, caller="data_agent"
        )
        if meta.get("error"):
            data.error = f"metadata: {meta['error']}"
        else:
            data.title = meta.get("title", "")
            data.units = meta.get("units", "")
            data.frequency = meta.get("frequency", req.frequency)
            data.metadata = _ensure_wrapped_notes(meta)

    if req.fetch_observations:
        obs = tools.call_tool(
            "get_series_observations",
            {
                "series_id": req.series_id,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "frequency": req.frequency,
            },
            caller="data_agent",
        )
        if obs.get("error"):
            data.error = f"observations: {obs['error']}"
        else:
            data.observations = obs.get("observations", [])

    return data


def fetch(plan: QueryPlan) -> DataAgentResult:
    if not plan.ok:
        return DataAgentResult(
            plan=plan,
            errors=[plan.error or "invalid_plan"],
            cost=cost_tracker.stage_cost(
                "data_agent", json.dumps(plan.user_query), "[]"
            ).as_dict(),
        )

    series: list[SeriesData] = []
    errors: list[str] = []
    for req in plan.fetches:
        sd = _fetch_one(req)
        series.append(sd)
        if sd.error:
            errors.append(f"{sd.series_id}: {sd.error}")

    result = DataAgentResult(plan=plan, series=series, errors=errors)
    result.cost = cost_tracker.stage_cost(
        "data_agent",
        json.dumps([vars(f) for f in plan.fetches]),
        json.dumps([_series_summary(s) for s in series], default=str),
    ).as_dict()
    return result


def _series_summary(s: SeriesData) -> dict:
    return {
        "series_id": s.series_id,
        "n": s.observation_count,
        "range": [s.start_date, s.end_date],
        "error": s.error,
    }
