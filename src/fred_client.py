"""
Thin wrapper around the FRED API with an in-memory idempotency cache.

Kept deliberately simple (dict cache, no eviction) — the README notes
swapping this for SQLite+TTL as a next step. The point here is to show
the *shape* of caching for idempotent reads, not to ship a production
cache.

Offline mode
------------
Set ``FRED_OFFLINE=1`` and every call is served from a small deterministic
synthetic fixture instead of the network. This is what the evaluation
harness and the test suite use so they run with no API key and no flakiness.
The synthetic numbers are *not* real economic data — they exist so tool
selection, orchestration, and cost accounting can be exercised end to end.
"""

import hashlib
import math
import os
import time
from datetime import date, timedelta

import httpx

import catalog

FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Cache key -> response dict. Since every tool call is validated and
# normalized (uppercase series ID, parsed dates) before it reaches here,
# identical logical requests always produce identical cache keys.
_cache: dict[str, dict] = {}


class FredAPIError(Exception):
    pass


def _offline() -> bool:
    """Serve from the synthetic fixture instead of the network?

    FRED_OFFLINE=1/0 forces it either way; unset means "auto" — offline only
    when there's no FRED_API_KEY, so a fresh clone works with zero config and
    adding a key switches to live data.
    """
    v = os.environ.get("FRED_OFFLINE", "").strip().lower()
    if v in {"1", "true", "yes"}:
        return True
    if v in {"0", "false", "no"}:
        return False
    return not os.environ.get("FRED_API_KEY")


def _offline_latency() -> float:
    """Optional simulated per-call latency for offline mode, in seconds.

    Set FRED_OFFLINE_LATENCY_MS to make the synthetic fixture sleep like a real
    network call would — used to demonstrate and benchmark the sequential vs.
    parallel Data Agent difference without hitting the real API.
    """
    try:
        return max(float(os.environ.get("FRED_OFFLINE_LATENCY_MS", "0")), 0.0) / 1000.0
    except ValueError:
        return 0.0


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise FredAPIError("FRED_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


def _cache_key(*parts: str) -> str:
    return "|".join(parts)


# --- Synthetic fixture (offline mode) -------------------------------------
#
# The catalog (src/catalog.py) is the single source of truth for which series
# exist and their shape; the offline branches below just render it.


def _synthetic_value(series_id: str, d: date) -> float:
    s = catalog.CATALOG[series_id]
    base, drift, amp = s.base, s.annual_drift, s.seasonal_amp
    months = (d.year - 2019) * 12 + (d.month - 1)
    seasonal = amp * math.sin(2 * math.pi * (d.month / 12.0))
    # Deterministic per-point jitter, no RNG import needed.
    h = int(hashlib.sha256(f"{series_id}:{d.isoformat()}".encode()).hexdigest(), 16)
    jitter = ((h % 1000) / 1000.0 - 0.5) * amp * 0.5
    return round(base + drift * (months / 12.0) + seasonal + jitter, 3)


def _observation_dates(start: date, end: date, frequency: str):
    """Dates the synthetic fixture emits, honouring the requested frequency —
    so a 10-year daily pull really is ~2,600 points, not 120."""
    if frequency in ("d", "w"):
        step = timedelta(days=1 if frequency == "d" else 7)
        d = start
        while d <= end:
            if frequency == "w" or d.weekday() < 5:  # daily ~ business days
                yield d
            d += step
        return

    months = {"m": range(1, 13), "q": (1, 4, 7, 10), "a": (1,)}[frequency]
    y = start.year
    while y <= end.year:
        for mth in months:
            d = date(y, mth, 1)
            if start <= d <= end:
                yield d
        y += 1


# --- Public API ---------------------------------------------------------


def search_series(search_text: str, limit: int = 5) -> list[dict]:
    key = _cache_key("search", search_text.lower(), str(limit))
    if key in _cache:
        return _cache[key]["results"]

    if _offline():
        time.sleep(_offline_latency())
        results = [
            {
                "series_id": s.id,
                "title": s.title,
                "frequency": s.frequency_short,
                "units": s.units,
            }
            for s in (catalog.CATALOG[sid] for sid in catalog.search(search_text, limit))
        ]
        _cache[key] = {"results": results}
        return results

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

    if _offline():
        time.sleep(_offline_latency())
        if series_id not in catalog.IDS:
            raise FredAPIError(f"No synthetic fixture for series '{series_id}' (offline mode).")
        observations = [
            {"date": d.isoformat(), "value": f"{_synthetic_value(series_id, d):.3f}"}
            for d in _observation_dates(start, end, frequency)
        ]
        _cache[key] = {"observations": observations}
        return observations

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

    if _offline():
        time.sleep(_offline_latency())
        if series_id not in catalog.IDS:
            raise FredAPIError(f"No synthetic fixture for series '{series_id}' (offline mode).")
        s = catalog.CATALOG[series_id]
        meta = {
            "series_id": s.id,
            "title": s.title,
            "units": s.units,
            "frequency": s.frequency,
            "last_updated": "2026-01-15 08:00:00-06",
            "notes": s.notes,
        }
        _cache[key] = {"meta": meta}
        return meta

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
