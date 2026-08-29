"""
Run one analytical question through the multi-agent system and print the
whole flow — delegations, tool calls, grounding set, risk signal, cost.

    python examples/demo.py
    python examples/demo.py "Compare core PCE and the fed funds rate since 2021."

Offline by default (synthetic FRED data, deterministic stub planner). Set
AGENT_BACKEND=anthropic and FRED_OFFLINE=0 with keys in .env for the real run.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("FRED_OFFLINE", "1")

from agents import Trace  # noqa: E402
from agents.supervisor import Supervisor  # noqa: E402

DEFAULT_Q = (
    "Compare CPI and unemployment over the last 5 years and explain whether "
    "the relationship changed after 2020."
)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_Q
    trace = Trace()
    Supervisor(trace).run(query)

    print(f"User:\n  {query}\n")
    print("Supervisor delegated to:")
    for d in trace.delegations:
        print(f"  → {d.to}")
    print("\nTool calls:")
    for c in trace.tool_calls:
        if c.name not in trace.LEAF_TOOLS:
            continue
        args = {k: v for k, v in c.arguments.items() if k != "frequency"}
        print(f"  [{c.agent}] {c.name}({args})  ok={c.ok}")
    print(f"\nSeries grounded on: {', '.join(trace.series_used)}")
    print(f"Risk signal: {trace.risk_signal}")
    d = trace.to_dict()
    print(
        f"Tokens: {d['input_tokens']} in / {d['output_tokens']} out   "
        f"Wall time: {d['elapsed_ms']} ms   "
        f"Backend: {os.environ.get('AGENT_BACKEND', 'stub')}"
    )
    print("\n--- Final report ---")
    print(trace.final_report)


if __name__ == "__main__":
    main()
