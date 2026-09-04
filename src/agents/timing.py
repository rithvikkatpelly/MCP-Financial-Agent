"""
Shared timing helper for agent instances.

`DataAgent` (data_agent.py) and `NewsAgent` (news_agent.py) both expose
`started_at` / `finished_at` (monotonic timestamps, set around their async
`run()`). This is the one bit of concurrency-proof logic factored out so both
agent kinds — and the orchestration layer, which gathers them together — can
answer "did these actually run at the same time, or one after another?"
without duplicating the interval-overlap check.
"""

from __future__ import annotations

from typing import Protocol


class _Timed(Protocol):
    started_at: float | None
    finished_at: float | None


def overlapped(agents: list[_Timed]) -> bool:
    """True if any two agents' [started_at, finished_at] windows overlap —
    i.e. they really ran concurrently, not sequentially."""
    windows = sorted(
        (a.started_at, a.finished_at)
        for a in agents
        if a.started_at is not None and a.finished_at is not None
    )
    return any(windows[i][1] > windows[i + 1][0] for i in range(len(windows) - 1))


def stage_wall_seconds(agents: list[_Timed]) -> float:
    """How long this stage's slowest agent took — the right number to compare
    against the batch's total wall time to see the parallelism payoff."""
    return max((a.finished_at - a.started_at for a in agents
                if a.started_at is not None and a.finished_at is not None), default=0.0)
