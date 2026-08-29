"""
Multi-agent orchestration layer for the econ-data project.

A supervisor decomposes an analytical question and delegates to four narrow
specialist agents, each of which runs its own tool-use loop over the shared
FRED tools in `tools.py`:

    User → Supervisor ┬─ Economic Data Agent   (resolves series, fetches data)
                      ├─ Research Agent         (source notes / framing)
                      ├─ Risk Agent             (reads indicators, scores risk)
                      └─ Report Agent           (grounded write-up + evidence)

Every agent talks to a `Model` (agents/model.py). `AnthropicModel` calls
Claude; `StubModel` is a deterministic offline planner so the evaluation
harness and tests run with no API key. Same loop code either way.
"""

import sys
from pathlib import Path

# Let `import tools`, `import fred_client`, ... resolve from src/ no matter
# who imported this package.
_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agents.supervisor import Supervisor, run  # noqa: E402,F401
from agents.trace import Trace  # noqa: E402,F401

__all__ = ["Supervisor", "run", "Trace"]
