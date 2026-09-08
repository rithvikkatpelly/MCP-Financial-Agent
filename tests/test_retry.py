"""
Retry / partial-failure hardening in orchestration.run_query.

A worker call is retried once (default AGENT_RETRY_ATTEMPTS=2) on a
*transient* error — rate limit, provider error, network blip — and left to
the skip/degrade path on a non-transient one. `PipelineResult.retries`
records where a retry fired.
"""

import tools
from orchestration import _is_transient, run_query

CPI_QUERY = "How has CPI changed over the last 5 years?"


def test_transient_marker_classification():
    assert _is_transient("observations: rate_limited")
    assert _is_transient("news_api_error")
    assert _is_transient("data_agent_exception: boom")
    assert not _is_transient("metadata: validation_error")
    assert not _is_transient("session_budget_exceeded")
    assert not _is_transient(None)


def test_transient_error_is_retried_then_recovers(monkeypatch):
    real = tools.call_tool
    failed = {"once": False}

    def flaky(name, args, **kw):
        if name == "get_series_observations" and not failed["once"]:
            failed["once"] = True
            return {"error": "rate_limited", "detail": "transient"}
        return real(name, args, **kw)

    monkeypatch.setattr(tools, "call_tool", flaky)
    run = run_query(CPI_QUERY)

    assert run.status == "ok"                 # the retry recovered it
    assert run.retries == {"CPIAUCSL": 2}     # exactly one retry, on that series
    assert run.answer.startswith("Data:")
    # the retry shows up in the data_agent trace stage
    data_stage = next(t for t in run.trace if t.stage == "data_agent")
    assert "retried" in data_stage.output_summary


def test_non_transient_error_is_not_retried(monkeypatch):
    real = tools.call_tool
    meta_calls = {"n": 0}

    def counting(name, args, **kw):
        if name == "get_series_metadata":
            meta_calls["n"] += 1
            return {"error": "validation_error", "detail": "nope"}
        return real(name, args, **kw)

    monkeypatch.setattr(tools, "call_tool", counting)
    run = run_query(CPI_QUERY)

    assert meta_calls["n"] == 1               # called once, not retried
    assert run.retries == {}
    assert run.status in {"failed", "partial"}


def test_retry_attempts_are_configurable(monkeypatch):
    # config is read at call time, not import time — no module reload needed.
    monkeypatch.setenv("AGENT_RETRY_ATTEMPTS", "3")

    real = tools.call_tool
    fails = {"n": 0}

    def always_transient(name, args, **kw):
        if name == "get_series_observations":
            fails["n"] += 1
            return {"error": "fred_api_error", "detail": "down"}
        return real(name, args, **kw)

    monkeypatch.setattr(tools, "call_tool", always_transient)
    run = run_query(CPI_QUERY)

    assert run.retries == {"CPIAUCSL": 3}     # tried the max
    assert fails["n"] == 3                    # obs attempted 3 times
    assert run.status == "failed"             # still failed after all retries
