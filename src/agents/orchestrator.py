"""
Orchestrator — the planning stage of the pipeline.

    Orchestrator → Data Agent(s) → Analysis Agent

Its whole job is to turn a natural-language query into a **structured plan**:
which FRED series to fetch, over what window, single-series vs. comparison,
and — when it can't do that cleanly — a structured refusal or a clarification
request instead of a guess. It never touches a FRED tool itself; series
resolution is done against the local catalog (`catalog.resolve` /
`catalog.score_query`), which is project knowledge, not a network call.

The plan carries a *list* of `FetchRequest`s; the orchestration layer runs one
Data Agent per request (concurrently for multi-series queries).

This orchestrator is **deterministic** — regex + dictionary lookups, no LLM,
so it has no instruction-following surface. An embedded "ignore previous
instructions…" in a query is just (uninterpretable) text: it resolves to no
series and comes back `cannot_fulfill`. When this is swapped for an LLM
planner, the defence against that is a tightly-scoped system prompt that keeps
the role narrow — never a keyword blocklist.

Errors are returned on the dataclass (`QueryPlan.error`), never raised.
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
_VAGUE_RECENT_RE = re.compile(
    r"\b(now|today|current|currently|latest|recent|recently|lately|nowadays|these days)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FetchRequest:
    """One series the Data Agent should retrieve.

    `search_text`, when set, records that the orchestrator could not resolve
    the query to a precise series name — `series_id` is a best guess and the
    Data Agent should confirm it via `search_series` first. (Acting on that
    signal in the Data Agent is a later phase; the routing decision is
    recorded here and verified by the routing eval.)
    """

    series_id: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    frequency: str = "m"
    fetch_observations: bool = True
    fetch_metadata: bool = True
    search_text: str = ""


@dataclass(frozen=True)
class QueryPlan:
    user_query: str
    fetches: tuple[FetchRequest, ...] = ()
    rationale: str = ""
    comparison: bool = False           # multi-series comparison vs. single lookup
    resolution: str = "exact"          # "exact" | "search" | "none"
    assumptions: tuple[str, ...] = ()  # things the orchestrator had to guess
    requested_series: int = 0          # how many the query seemed to ask for
    clarification: str = ""            # question to put back to the user
    error: str | None = None           # None | empty_query | cannot_fulfill
                                       # | needs_clarification
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.fetches)

    @property
    def status(self) -> str:
        return self.error or "ok"

    @property
    def mode(self) -> str:
        if self.error is not None:
            return "error"
        return "comparison" if self.comparison else "single_series"

    @property
    def capped(self) -> bool:
        """True when the query asked for more series than the plan carries."""
        return self.requested_series > len(self.fetches)

    @property
    def via_search(self) -> bool:
        return self.resolution == "search" or any(f.search_text for f in self.fetches)

    @property
    def tool_call_count(self) -> int:
        return sum(f.fetch_observations + f.fetch_metadata for f in self.fetches)


# --- date window ------------------------------------------------------


def _parse_window(query: str, today: date | None = None) -> tuple[str, str, str, tuple[str, ...]]:
    """(start_date, end_date, frequency, assumptions).

    `assumptions` is non-empty whenever no explicit range was given and the
    orchestrator had to pick a default — so an ambiguous date range is always
    *flagged*, never silently guessed.
    """
    today = today or date.today()
    q = query.lower()

    if "quarter" in q:
        freq = "q"
    elif "annual" in q or "yearly" in q:
        freq = "a"
    elif "daily" in q:
        freq = "d"
    else:
        freq = "m"

    m = _LAST_N_RE.search(q)
    if m:
        start = date(today.year - int(m.group(1)), today.month, 1)
        return start.isoformat(), today.isoformat(), freq, ()

    if "decade" in q:
        start = date(today.year - 10, today.month, 1)
        return start.isoformat(), today.isoformat(), freq, ()

    years = sorted({int(y) for y in _YEAR_RE.findall(query)})
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[-1]}-12-01", freq, ()
    if len(years) == 1:
        return f"{years[0]}-01-01", today.isoformat(), freq, ()

    # No explicit window — pick a default and say so.
    if _VAGUE_RECENT_RE.search(q):
        start = date(today.year - 1, today.month, 1)
        note = (f"no date range given ('recently'/'current'); assumed the last "
                f"12 months ({start.isoformat()}..{today.isoformat()})")
    else:
        start = date(today.year - 5, today.month, 1)
        note = (f"no date range given; assumed the last 5 years "
                f"({start.isoformat()}..{today.isoformat()})")
    return start.isoformat(), today.isoformat(), freq, (note,)


# --- planning ---------------------------------------------------------


def plan_query(user_query: str, today: date | None = None) -> QueryPlan:
    if not user_query or not user_query.strip():
        return QueryPlan(user_query, error="empty_query", detail="No query provided.")

    q = user_query.strip()
    start, end, freq, assumptions = _parse_window(q, today)

    exact = catalog.resolve(q)
    if exact:
        if len(exact) > MAX_SERIES:
            return QueryPlan(
                user_query,
                error="needs_clarification",
                requested_series=len(exact),
                clarification=(
                    f"You named {len(exact)} series ({', '.join(exact)}). I can "
                    f"compare at most {MAX_SERIES} at once — which {MAX_SERIES}?"
                ),
                detail=f"{len(exact)} series requested; the compare limit is {MAX_SERIES}.",
            )
        return _build_plan(
            user_query, exact, start, end, freq,
            resolution="exact", assumptions=assumptions, requested_series=len(exact),
        )

    scored = catalog.score_query(q)
    if not scored:
        return QueryPlan(
            user_query,
            error="cannot_fulfill",
            detail="This doesn't map to any economic series I can fetch from FRED.",
        )

    # In scope, but not a precise series name → route through search_series.
    best = scored[0][0]
    fetch = FetchRequest(
        series_id=best, start_date=start, end_date=end, frequency=freq, search_text=q
    )
    return QueryPlan(
        user_query=user_query,
        fetches=(fetch,),
        comparison=False,
        resolution="search",
        assumptions=assumptions,
        requested_series=1,
        rationale=(
            f"'{q}' is not a precise series name; closest catalog match is {best}. "
            f"Data Agent to confirm via search_series before fetching. "
            f"Window {start}..{end} at frequency '{freq}'."
        ),
    )


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
    start, end, freq, assumptions = _parse_window(user_query, today)
    kept = list(series_ids)[:MAX_SERIES]
    return _build_plan(
        user_query, kept, start, end, freq,
        resolution="exact", assumptions=assumptions, requested_series=len(series_ids),
    )


def _build_plan(
    user_query: str,
    series: list[str],
    start: str,
    end: str,
    freq: str,
    *,
    resolution: str,
    assumptions: tuple[str, ...],
    requested_series: int,
) -> QueryPlan:
    fetches = tuple(
        FetchRequest(series_id=sid, start_date=start, end_date=end, frequency=freq)
        for sid in series
    )
    comparison = len(fetches) > 1
    kind = "comparison across" if comparison else "single-series lookup of"
    capped_note = ""
    if requested_series > len(fetches):
        capped_note = (
            f" Query implied {requested_series} series; kept the first "
            f"{len(fetches)} (compare limit is {MAX_SERIES})."
        )
    rationale = (
        f"{kind} {len(series)} series ({', '.join(series)}); "
        f"window {start}..{end} at frequency '{freq}'. "
        f"One Data Agent per series to fetch observations + metadata.{capped_note}"
    )
    return QueryPlan(
        user_query=user_query,
        fetches=fetches,
        rationale=rationale,
        comparison=comparison,
        resolution=resolution,
        assumptions=assumptions,
        requested_series=requested_series,
    )
