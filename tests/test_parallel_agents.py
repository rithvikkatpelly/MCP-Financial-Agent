"""
Phase-2 multi-series behaviour: one Data Agent per series, run concurrently,
with partial-failure tolerance and correct cost/ordering.
"""

import time

import pytest

import fred_client
from agents import data_agent
from agents.orchestrator import plan_for_series, plan_query
from orchestration import run_query

THREE_SERIES = "Compare CPI, unemployment, and the 10-year treasury rate over the last 5 years"


@pytest.fixture
def slow_fetch(monkeypatch):
    """Make each blocking fetch take ~120 ms so concurrency is observable."""
    real = data_agent._fetch_one

    def slow(req):
        time.sleep(0.12)
        return real(req)

    monkeypatch.setattr(data_agent, "_fetch_one", slow)
    return slow


# --- (a) multiple Data Agents actually ran, concurrently ----------------


def test_one_data_agent_instance_per_series():
    plan = plan_query(THREE_SERIES)
    assert len(plan.fetches) == 3
    batch = data_agent.fetch_all(plan, parallel=True)
    assert len(batch.agents) == 3
    assert len({id(a) for a in batch.agents}) == 3  # distinct instances
    assert [r.series_id for r in batch.results] == ["CPIAUCSL", "UNRATE", "DGS10"]


def test_agents_really_run_in_parallel_not_a_sequential_loop(slow_fetch):
    plan = plan_query(THREE_SERIES)

    fred_client._cache.clear()
    seq = data_agent.fetch_all(plan, parallel=False)
    fred_client._cache.clear()
    par = data_agent.fetch_all(plan, parallel=True)

    # 3 agents x ~0.12s: sequential ≈ 0.36s, parallel ≈ 0.12s
    assert seq.wall_seconds > 3 * 0.10
    assert par.wall_seconds < seq.wall_seconds / 2
    assert par.overlapped is True          # execution windows overlapped
    assert seq.overlapped is False         # they did not, run one at a time


# --- (b) results preserve request order --------------------------------


def test_results_come_back_in_request_order():
    plan = plan_for_series(THREE_SERIES, ["DGS10", "CPIAUCSL", "UNRATE"])
    run = run_query(plan.user_query, plan=plan)
    assert [r.series_id for r in run.data] == ["DGS10", "CPIAUCSL", "UNRATE"]
    assert [a.series_id for a in run.analysis.per_series] == ["DGS10", "CPIAUCSL", "UNRATE"]


# --- (c) partial failure doesn't kill the run -------------------------


def test_one_bad_series_id_does_not_crash_the_run():
    plan = plan_for_series(THREE_SERIES, ["CPIAUCSL", "FAKESERIES", "DGS10"])
    run = run_query(plan.user_query, plan=plan)

    assert run.error is None
    assert run.status == "partial"
    assert [f["series_id"] for f in run.failures] == ["FAKESERIES"]
    assert run.failures[0]["reason"]  # a reason is recorded

    ok_ids = [r.series_id for r in run.data if r.ok]
    assert ok_ids == ["CPIAUCSL", "DGS10"]
    assert len(run.analysis.per_series) == 2
    assert "FAKESERIES" in run.answer  # the answer notes the failure


def test_all_series_failing_is_a_clean_failure_not_a_crash():
    plan = plan_for_series("compare nonsense", ["NOPE1", "NOPE2"])
    run = run_query(plan.user_query, plan=plan)
    assert run.error == "all_data_agents_failed"
    assert run.status == "failed"
    assert run.analysis is not None  # failure note still produced


# --- (d) cost sums across the parallel calls --------------------------


def test_cost_sums_across_all_parallel_data_agents():
    run = run_query(THREE_SERIES)
    rows = {r["stage"]: r for r in run.cost["per_agent"]}

    assert rows["data_agent"]["calls"] == 3
    assert rows["orchestrator"]["calls"] == 1
    assert rows["analysis_agent"]["calls"] == 1

    total = run.cost["total"]["estimated_usd"]
    assert total == pytest.approx(round(sum(r["estimated_usd"] for r in rows.values()), 6))
    # the data-agent stage is the bulk of the run's token cost
    assert rows["data_agent"]["input_tokens"] + rows["data_agent"]["output_tokens"] > 0


# --- cross-series analysis --------------------------------------------


def test_multi_series_produces_cross_series_analysis():
    run = run_query(THREE_SERIES)
    cross = run.analysis.cross_series
    assert cross is not None
    assert set(cross.series_ids) == {"CPIAUCSL", "UNRATE", "DGS10"}
    assert cross.overlap_points > 24
    # a correlation for each of the 3 pairs
    assert len(cross.correlations) == 3
    assert all(-1.0 <= v <= 1.0 for v in cross.correlations.values())
    assert cross.strongest_mover in cross.series_ids
