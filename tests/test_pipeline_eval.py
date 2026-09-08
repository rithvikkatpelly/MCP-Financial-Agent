"""
Pipeline-level eval.

Sibling to `test_routing.py`: that one runs `orchestrator.plan_query` only and
checks the *plan*; this one runs the *whole* pipeline through
`orchestration.run_query` (offline, deterministic) and checks execution —
which workers ran, whether a retry fired, whether the run degraded
gracefully, and whether the answer is what the routing implies.

Prints a full pass/fail table (not first-failure), then asserts every
non-`xfail` case passed.

    pytest tests/test_pipeline_eval.py -s      # see the table
    python tests/test_pipeline_eval.py         # same table, standalone
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_cases  # noqa: E402

from agents.orchestrator import plan_for_series  # noqa: E402
from orchestration import run_query  # noqa: E402


def _run() -> list[tuple[eval_cases.PipelineCase, object, list[str]]]:
    rows = []
    for case in eval_cases.PIPELINE_CASES:
        if case.series is not None:
            plan = plan_for_series(case.query, case.series)
            result = run_query(case.query, plan=plan)
        else:
            result = run_query(case.query)
        rows.append((case, result, case.check(result)))
    return rows


def _summary(rows) -> str:
    lines = []
    passed = xfailed = failed = 0
    for case, _result, problems in rows:
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
        f"\nPipeline eval: {passed}/{total} passed"
        + (f", {xfailed} known gaps" if xfailed else "")
        + (f", {failed} FAILING" if failed else "")
        + "\n"
    )
    return header + "\n".join(lines) + "\n"


def test_pipeline_suite():
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
