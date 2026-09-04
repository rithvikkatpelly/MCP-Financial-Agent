"""The offline headline fixture and its idempotency cache — same shape as
test_fred_client.py, because news_client.py is deliberately the same shape
as fred_client.py."""

import news_client


def test_topic_matching_is_deterministic():
    a = news_client.search_headlines("inflation", "2026-08-01", "2026-09-01")
    news_client._cache.clear()
    b = news_client.search_headlines("inflation", "2026-08-01", "2026-09-01")
    assert a == b
    assert a  # never empty offline


def test_result_is_capped_at_max_headlines():
    results = news_client.search_headlines("inflation", "2026-08-01", "2026-09-01", limit=100)
    assert len(results) <= news_client.MAX_HEADLINES


def test_different_topics_return_different_headlines():
    inflation = news_client.search_headlines("inflation prices", "2026-08-01", "2026-09-01")
    jobs = news_client.search_headlines("jobs labor market", "2026-08-01", "2026-09-01")
    assert {h["title"] for h in inflation} != {h["title"] for h in jobs}


def test_second_identical_call_is_served_from_cache(monkeypatch):
    news_client._cache.clear()
    calls = {"n": 0}
    real = news_client.search_headlines

    def counting(query, start_date, end_date, limit=10):
        key = news_client._cache_key(
            "news", query.lower().strip(), start_date, end_date, str(limit)
        )
        if key not in news_client._cache:
            calls["n"] += 1
        return real(query, start_date, end_date, limit)

    monkeypatch.setattr(news_client, "search_headlines", counting)
    args = ("inflation", "2026-08-01", "2026-09-01")
    news_client.search_headlines(*args)
    news_client.search_headlines(*args)
    news_client.search_headlines(*args)
    assert calls["n"] == 1


def test_every_headline_has_the_required_fields():
    for h in news_client.search_headlines("federal reserve", "2026-08-01", "2026-09-01"):
        assert set(h) >= {"title", "source", "published_date", "snippet"}
        assert "body" not in h and "content" not in h  # never the full article
