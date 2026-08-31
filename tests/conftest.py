"""Shared test setup: run everything offline, hermetic, and deterministic.

`src/` is put on the path by `[tool.pytest.ini_options] pythonpath` in
pyproject.toml — no sys.path juggling here.
"""

import pytest


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_OFFLINE", "1")
    monkeypatch.setenv("AGENT_BACKEND", "stub")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    import audit_log
    import cost_tracker
    import fred_client
    import rate_limit

    fred_client._cache.clear()
    audit_log.reset()
    rate_limit.limiter.reset()
    cost_tracker.reset_budget()
    yield
