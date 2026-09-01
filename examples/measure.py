"""
Turn the context/cost claims into numbers.

Runs entirely offline against the synthetic fixture (so it's deterministic and
free) and prints — and writes to docs/measurements.md — a few before/after
comparisons:

  * how a result grows with the date range and frequency, and why the tools
    require bounds
  * the shrink fallback firing (points and tokens, before vs after)
  * the budget guardrail refusing instead of dumping
  * the idempotency cache turning repeat calls into zero fetches
  * how much of each turn is prompt-cache-eligible

    python examples/measure.py

Token counts use the project's own ~4-chars/token estimate
(cost_tracker.estimate_tokens) — the same number the budget guardrail uses,
not a tokenizer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ["FRED_OFFLINE"] = "1"
os.environ.setdefault("AUDIT_LOG_PATH", os.devnull)

import cost_tracker  # noqa: E402
import fred_client  # noqa: E402
import tools  # noqa: E402
from agents import specialists  # noqa: E402
from agents.supervisor import SUPERVISOR_SYSTEM  # noqa: E402

TOK = cost_tracker.estimate_tokens


def _payload_tokens(result: dict) -> int:
    return TOK(json.dumps(result, default=str))


def bounds_and_frequency() -> str:
    rows = []
    for label, sid, start, end, freq in [
        ("CPIAUCSL, 2 years, monthly", "CPIAUCSL", "2023-01-01", "2024-12-01", "m"),
        ("CPIAUCSL, 10 years, monthly", "CPIAUCSL", "2015-01-01", "2024-12-01", "m"),
        ("CPIAUCSL, 25 years, monthly", "CPIAUCSL", "2000-01-01", "2024-12-01", "m"),
        ("DGS10, 10 years, *daily*", "DGS10", "2015-01-01", "2024-12-01", "d"),
    ]:
        fred_client._cache.clear()
        cost_tracker.reset_budget()
        r = tools.get_series_observations(sid, start, end, freq)
        n = len(r.get("observations", []))
        rows.append(f"| {label} | {n} | ~{_payload_tokens(r):,} |")
    return (
        "### Result size scales with the range — so the tools require bounds\n\n"
        "`get_series_observations` refuses an open-ended request; it needs an "
        "explicit `start_date`/`end_date`, and defaults to monthly. A single "
        "unbounded daily series is thousands of points.\n\n"
        "| Request | Observations | Est. tokens in context |\n"
        "|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def shrink_fallback() -> str:
    fred_client._cache.clear()
    cost_tracker.reset_budget()
    full = tools.get_series_observations("CPIAUCSL", "2000-01-01", "2024-12-01", "m")
    full_n, full_tok = len(full["observations"]), _payload_tokens(full)

    fred_client._cache.clear()
    cost_tracker.reset_budget()
    cost_tracker.budget.limit_tokens = 900  # forces the shrink path
    shrunk = tools.get_series_observations("CPIAUCSL", "2000-01-01", "2024-12-01", "m")
    shrunk_n, shrunk_tok = len(shrunk["observations"]), _payload_tokens(shrunk)

    return (
        "### The shrink fallback: thin, don't drop\n\n"
        "When a result won't fit the session budget, the observation list is "
        "collapsed to every 12th point plus the last one and annotated — the "
        "call still returns.\n\n"
        f"| | Points | Est. tokens |\n|---|---|---|\n"
        f"| Full result | {full_n} | ~{full_tok:,} |\n"
        f"| After shrink (budget 900) | {shrunk_n} | ~{shrunk_tok:,} |\n\n"
        f"Note added to the payload: _{shrunk.get('note', '')}_\n"
    )


def budget_refusal() -> str:
    fred_client._cache.clear()
    cost_tracker.reset_budget()
    cost_tracker.budget.limit_tokens = 200
    r = tools.compare_series(
        ["UNRATE", "CPIAUCSL", "FEDFUNDS", "DGS10"], "2000-01-01", "2024-12-01", "m"
    )
    return (
        "### Over budget → a structured refusal, not a silent dump\n\n"
        f"A 4-series, 25-year request estimated at ~{r['estimated_tokens']:,} "
        "tokens, against a 200-token budget, comes back as:\n\n"
        "```json\n" + json.dumps(r, indent=2) + "\n```\n\n"
        "~40 tokens enter the context instead of "
        f"~{r['estimated_tokens']:,}, and the model is told how to retry.\n"
    )


def cache_idempotency() -> str:
    fred_client._cache.clear()
    cost_tracker.reset_budget()
    fetches = {"n": 0}
    real = fred_client.get_observations

    def counting(sid, start, end, freq):
        key = fred_client._cache_key("obs", sid, str(start), str(end), freq)
        if key not in fred_client._cache:
            fetches["n"] += 1
        return real(sid, start, end, freq)

    fred_client.get_observations = counting
    try:
        seq = ["UNRATE", "UNRATE", "CPIAUCSL", "UNRATE", "CPIAUCSL"]
        for sid in seq:
            tools.get_series_observations(sid, "2020-01-01", "2021-01-01", "m")
    finally:
        fred_client.get_observations = real

    return (
        "### Idempotent cache: repeat calls cost nothing\n\n"
        f"Five `get_series_observations` calls, two distinct "
        f"(`{', '.join(sorted(set(seq)))}`): **{fetches['n']} fetches**, "
        f"{len(seq) - fetches['n']} served from cache. Live, that's "
        f"{len(seq) - fetches['n']} FRED requests (and rate-limit budget) saved.\n"
    )


def prompt_cache_split() -> str:
    static = TOK(json.dumps(tools.TOOL_SCHEMAS))
    static += TOK(SUPERVISOR_SYSTEM)
    for name in specialists.BUILDERS:
        sysmod = {
            "economic_data_agent": specialists.ECONOMIC_DATA_SYSTEM,
            "research_agent": specialists.RESEARCH_SYSTEM,
            "risk_agent": specialists.RISK_SYSTEM,
            "report_agent": specialists.REPORT_SYSTEM,
        }[name]
        static += TOK(sysmod)
    query = TOK("Compare CPI and unemployment over the last 5 years and explain "
                "whether the relationship changed after 2020.")
    return (
        "### Most of every turn is prompt-cache-eligible\n\n"
        f"Tool schemas + all five system prompts come to ~{static:,} tokens and "
        f"are byte-identical across a session. A typical user query is ~{query} "
        "tokens. Putting the static content first (see `cost_tracker.py`) makes "
        f"that ~{static:,}-token prefix a cache hit on every turn after the "
        "first — about 90% cheaper on the cached portion.\n"
    )


def main() -> None:
    sections = [
        bounds_and_frequency(),
        shrink_fallback(),
        budget_refusal(),
        cache_idempotency(),
        prompt_cache_split(),
    ]
    body = (
        "# Measured: context and cost\n\n"
        "_Generated by `python examples/measure.py` — offline, deterministic. "
        "Token counts are the project's ~4-chars/token estimate._\n\n"
        + "\n---\n\n".join(sections)
    )
    print(body)
    out = _ROOT / "docs" / "measurements.md"
    out.write_text(body)
    print(f"\n[wrote {out.relative_to(_ROOT)}]")


if __name__ == "__main__":
    main()
