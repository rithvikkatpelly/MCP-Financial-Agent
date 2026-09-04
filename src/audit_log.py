"""
Append-only security audit log.

Every security-relevant event — tool invocation, validation rejection,
rate-limit hit, untrusted-content wrapping — is written as one JSON object
per line to `audit.log` (git-ignored). Separate from `usage.log`, which is
cost/telemetry: this one is for "what was asked of the system and what did
it refuse".

Design notes:
  * Best-effort: a logging failure never blocks or breaks a tool call.
  * Secret-safe: every string field is run through `security.redact_secrets`
    with the live FRED key before it is written.
  * Arguments are summarized, not dumped verbatim — enough to reconstruct
    intent, not enough to make the log a data-exfiltration target.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import security

DEFAULT_PATH = Path(__file__).parent.parent / "audit.log"

# Small in-memory ring so tests (and a future /audit resource) can read recent
# events without touching disk.
_RECENT: list[dict] = []
_RECENT_MAX = 200


def _path() -> Path:
    return Path(os.environ.get("AUDIT_LOG_PATH", str(DEFAULT_PATH)))


def _secrets() -> list[str]:
    return [
        v for v in (os.environ.get("FRED_API_KEY"), os.environ.get("NEWS_API_KEY")) if v
    ]


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return security.redact_secrets(value, _secrets())
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _summarize_args(arguments: dict) -> dict:
    out = {}
    for k, v in arguments.items():
        if isinstance(v, str) and len(v) > 80:
            out[k] = v[:77] + "..."
        elif isinstance(v, list):
            out[k] = v[:8]
        else:
            out[k] = v
    return out


def record(event: str, **fields: Any) -> dict:
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event}
    if "arguments" in fields:
        fields["arguments"] = _summarize_args(fields["arguments"])
    entry.update(_redact(fields))

    _RECENT.append(entry)
    del _RECENT[:-_RECENT_MAX]

    try:
        with open(_path(), "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass  # best-effort
    return entry


def recent(n: int = 20) -> list[dict]:
    return _RECENT[-n:]


def reset() -> None:
    _RECENT.clear()
