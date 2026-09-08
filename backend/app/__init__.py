"""HTTP interface package.

Importing this package runs two side effects that must happen before any
module under ``src/`` is imported (``app.main`` imports ``tools`` from there):

1. Put the repo's ``src/`` on ``sys.path``. The shared tool logic
   (``tools.py`` → ``fred_client`` + ``cost_tracker`` + ``security``) lives
   there and is imported as-is. This HTTP surface is a second caller of it,
   exactly as ``src/server.py`` is the MCP caller — no code is copied or
   moved, and ``src/server.py`` does not depend on this package.
2. Load ``.env`` and push the relevant settings into ``os.environ``, because
   those ``src/`` modules read ``os.environ`` at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.config import get_settings  # noqa: E402  (sys.path set up just above)

get_settings().apply_to_environ()
