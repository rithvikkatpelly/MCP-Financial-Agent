"""
Lightweight token/cost estimation and a per-session budget guardrail.

Not a precise tokenizer match — the goal is a consistent, logged estimate
so tool results can be shaped *before* they're returned, and so the
caching/truncation choices in server.py can be justified with real numbers
instead of a hand-wavy claim.
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# Rough heuristic: ~4 characters per token for English/JSON-ish text.
# Good enough for a budget guardrail; not a substitute for the real
# tokenizer if this were going to production.
_CHARS_PER_TOKEN = 4

LOG_PATH = Path(__file__).parent.parent / "usage.log"


def estimate_tokens(payload: str) -> int:
    return max(1, len(payload) // _CHARS_PER_TOKEN)


@dataclass
class SessionBudget:
    limit_tokens: int = int(os.environ.get("SESSION_TOKEN_BUDGET", "50000"))
    used_tokens: int = field(default=0)

    def would_exceed(self, additional_tokens: int) -> bool:
        return (self.used_tokens + additional_tokens) > self.limit_tokens

    def record(self, tool_name: str, tokens: int, note: str = "") -> None:
        self.used_tokens += tokens
        self._log(tool_name, tokens, note)

    def remaining(self) -> int:
        return max(0, self.limit_tokens - self.used_tokens)

    def _log(self, tool_name: str, tokens: int, note: str) -> None:
        line = (
            f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{tool_name}\t"
            f"tokens={tokens}\trunning_total={self.used_tokens}\t{note}\n"
        )
        try:
            with open(LOG_PATH, "a") as f:
                f.write(line)
        except OSError:
            pass  # logging is best-effort, never block a tool call on it


# One shared budget per server process. In a multi-session deployment this
# would be keyed by session ID instead of being a module-level singleton.
budget = SessionBudget()


def reset_budget() -> None:
    """Start a fresh session budget. The evaluation harness calls this between
    cases so one case's spend can't push the next over the limit; tests use it
    for isolation."""
    global budget
    budget = SessionBudget()


def guard_or_shrink(tool_name: str, payload: str, shrink_fn=None) -> tuple[str, dict]:
    """
    Check a would-be tool result against the session budget before
    returning it. If it fits, record the cost and return it as-is.
    If it doesn't fit and a shrink_fn was provided, try shrinking once
    (e.g. drop to monthly granularity, or truncate a series) and re-check.
    If it still doesn't fit, return a structured warning instead of the
    raw payload so the model can narrow the request.
    """
    tokens = estimate_tokens(payload)

    if not budget.would_exceed(tokens):
        budget.record(tool_name, tokens)
        return payload, {"estimated_tokens": tokens, "budget_remaining": budget.remaining()}

    if shrink_fn is not None:
        shrunk = shrink_fn(payload)
        shrunk_tokens = estimate_tokens(shrunk)
        if not budget.would_exceed(shrunk_tokens):
            budget.record(tool_name, shrunk_tokens, note="shrunk")
            return shrunk, {
                "estimated_tokens": shrunk_tokens,
                "budget_remaining": budget.remaining(),
                "note": "Result was shrunk to fit the session token budget.",
            }

    return "", {
        "error": "session_budget_exceeded",
        "estimated_tokens": tokens,
        "budget_remaining": budget.remaining(),
        "suggestion": "Narrow the date range, reduce the number of series, "
                       "or start a new session.",
    }
