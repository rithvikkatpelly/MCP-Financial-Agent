"""
Run the multi-agent pipeline (orchestrator → data agent(s) → analysis agent)
and print the full trace: each stage's input, output, estimated cost, and wall
time, then the per-agent cost table and the grounded answer.

    python examples/pipeline_demo.py
    python examples/pipeline_demo.py "Compare CPI, unemployment, and interest rates over 5 years"
    python examples/pipeline_demo.py --broken "Compare CPI and unemployment over the last 5 years"
    python examples/pipeline_demo.py --sequential "..."

--broken injects one invalid series ID to show partial-failure handling.
Offline and keyless by default (synthetic FRED fixture).
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("FRED_OFFLINE", "1")

from agents.orchestrator import plan_for_series, plan_query  # noqa: E402
from orchestration import run_query  # noqa: E402

DEFAULT_Q = "How has CPI changed over the last 5 years?"


def main() -> None:
    args = sys.argv[1:]
    parallel = "--sequential" not in args
    broken = "--broken" in args
    args = [a for a in args if not a.startswith("--")]
    query = args[0] if args else DEFAULT_Q

    plan = None
    if broken:
        base = plan_query(query)
        ids = [f.series_id for f in base.fetches] + ["FAKESERIES"]
        plan = plan_for_series(query, ids)

    result = run_query(query, plan=plan, parallel=parallel)

    print(f"Query: {query}")
    print(f"Plan:  {result.plan.mode} — {result.plan.rationale}")
    print(f"Mode:  {'parallel' if parallel else 'sequential'} data agents\n")

    for stage in result.trace:
        c = stage.cost
        print(f"[{stage.stage}]  ({stage.calls} call{'s' if stage.calls != 1 else ''}, "
              f"{stage.wall_seconds * 1000:.0f} ms)")
        print(f"  in : {stage.input_summary}")
        print(f"  out: {stage.output_summary}")
        print(f"  cost: ~{c['input_tokens']}+{c['output_tokens']} tok  ~${c['estimated_usd']:.6f}")

    cost = result.cost
    print("\nper-agent cost:")
    for row in cost["per_agent"]:
        print(f"  {row['stage']:<15} {row['calls']}x  "
              f"~{row['input_tokens']}+{row['output_tokens']} tok  ~${row['estimated_usd']:.6f}")
    t = cost["total"]
    print(f"  {'RUN TOTAL':<15}     ~{t['input_tokens']}+{t['output_tokens']} tok  "
          f"~${t['estimated_usd']:.6f}")

    print(f"\nstatus: {result.status}   wall clock: {result.wall_seconds * 1000:.0f} ms")
    if result.failures:
        for f in result.failures:
            print(f"  failed: {f['series_id']} — {f['reason']}")

    print(f"\nAnswer:\n  {result.answer}")


if __name__ == "__main__":
    main()
