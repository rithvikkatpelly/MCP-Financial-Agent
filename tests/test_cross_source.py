"""
Cross-source routing and concurrency: Data Agent(s) + News Agent.

Complements test_news_injection.py (which focuses on the security property)
with the routing and orchestration properties phase 4 added: the three
example queries route to the right agents, both sources run under one
`asyncio.gather` when both are needed, and a failure in one source doesn't
sink a run the other source could still answer.
"""

import fred_client
import news_client
from agents import timing
from agents.orchestrator import QueryPlan, plan_for_series, plan_query
from orchestration import run_query


def test_the_three_example_queries_route_correctly():
    data_only = plan_query("How has CPI changed over the last 5 years?")
    both = plan_query("What's driving recent inflation news?")
    news_only = plan_query("What are the top headlines about the Fed today?")

    assert data_only.sources == ("data",)
    assert both.sources == ("data", "news")
    assert news_only.sources == ("news",)


def test_data_and_news_agents_run_concurrently_not_sequentially(monkeypatch):
    monkeypatch.setenv("FRED_OFFLINE_LATENCY_MS", "150")
    monkeypatch.setenv("NEWS_OFFLINE_LATENCY_MS", "150")
    fred_client._cache.clear()
    news_client._cache.clear()

    query = "What's driving recent inflation news?"
    sequential = run_query(query, parallel=False)
    fred_client._cache.clear()
    news_client._cache.clear()
    parallel = run_query(query, parallel=True)

    assert sequential.sources_overlapped is False
    assert parallel.sources_overlapped is True
    # sequential ~= data + news; parallel ~= max(data, news)
    assert parallel.wall_seconds < sequential.wall_seconds * 0.7


def test_news_only_query_never_touches_a_data_agent():
    run = run_query("What are the top headlines about the Fed today?")
    assert run.plan.sources == ("news",)
    assert run.data == []
    assert run.news is not None and run.news.ok


def test_news_failure_does_not_sink_a_data_and_news_run(monkeypatch):
    def broken(query, start_date, end_date, limit=10):
        raise news_client.NewsAPIError("simulated outage")

    monkeypatch.setattr(news_client, "search_headlines", broken)

    run = run_query("What's driving recent inflation news?")

    assert run.error is None
    assert run.status == "partial"
    assert run.news_failure is not None
    assert "CPIAUCSL" in run.answer  # the data side still came through


def test_all_sources_failing_is_a_clean_failure(monkeypatch):
    def broken(query, start_date, end_date, limit=10):
        raise news_client.NewsAPIError("simulated outage")

    monkeypatch.setattr(news_client, "search_headlines", broken)

    base = plan_for_series("news about a fake series", ["FAKESERIES"])
    plan = QueryPlan(
        user_query=base.user_query, fetches=base.fetches, needs_data=True,
        needs_news=True, news_query="fake", news_start_date="2026-01-01",
        news_end_date="2026-02-01",
    )
    run = run_query(plan.user_query, plan=plan)

    assert run.error == "all_sources_failed"
    assert run.status == "failed"
    assert run.analysis is not None  # still produced a failure-note answer


def test_timing_module_reused_by_both_agent_kinds():
    """The one bit of shared infra this phase needed: agents/timing.py, used
    by DataFetchBatch.overlapped and by orchestration's cross-source check."""

    class Fake:
        def __init__(self, s, f):
            self.started_at, self.finished_at = s, f

    assert timing.overlapped([Fake(0, 1), Fake(0.5, 1.5)]) is True
    assert timing.overlapped([Fake(0, 1), Fake(1, 2)]) is False
    assert timing.stage_wall_seconds([Fake(0, 1), Fake(0.5, 3)]) == 2.5
