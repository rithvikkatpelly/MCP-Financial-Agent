"""Token-bucket rate limiter behaviour."""

from rate_limit import RateLimiter, guard


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

    rl.check("k"); rl.check("k")
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
    monkeypatch.setenv("TOOL_RATE_LIMIT_PER_MIN", "60")
    monkeypatch.setenv("TOOL_RATE_LIMIT_BURST", "1")
    import importlib

    import rate_limit
    importlib.reload(rate_limit)

    assert rate_limit.guard("client", "search_series") is None
    rejected = rate_limit.guard("client", "search_series")
    assert rejected["error"] == "rate_limited"
    assert "retry_after_seconds" in rejected

    importlib.reload(rate_limit)  # restore module-level limiter for other tests
