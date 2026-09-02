"""
Measure the sequential vs. parallel Data Agent difference for a multi-series
query. Uses the offline fixture with a simulated per-call latency
(FRED_OFFLINE_LATENCY_MS) so the numbers are real and reproducible without
hitting the FRED API.

    python examples/bench_parallel.py
    FRED_OFFLINE_LATENCY_MS=200 python examples/bench_parallel.py

Prints a small table; also used to source the numbers in README §4.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ["FRED_OFFLINE"] = "1"
os.environ.setdefault("FRED_OFFLINE_LATENCY_MS", "150")
os.environ.setdefault("AGENT_TRACE_PATH", os.devnull)
os.environ.setdefault("AUDIT_LOG_PATH", os.devnull)

import fred_client  # noqa: E402
from agents.orchestrator import plan_query  # noqa: E402
from orchestration import run_query  # noqa: E402

QUERIES = [
    "How has CPI changed over the last 5 years?",
    "Compare CPI and unemployment over the last 5 years",
    "Compare CPI, unemployment, and the 10-year treasury rate over the last 5 years",
]


def _time(query: str, parallel: bool) -> float:
    fred_client._cache.clear()  # each run pays the simulated latency
    return run_query(query, parallel=parallel).wall_seconds


def main() -> None:
    latency = os.environ["FRED_OFFLINE_LATENCY_MS"]
    print(f"simulated FRED latency: {latency} ms/call  (2 calls per series: obs + metadata)\n")
    print(f"{'series':<8}{'sequential':>14}{'parallel':>14}{'speed-up':>12}")
    print("-" * 48)
    for q in QUERIES:
        n = len(plan_query(q).fetches)
        seq = _time(q, parallel=False)
        par = _time(q, parallel=True)
        print(f"{n:<8}{seq * 1000:>11.0f} ms{par * 1000:>11.0f} ms{seq / par:>10.2f}x")


if __name__ == "__main__":
    main()
