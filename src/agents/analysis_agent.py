"""
Analysis Agent — reasons over the Data Agents' output. No tools, by
construction: this module imports nothing that can reach FRED, the MCP
tools, or the network. It only reads the numbers in the DataAgentResults.

It deliberately never looks at `SeriesData.metadata` (where the wrapped,
untrusted FRED notes live) — it works purely from `observations`, so no
external text can influence its reasoning.

Input is a **list** of `DataAgentResult` (one per series). It produces:
  * per-series descriptive stats (trend, % change, direction, annualised rate)
  * cross-series stats when ≥2 series succeeded (pairwise correlation on the
    overlapping dates, strongest/weakest mover)
  * an explicit note of any series that failed and why

A narrative Report Agent is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

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
class CrossSeriesAnalysis:
    series_ids: list[str]
    overlap_points: int
    correlations: dict[str, float]  # "CPIAUCSL~UNRATE" -> -0.87
    strongest_mover: str
    weakest_mover: str
    summary: str


@dataclass
class AnalysisResult:
    answer: str = ""
    per_series: list[SeriesAnalysis] = field(default_factory=list)
    cross_series: CrossSeriesAnalysis | None = None
    failed_series: list[dict] = field(default_factory=list)  # [{series_id, reason}]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.per_series)


# --- numeric helpers ---------------------------------------------------


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
        return max((date.fromisoformat(end) - date.fromisoformat(start)).days / 365.25, 0.0)
    except ValueError:
        return 0.0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return round(sxy / (sxx**0.5 * syy**0.5), 4)


# --- per-series -----------------------------------------------------


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


# --- cross-series ----------------------------------------------------


def _analyze_cross_series(
    series: list[SeriesData], per_series: list[SeriesAnalysis]
) -> CrossSeriesAnalysis | None:
    if len(series) < 2:
        return None

    aligned = {s.series_id: dict(_numeric(s.observations)) for s in series}
    common = set.intersection(*(set(v) for v in aligned.values()))
    common_sorted = sorted(common)

    correlations: dict[str, float] = {}
    ids = [s.series_id for s in series]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            xs = [aligned[a][d] for d in common_sorted]
            ys = [aligned[b][d] for d in common_sorted]
            r = _pearson(xs, ys)
            if r is not None:
                correlations[f"{a}~{b}"] = r

    movers = {a.series_id: a.percent_change for a in per_series if a.error is None}
    strongest = max(movers, key=lambda k: abs(movers[k])) if movers else ""
    weakest = min(movers, key=lambda k: abs(movers[k])) if movers else ""

    parts = []
    if correlations:
        pretty = ", ".join(f"{k} r={v:+.2f}" for k, v in correlations.items())
        parts.append(f"Pairwise correlation over {len(common_sorted)} shared months: {pretty}.")
    if strongest and weakest and strongest != weakest:
        parts.append(
            f"{strongest} moved most ({movers[strongest]:+.2f}%), "
            f"{weakest} least ({movers[weakest]:+.2f}%)."
        )

    return CrossSeriesAnalysis(
        series_ids=ids,
        overlap_points=len(common_sorted),
        correlations=correlations,
        strongest_mover=strongest,
        weakest_mover=weakest,
        summary=" ".join(parts),
    )


# --- entry point ----------------------------------------------------


def analyze(results: list[DataAgentResult]) -> AnalysisResult:
    """Descriptive + cross-series stats. No tool access; cost is accounted for
    by the orchestration layer. Partial input is fine — failed series are
    reported, the rest are analysed."""
    ok = [r for r in results if r.ok and r.series is not None]
    failed = [
        {"series_id": r.series_id, "reason": r.failure_reason}
        for r in results
        if not r.ok
    ]

    if not ok:
        reasons = "; ".join(f"{f['series_id']}: {f['reason']}" for f in failed) or "no data"
        return AnalysisResult(
            failed_series=failed,
            error="no_analyzable_series",
            answer=f"Could not analyse the requested data ({reasons}).",
        )

    per_series = [_analyze_series(r.series) for r in ok]
    usable = [a for a in per_series if a.error is None]
    cross = _analyze_cross_series([r.series for r in ok], per_series) if len(usable) >= 2 else None

    parts = [a.summary for a in usable]
    if cross and cross.summary:
        parts.append(cross.summary)
    if failed:
        notes = "; ".join(f"{f['series_id']} ({f['reason']})" for f in failed)
        parts.append(f"Note: {len(failed)} series could not be fetched — {notes}.")

    return AnalysisResult(
        answer=" ".join(parts),
        per_series=per_series,
        cross_series=cross,
        failed_series=failed,
        error=None if usable else "no_analyzable_series",
    )
