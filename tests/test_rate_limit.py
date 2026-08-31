"""Token-bucket rate limiter behaviour."""

import rate_limit
from rate_limit import RateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def test_burst_then_block():
    clock = FakeClock()
    rl = RateLimiter(capacity=3, refill_per_sec=1.0, clock=clock)

    assert [rl.check("k")[0] for _ in range(3)] == [True, True, True]
    allowed, retry_after = rl.check("k")
    assert allowed is False
    assert retry_after > 0


def test_refill_over_time():
    clock = FakeClock()
    rl = RateLimiter(capacity=2, refill_per_sec=1.0, clock=clock)

    rl.check("k")
    rl.check("k")
    assert rl.check("k")[0] is False

    clock.advance(1.0)  # one token back
    assert rl.check("k")[0] is True
    assert rl.check("k")[0] is False


def test_keys_are_independent():
    clock = FakeClock()
    rl = RateLimiter(capacity=1, refill_per_sec=1.0, clock=clock)

    assert rl.check("a")[0] is True
    assert rl.check("b")[0] is True   # different key, own bucket
    assert rl.check("a")[0] is False


def test_guard_returns_structured_error(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(rate_limit, "limiter", RateLimiter(1, 1.0, clock=clock))

    assert rate_limit.guard("client", "search_series") is None
    rejected = rate_limit.guard("client", "search_series")
    assert rejected["error"] == "rate_limited"
    assert rejected["retry_after_seconds"] > 0


def test_guard_keys_client_and_tool_separately(monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", RateLimiter(1, 1.0, clock=FakeClock()))
    assert rate_limit.guard("a", "search_series") is None
    assert rate_limit.guard("a", "compare_series") is None  # different tool
    assert rate_limit.guard("b", "search_series") is None   # different client
    assert rate_limit.guard("a", "search_series") is not None
