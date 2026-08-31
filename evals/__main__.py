"""`python -m evals` — run the suite, print a summary, write evals/REPORT.md."""

import sys
from pathlib import Path

from evals import report, runner  # evals/__init__ puts src/ on the path


def main() -> int:
    suite = runner.run_suite()
    report.print_summary(suite)

    out = Path(__file__).resolve().parent / "REPORT.md"
    out.write_text(report.to_markdown(suite))
    print(f"\nwrote {out}")

    # Non-zero exit if any case regressed, so CI fails loudly.
    failed = [r.id for r in suite.results if not r.passed]
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
