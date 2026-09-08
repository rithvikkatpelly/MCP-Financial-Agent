"""
Thin wrapper around a news-headlines API — the second data source, alongside
FRED. Deliberately mirrors `fred_client.py`: same in-memory idempotency
cache, same `_offline()` auto-switch, same "raise a typed error, let the
caller turn it into a structured dict" pattern.

Why NewsAPI.org: free "Developer" tier (100 requests/day, articles from
roughly the last month, `/v2/everything` endpoint), no card required, and a
plain JSON response shape that needs no SDK. The month-old history cap and
100/day ceiling are why `search_news` bounds its own date range and result
count rather than trusting the caller — see README "Why NewsAPI.org".

Offline mode
------------
Same auto-switch as FRED: `NEWS_OFFLINE=1`/`0` forces it; unset means
"offline only when NEWS_API_KEY is missing". Offline calls are served from a
small deterministic synthetic headline bank, topic-matched the same way
`catalog.search` ranks FRED series — a keyword-overlap score against a fixed
vocabulary, not a live index. The synthetic headlines are not real news; they
exist so cross-source routing and analysis can be exercised end to end.
"""

from __future__ import annotations

import os
import time

import httpx

from cache import TTLCache

NEWS_API_URL = "https://newsapi.org/v2/everything"
MAX_HEADLINES = 10

# Same idempotency shape as fred_client._cache — sqlite-backed with a TTL
# (src/cache.py). Shorter default than FRED: "recent" headlines for an
# open-ended window do shift. Set CACHE_PATH to persist across restarts.
_cache = TTLCache(ttl_seconds=float(os.environ.get("NEWS_CACHE_TTL_SECONDS", "3600")))


class NewsAPIError(Exception):
    pass


def _offline() -> bool:
    """Same "auto" contract as fred_client._offline(): forced by NEWS_OFFLINE,
    otherwise offline only when there's no NEWS_API_KEY."""
    v = os.environ.get("NEWS_OFFLINE", "").strip().lower()
    if v in {"1", "true", "yes"}:
        return True
    if v in {"0", "false", "no"}:
        return False
    return not os.environ.get("NEWS_API_KEY")


def _api_key() -> str:
    key = os.environ.get("NEWS_API_KEY")
    if not key:
        raise NewsAPIError("NEWS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


def _offline_latency() -> float:
    """Same simulated-latency knob as fred_client._offline_latency(), for the
    cross-source concurrency demo/benchmark: NEWS_OFFLINE_LATENCY_MS makes the
    offline fixture sleep like a real network call would."""
    try:
        return max(float(os.environ.get("NEWS_OFFLINE_LATENCY_MS", "0")), 0.0) / 1000.0
    except ValueError:
        return 0.0


def _cache_key(*parts: str) -> str:
    return "|".join(parts)


# --- synthetic offline fixture -------------------------------------------
# Small, fixed, and clearly synthetic (see the dates and the last entry).

def _h(title: str, source: str, published_date: str, snippet: str) -> dict:
    return {"title": title, "source": source, "published_date": published_date, "snippet": snippet}


_HEADLINE_BANK: dict[str, list[dict]] = {
    "inflation": [
        _h("Inflation Cools as Energy Prices Ease", "Reuters", "2026-08-20",
           "Falling gasoline prices helped headline inflation ease last month, "
           "though housing costs stayed elevated."),
        _h("Housing Costs Keep Core Inflation Sticky, Economists Say", "Bloomberg", "2026-08-18",
           "Shelter costs continue to drive the bulk of core CPI gains even as "
           "goods prices flatten out."),
        _h("Fed Officials Split on Whether Disinflation Will Last", "AP", "2026-08-15",
           "Policymakers disagree on whether recent progress on prices reflects "
           "a durable trend or temporary factors like energy costs."),
    ],
    "fed": [
        _h("Fed Holds Rates Steady, Signals Patience on Cuts", "Reuters", "2026-08-21",
           "The central bank left its policy rate unchanged and gave no firm "
           "timeline for further cuts."),
        _h("What the Fed's Statement Tells Us About the Path Ahead", "CNBC", "2026-08-21",
           "Analysts parsed the post-meeting statement for clues on the next move."),
        _h("Fed Watchers Eye Labor Market Data Ahead of Next Meeting", "MarketWatch", "2026-08-17",
           "Upcoming jobs figures could sway the committee's next rate decision."),
    ],
    "jobs": [
        _h("Hiring Slows but Layoffs Remain Low", "Associated Press", "2026-08-19",
           "The labor market is cooling gradually rather than cracking, economists say."),
        _h("Wage Growth Moderates as Job Market Balances Out", "Bloomberg", "2026-08-14",
           "Pay gains slowed for a third straight month as labor supply and demand converge."),
    ],
    "gdp": [
        _h("Economic Growth Beats Expectations Last Quarter", "Reuters", "2026-08-10",
           "Consumer spending and business investment powered a stronger-than-forecast reading."),
    ],
}
_TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inflation", ("inflation", "prices", "cpi", "cost of living")),
    ("fed", ("fed", "federal reserve", "interest rate", "rate cut", "rate hike", "central bank")),
    ("jobs", ("job", "jobs", "labor market", "unemployment", "hiring", "layoffs")),
    ("gdp", ("gdp", "economic growth", "economy")),
)


def _offline_headlines(query: str, limit: int) -> list[dict]:
    q = query.lower()
    scored = [
        (sum(1 for kw in keywords if kw in q), topic)
        for topic, keywords in _TOPIC_KEYWORDS
    ]
    scored.sort(key=lambda p: -p[0])
    best_score, best_topic = scored[0]
    topic = best_topic if best_score > 0 else "inflation"  # always return *something*
    return list(_HEADLINE_BANK.get(topic, []))[:limit]


# --- public API -----------------------------------------------------------


def search_headlines(query: str, start_date: str, end_date: str, limit: int = 10) -> list[dict]:
    """Up to `limit` (capped at MAX_HEADLINES) headlines for `query` between
    start_date and end_date. Each item: title, source, published_date,
    snippet — never the full article body."""
    limit = min(max(int(limit), 1), MAX_HEADLINES)
    key = _cache_key("news", query.lower().strip(), start_date, end_date, str(limit))
    if key in _cache:
        return _cache[key]

    if _offline():
        time.sleep(_offline_latency())
        results = _offline_headlines(query, limit)
        _cache[key] = results
        return results

    resp = httpx.get(
        NEWS_API_URL,
        params={
            "q": query,
            "from": start_date,
            "to": end_date,
            "sortBy": "relevancy",
            "pageSize": limit,
            "language": "en",
            "apiKey": _api_key(),
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "ok":
        raise NewsAPIError(data.get("message", "NewsAPI request failed."))

    results = [
        {
            "title": a.get("title") or "",
            "source": (a.get("source") or {}).get("name") or "unknown",
            "published_date": (a.get("publishedAt") or "")[:10],
            "snippet": a.get("description") or "",
        }
        for a in data.get("articles", [])[:limit]
    ]
    _cache[key] = results
    return results
