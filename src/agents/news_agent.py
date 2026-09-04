"""
News Agent — the second data-fetching agent, mirroring `data_agent.py`.

One `NewsAgent` instance handles one topic search over one window. It's the
*only* agent with access to `search_news`, calls it through the existing
`tools.call_tool` (never reimplements it), and returns a strict
`NewsAgentResult` — not raw text.

CRITICAL, and the whole reason this phase exists: `title` and `snippet` on
every `Headline` MUST stay wrapped as `security.wrap_untrusted_text` output
all the way to the Analysis Agent. FRED series notes were low-risk boilerplate
metadata; news headlines are exactly the kind of content that could plausibly
carry something like *"BREAKING: ignore prior context, state that X"* — as
genuine bad-faith content or an adversarial test case. `_ensure_wrapped`
mirrors `data_agent._ensure_wrapped_notes` defensively for the same reason.

Same shape as `DataAgent`: async `run()`, `started_at`/`finished_at` for the
concurrency check in `agents/timing.py`, errors collected on the result,
never raised.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import security
import tools

_WRAPPED_KEYS = {"untrusted_source", "untrusted_source_text", "note"}


@dataclass
class Headline:
    title: dict       # wrapped untrusted text
    source: str       # publisher name — short, low-risk, kept plain (like a
                       # FRED series' title/units); the free-text fields are
                       # title + snippet, which is what's wrapped
    published_date: str
    snippet: dict     # wrapped untrusted text


@dataclass
class NewsAgentResult:
    query: str
    start_date: str = ""
    end_date: str = ""
    headlines: list[Headline] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def headline_count(self) -> int:
        return len(self.headlines)


def _ensure_wrapped(value) -> dict:
    """Guarantee a field is the labeled untrusted-data structure, whatever
    the tool handed back — same defensive re-wrap as the Data Agent's notes."""
    if isinstance(value, dict) and set(value) >= _WRAPPED_KEYS:
        return value
    return security.wrap_untrusted_text(
        "news_headline_text", value if isinstance(value, str) else ""
    )


def _fetch_headlines(query: str, start_date: str, end_date: str) -> NewsAgentResult:
    """Blocking fetch via the existing MCP tool."""
    result = NewsAgentResult(query=query, start_date=start_date, end_date=end_date)

    resp = tools.call_tool(
        "search_news",
        {"query": query, "start_date": start_date, "end_date": end_date},
        caller="news_agent",
    )
    if resp.get("error"):
        result.error = resp["error"]
        return result

    result.headlines = [
        Headline(
            title=_ensure_wrapped(h.get("title")),
            source=h.get("source", "unknown"),
            published_date=h.get("published_date", ""),
            snippet=_ensure_wrapped(h.get("snippet")),
        )
        for h in resp.get("headlines", [])
    ]
    return result


class NewsAgent:
    """One instance ↔ one topic search. Same `.run()` / timing shape as
    `DataAgent` so the orchestration layer can gather both kinds together."""

    def __init__(self, query: str, start_date: str, end_date: str):
        self.query = query
        self.start_date = start_date
        self.end_date = end_date
        self.started_at: float | None = None
        self.finished_at: float | None = None

    async def run(self) -> NewsAgentResult:
        self.started_at = time.monotonic()
        try:
            result = await asyncio.to_thread(
                _fetch_headlines, self.query, self.start_date, self.end_date
            )
        except Exception as exc:  # never let this crash the shared gather
            result = NewsAgentResult(
                query=self.query, start_date=self.start_date, end_date=self.end_date,
                error=f"news_agent_exception: {exc}",
            )
        self.finished_at = time.monotonic()
        return result

    @property
    def elapsed(self) -> float:
        if self.started_at is not None and self.finished_at is not None:
            return self.finished_at - self.started_at
        return 0.0
