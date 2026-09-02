"""
Orchestrator — the planning stage of the pipeline.

    Orchestrator → Data Agent(s) → Analysis Agent

Its whole job is to turn a natural-language query into a **structured plan**:
which FRED series to fetch, over what window, and whether the query is a
single-series lookup or a multi-series comparison. It never touches a FRED
tool itself — series resolution is done against the local catalog
(`catalog.resolve` / `catalog.search`), which is project knowledge, not a
network call.

The plan carries a *list* of `FetchRequest`s; the orchestration layer runs
one Data Agent per request (concurrently for multi-series queries).

Errors are returned on the dataclass (`QueryPlan.error`), never raised — same
pattern as `fred_client` / `security` at the tool boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import catalog

# How many series one query is allowed to pull — mirrors the compare_series
# cap so a plan can't fan out unboundedly.
MAX_SERIES = 4

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_LAST_N_RE = re.compile(r"(?:last|past|previous)\s+(\d{1,2})\s+years?", re.IGNORECASE)


@dataclass(frozen=True)
class FetchRequest:
    """One series the Data Agent should retrieve."""

    series_id: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    frequency: str = "m"
    fetch_observations: bool = True
    fetch_metadata: bool = True


@dataclass(frozen=True)
class QueryPlan:
    user_query: str
    fetches: tuple[FetchRequest, ...] = ()
    rationale: str = ""
    comparison: bool = False  # multi-series comparison vs. single-series lookup
    error: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.fetches)

    @property
    def mode(self) -> str:
        if self.error is not None:
            return "error"
        return "comparison" if self.comparison else "single_series"

    @property
    def tool_call_count(self) -> int:
        return sum(f.fetch_observations + f.fetch_metadata for f in self.fetches)


def _parse_window(query: str, today: date | None = None) -> tuple[str, str, str]:
    """(start_date, end_date, frequency) from the phrasing of the query."""
    today = today or date.today()
    q = query.lower()

    if "quarter" in q:
        freq = "q"
    elif "annual" in q or "yearly" in q:
        freq = "a"
    elif "daily" in q or "day" in q:
        freq = "d"
    else:
        freq = "m"

    m = _LAST_N_RE.search(q)
    if m:
        n = int(m.group(1))
        start = date(today.year - n, today.month, 1)
        return start.isoformat(), today.isoformat(), freq

    years = sorted({int(y) for y in _YEAR_RE.findall(query)})
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[-1]}-12-01", freq
    if len(years) == 1:
        return f"{years[0]}-01-01", today.isoformat(), freq

    # No window given — default to the last 5 years.
    return date(today.year - 5, today.month, 1).isoformat(), today.isoformat(), freq


def _identify_series(query: str) -> list[str]:
    """Precise matches first; fall back to the single best search hit so a
    vague-but-recognisable query still yields a plan."""
    hits = catalog.resolve(query)
    if hits:
        return hits[:MAX_SERIES]
    best = catalog.search(query, limit=1)
    return best[:1]


def plan_query(user_query: str, today: date | None = None) -> QueryPlan:
    if not user_query or not user_query.strip():
        return QueryPlan(user_query, error="empty_query", detail="No query provided.")

    series = _identify_series(user_query)
    if not series:
        return QueryPlan(
            user_query,
            error="no_series_identified",
            detail="Could not map the query to any known FRED series.",
        )

    start, end, freq = _parse_window(user_query, today)
    return _build_plan(user_query, series, start, end, freq)


def plan_for_series(
    user_query: str,
    series_ids: list[str],
    *,
    today: date | None = None,
) -> QueryPlan:
    """Build a plan for an explicit list of series IDs (window still parsed
    from the query). For callers that already know which series they want —
    and for exercising the partial-failure path with a deliberately bad ID."""
    if not series_ids:
        return QueryPlan(user_query, error="no_series_identified", detail="No series given.")
    start, end, freq = _parse_window(user_query, today)
    return _build_plan(user_query, list(series_ids)[:MAX_SERIES], start, end, freq)


def _build_plan(
    user_query: str, series: list[str], start: str, end: str, freq: str
) -> QueryPlan:
    fetches = tuple(
        FetchRequest(series_id=sid, start_date=start, end_date=end, frequency=freq)
        for sid in series
    )
    comparison = len(fetches) > 1
    kind = "comparison across" if comparison else "single-series lookup of"
    rationale = (
        f"{kind} {len(series)} series ({', '.join(series)}); "
        f"window {start}..{end} at frequency '{freq}'. "
        f"One Data Agent per series to fetch observations + metadata."
    )
    return QueryPlan(
        user_query=user_query, fetches=fetches, rationale=rationale, comparison=comparison
    )
