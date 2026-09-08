"""
TTL cache — an idempotency cache with a per-entry expiry, backed by sqlite.

Why sqlite and not the plain `dict` the FRED / news clients used before: FRED
observations and metadata for a *closed* date window don't change, and news
results for a past window are stable enough. Persisting them (set `CACHE_PATH`)
turns a cold start into a warm one and shares the cache across worker
processes. The TTL bounds staleness for the one thing that does move — "recent"
news.

Drop-in for the dict it replaces — same `key in cache`, `cache[key]`,
`cache[key] = value`, `cache.clear()`, `for k in cache`. Values are JSON
round-tripped, so store plain dicts / lists (which both clients already do).

`CACHE_PATH` defaults to `:memory:` — a per-process in-memory sqlite db, same
API, nothing on disk. That's what the test suite and a fresh clone get with
zero config; a deployment points it at a file.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from typing import Any


class TTLCache:
    def __init__(self, *, ttl_seconds: float, path: str | None = None, clock=time.time):
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self.path = path or os.environ.get("CACHE_PATH") or ":memory:"
        # check_same_thread=False + the lock: the pipeline fetches run in
        # asyncio.to_thread worker threads; every DB op below is serialized.
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)"
        )
        self._db.commit()

    def _live_value(self, key: str) -> str | None:
        now = self._clock()
        with self._lock:
            row = self._db.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            value, expires_at = row
            if expires_at <= now:  # lazily evict on read
                self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._db.commit()
                return None
            return value

    def __contains__(self, key: str) -> bool:
        return self._live_value(key) is not None

    def __getitem__(self, key: str) -> Any:
        value = self._live_value(key)
        if value is None:
            raise KeyError(key)
        return json.loads(value)

    def get(self, key: str, default: Any = None) -> Any:
        value = self._live_value(key)
        return default if value is None else json.loads(value)

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, default=str), self._clock() + self._ttl),
            )
            self._db.commit()

    def __iter__(self) -> Iterator[str]:
        now = self._clock()
        with self._lock:
            rows = self._db.execute(
                "SELECT key FROM cache WHERE expires_at > ?", (now,)
            ).fetchall()
        return iter([r[0] for r in rows])

    def __len__(self) -> int:
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at > ?", (self._clock(),)
            ).fetchone()[0]

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM cache")
            self._db.commit()
