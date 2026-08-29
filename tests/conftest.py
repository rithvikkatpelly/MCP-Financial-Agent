"""Shared test setup: run everything offline, hermetic, and deterministic."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_OFFLINE", "1")
    monkeypatch.setenv("AGENT_BACKEND", "stub")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    import audit_log
    import fred_client
    import rate_limit

    fred_client._cache.clear()
    audit_log.reset()
    rate_limit.limiter.reset()
    yield
