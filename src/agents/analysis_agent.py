"""
Analysis Agent — reasons over the Data Agent's output. No tools, by
construction: this module imports nothing that can reach FRED, the MCP
tools, or the network. It only reads the numbers in `DataAgentResult`.

It deliberately never looks at `SeriesData.metadata` (where the wrapped,
untrusted FRED notes live) — it works purely from `observations`, so no
external text can influence its reasoning.

Phase 1 produces structured descriptive stats (trend, change over the
window, annualised rate) and a grounded one-line summary per series. A
narrative Report Agent is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import cost_tracker
from agents.data_agent import DataAgentResult, SeriesData


@dataclass
class SeriesAnalysis:
    series_id: str
    units: str
    date_range: tuple[str, str]
    n_observations: int
    start_value: float
    end_value: float
    absolute_change: float
    percent_change: float
    direction: str  # "up" | "down" | "flat"
    annualized_pct: float | None
    summary: str
    error: str | None = None


@dataclass
class AnalysisResult:
    answer: str = ""
    per_series: list[SeriesAnalysis] = field(default_factory=list)
    error: str | None = None
    cost: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.per_series)


def _numeric(observations: list[dict]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for o in observations:
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _years_between(start: str, end: str) -> float:
    try:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
        return max((d1 - d0).days / 365.25, 0.0)
    except ValueError:
        return 0.0


def _analyze_series(s: SeriesData) -> SeriesAnalysis:
    base = SeriesAnalysis(
        series_id=s.series_id,
        units=s.units,
        date_range=(s.start_date, s.end_date),
        n_observations=s.observation_count,
        start_value=0.0,
        end_value=0.0,
        absolute_change=0.0,
        percent_change=0.0,
        direction="flat",
        annualized_pct=None,
        summary="",
    )

    if s.error:
        base.error = s.error
        base.summary = f"{s.series_id}: no analysis — data error ({s.error})."
        return base

    points = _numeric(s.observations)
    if len(points) < 2:
        base.error = "insufficient_data"
        base.summary = f"{s.series_id}: not enough observations to analyse."
        return base

    (first_date, first), (last_date, last) = points[0], points[-1]
    abs_change = round(last - first, 3)
    pct_change = round((last - first) / first * 100, 2) if first else 0.0
    direction = "up" if abs_change > 0 else "down" if abs_change < 0 else "flat"

    span_years = _years_between(first_date, last_date)
    annualized = None
    if span_years >= 1.0 and first > 0 and last > 0:
        annualized = round(((last / first) ** (1 / span_years) - 1) * 100, 2)

    base.start_value = round(first, 3)
    base.end_value = round(last, 3)
    base.absolute_change = abs_change
    base.percent_change = pct_change
    base.direction = direction
    base.annualized_pct = annualized

    ann = f", an annualised {annualized:+.2f}%" if annualized is not None else ""
    base.summary = (
        f"{s.series_id} ({s.units}) went {direction} {pct_change:+.2f}% "
        f"from {first_date} to {last_date} ({base.start_value} → {base.end_value}){ann}."
    )
    return base


def analyze(data: DataAgentResult) -> AnalysisResult:
    if not data.series:
        return AnalysisResult(
            error=data.errors[0] if data.errors else "no_data",
            cost=cost_tracker.stage_cost("analysis_agent", "{}", "{}").as_dict(),
        )

    per_series = [_analyze_series(s) for s in data.series]
    usable = [a for a in per_series if a.error is None]

    if not usable:
        answer = "Could not analyse the requested data: " + "; ".join(
            a.summary for a in per_series
        )
        error = "no_analyzable_series"
    else:
        answer = " ".join(a.summary for a in usable)
        error = None

    result = AnalysisResult(answer=answer, per_series=per_series, error=error)
    result.cost = cost_tracker.stage_cost(
        "analysis_agent",
        _input_repr(data),
        answer + " ".join(a.summary for a in per_series),
    ).as_dict()
    return result


def _input_repr(data: DataAgentResult) -> str:
    return "".join(
        f"{s.series_id}:{s.observation_count}pts " for s in data.series
    )
