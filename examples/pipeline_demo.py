"""
Run the phase-1 pipeline (orchestrator → data agent → analysis agent) and
print the full trace: each stage's summary and estimated cost, then the
grounded answer.

    python examples/pipeline_demo.py
    python examples/pipeline_demo.py "Compare CPI and unemployment from 2019 to 2024"

Offline and keyless by default (synthetic FRED fixture).
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("FRED_OFFLINE", "1")

from orchestration import run_query  # noqa: E402

DEFAULT_Q = "How has CPI changed over the last 5 years?"


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_Q
    result = run_query(query)

    print(f"Query: {query}\n")
    for stage in result.trace:
        c = stage.cost
        print(f"[{stage.stage}]")
        print(f"  in : {stage.input_summary}")
        print(f"  out: {stage.output_summary}")
        print(f"  cost: ~{c['input_tokens']}+{c['output_tokens']} tok  ~${c['estimated_usd']:.6f}")
    print(f"\ntotal estimated: ~${result.total_estimated_usd:.6f}")

    if result.error:
        print(f"\nerror: {result.error}")
    print(f"\nAnswer:\n  {result.answer}")


if __name__ == "__main__":
    main()
