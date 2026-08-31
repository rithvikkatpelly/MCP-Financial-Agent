"""Audit log records events, redacts secrets, and never raises."""

import json

import audit_log
import tools


def test_tool_call_is_recorded():
    tools.call_tool("get_series_metadata", {"series_id": "UNRATE"}, caller="test")
    events = audit_log.recent()
    assert events[-1]["event"] == "tool_call"
    assert events[-1]["tool"] == "get_series_metadata"
    assert events[-1]["outcome"] == "ok"
    assert events[-1]["caller"] == "test"


def test_validation_failure_outcome_is_logged():
    tools.call_tool("get_series_metadata", {"series_id": "../etc/passwd"}, caller="test")
    assert audit_log.recent()[-1]["outcome"] == "validation_error"


def test_secret_is_redacted(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "supersecretkey123")
    entry = audit_log.record("custom", detail="leaked supersecretkey123 in text")
    assert "supersecretkey123" not in json.dumps(entry)
    assert "[REDACTED]" in entry["detail"]


def test_long_args_are_summarized():
    entry = audit_log.record("tool_call", arguments={"search_text": "x" * 500})
    assert len(entry["arguments"]["search_text"]) < 100


def test_logging_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_PATH", "/nonexistent-dir/audit.log")
    # Should swallow the OSError and still return the entry.
    entry = audit_log.record("tool_call", tool="search_series")
    assert entry["event"] == "tool_call"


def test_log_file_is_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "a.log"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
    audit_log.record("tool_call", tool="search_series")
    audit_log.record("rate_limited", tool="search_series")
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["event"] for line in lines)
