"""
Orchestrator routing eval.

Runs every case in `eval_cases.ROUTING_CASES` through `orchestrator.plan_query`
only — no Data Agent, no FRED, no LLM, so it's fast and free — and checks the
plan's *structure* against the case's expectations.

Prints a full pass/fail table (not first-failure), then asserts that every
non-`xfail` case passed.

    pytest tests/test_routing.py -s      # see the table
    python tests/test_routing.py         # same table, standalone
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_cases  # noqa: E402

from agents.orchestrator import plan_query  # noqa: E402


def _run() -> list[tuple[eval_cases.RoutingCase, object, list[str]]]:
    rows = []
    for case in eval_cases.ROUTING_CASES:
        plan = plan_query(case.query)
        rows.append((case, plan, case.check(plan)))
    return rows


def _summary(rows) -> str:
    lines = []
    passed = xfailed = failed = 0
    for case, _plan, problems in rows:
        if not problems:
            mark, _ = "PASS", (passed := passed + 1)
        elif case.xfail:
            mark, _ = "XFAIL", (xfailed := xfailed + 1)
        else:
            mark, _ = "FAIL", (failed := failed + 1)
        lines.append(f"  [{mark:^5}] {case.id:<24} {case.category}")
        for p in problems:
            lines.append(f"          - {p}")
        if case.xfail and problems:
            lines.append(f"          (known gap: {case.xfail})")
    total = len(rows)
    header = (
        f"\nOrchestrator routing eval: {passed}/{total} passed"
        + (f", {xfailed} known gaps" if xfailed else "")
        + (f", {failed} FAILING" if failed else "")
        + "\n"
    )
    return header + "\n".join(lines) + "\n"


def test_routing_suite():
    rows = _run()
    report = _summary(rows)
    print(report)
    hard_failures = [c.id for c, _, probs in rows if probs and not c.xfail]
    assert not hard_failures, report


if __name__ == "__main__":
    _rows = _run()
    print(_summary(_rows))
    _hard = [c.id for c, _, probs in _rows if probs and not c.xfail]
    sys.exit(1 if _hard else 0)
