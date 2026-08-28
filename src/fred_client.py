"""
Thin wrapper around the FRED API with an in-memory idempotency cache.

Kept deliberately simple (dict cache, no eviction) — the README notes
swapping this for SQLite+TTL as a next step. The point here is to show
the *shape* of caching for idempotent reads, not to ship a production
cache.
"""

import os
from datetime import date

import httpx

FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Cache key -> response dict. Since every tool call is validated and
# normalized (uppercase series ID, parsed dates) before it reaches here,
# identical logical requests always produce identical cache keys.
_cache: dict[str, dict] = {}


class FredAPIError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise FredAPIError("FRED_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


def _cache_key(*parts: str) -> str:
    return "|".join(parts)


def search_series(search_text: str, limit: int = 5) -> list[dict]:
    key = _cache_key("search", search_text.lower(), str(limit))
    if key in _cache:
        return _cache[key]["results"]

    resp = httpx.get(
        f"{FRED_BASE_URL}/series/search",
        params={
            "search_text": search_text,
            "api_key": _api_key(),
            "file_type": "json",
            "limit": limit,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = [
        {
            "series_id": s["id"],
            "title": s["title"],
            "frequency": s["frequency_short"],
            "units": s["units"],
        }
        for s in data.get("seriess", [])
    ]
    _cache[key] = {"results": results}
    return results


def get_observations(series_id: str, start: date, end: date, frequency: str) -> list[dict]:
    key = _cache_key("obs", series_id, str(start), str(end), frequency)
    if key in _cache:
        return _cache[key]["observations"]

    resp = httpx.get(
        f"{FRED_BASE_URL}/series/observations",
        params={
            "series_id": series_id,
            "api_key": _api_key(),
            "file_type": "json",
            "observation_start": str(start),
            "observation_end": str(end),
            "frequency": frequency,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    observations = [
        {"date": o["date"], "value": o["value"]}
        for o in data.get("observations", [])
        if o["value"] != "."  # FRED uses "." for missing values
    ]
    _cache[key] = {"observations": observations}
    return observations


def get_series_metadata(series_id: str) -> dict:
    key = _cache_key("meta", series_id)
    if key in _cache:
        return _cache[key]["meta"]

    resp = httpx.get(
        f"{FRED_BASE_URL}/series",
        params={"series_id": series_id, "api_key": _api_key(), "file_type": "json"},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    series_list = data.get("seriess", [])
    if not series_list:
        raise FredAPIError(f"No metadata found for series '{series_id}'.")
    s = series_list[0]
    meta = {
        "series_id": s["id"],
        "title": s["title"],
        "units": s["units"],
        "frequency": s["frequency"],
        "last_updated": s["last_updated"],
        "notes": s.get("notes", ""),
    }
    _cache[key] = {"meta": meta}
    return meta
