"""
TTLCache (src/cache.py) — the sqlite-backed idempotency cache the FRED and
news clients use. The hit/miss/iterate behaviour is exercised through those
clients in test_fred_client / test_news_client; this file covers the TTL and
persistence that the plain dict didn't have.
"""

import pytest

from cache import TTLCache


class FakeClock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def test_entry_expires_after_its_ttl():
    clock = FakeClock()
    c = TTLCache(ttl_seconds=60, clock=clock)
    c["k"] = {"v": 1}

    assert "k" in c and c["k"] == {"v": 1}
    clock.advance(59)
    assert "k" in c                      # not yet
    clock.advance(2)
    assert "k" not in c                  # expired
    with pytest.raises(KeyError):
        _ = c["k"]
    assert c.get("k", "default") == "default"


def test_expired_entry_is_evicted_on_read_not_left_to_rot():
    clock = FakeClock()
    c = TTLCache(ttl_seconds=10, clock=clock)
    c["a"] = 1
    c["b"] = 2
    clock.advance(11)
    c["c"] = 3  # fresh
    assert list(c) == ["c"]              # iterating skips the expired ones
    assert len(c) == 1
    _ = "a" in c                         # touching an expired key drops it
    clock.advance(-11)                   # even if the clock were to go back
    assert "a" not in c


def test_set_refreshes_the_ttl():
    clock = FakeClock()
    c = TTLCache(ttl_seconds=30, clock=clock)
    c["k"] = 1
    clock.advance(20)
    c["k"] = 2                           # re-set → new 30s window from now
    clock.advance(20)
    assert c["k"] == 2                   # would have expired on the old window


def test_values_json_round_trip_through_sqlite():
    c = TTLCache(ttl_seconds=999)
    payload = {"observations": [{"date": "2020-01-01", "value": "1.5"}], "n": 1}
    c["obs|X"] = payload
    assert c["obs|X"] == payload


def test_survives_a_new_connection_to_the_same_file(tmp_path):
    db = str(tmp_path / "c.sqlite")
    a = TTLCache(ttl_seconds=999, path=db)
    a["k"] = {"cached": True}

    b = TTLCache(ttl_seconds=999, path=db)   # separate instance, same file
    assert b["k"] == {"cached": True}


def test_clear_empties_it():
    c = TTLCache(ttl_seconds=999)
    c["a"] = 1
    c["b"] = 2
    c.clear()
    assert len(c) == 0 and "a" not in c
