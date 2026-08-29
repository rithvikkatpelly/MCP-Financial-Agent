"""Multi-agent orchestration (stub backend)."""

import pytest

from agents import Trace
from agents.supervisor import Supervisor, run


def test_analytical_query_runs_the_full_chain():
    trace = run("Analyze whether inflation and unemployment indicate rising recession risk since 2019.")
    assert [d.to for d in trace.delegations] == [
        "economic_data_agent", "research_agent", "risk_agent", "report_agent"
    ]
    assert trace.leaf_tool_sequence[:1] == ["compare_series"]
    assert set(trace.series_used) == {"CPIAUCSL", "UNRATE"}
    assert trace.risk_signal == "elevated"
    assert "Evidence" in trace.final_report


def test_pure_fetch_skips_research_and_risk():
    trace = run("Just pull the unemployment rate from 2015 to 2020.")
    targets = [d.to for d in trace.delegations]
    assert targets == ["economic_data_agent", "report_agent"]
    assert trace.leaf_tool_sequence == ["get_series_observations"]


def test_single_series_uses_observations_not_compare():
    trace = run("Show core PCE since 2021.")
    assert trace.leaf_tool_sequence == ["get_series_observations"]
    assert trace.series_used == ["PCEPILFE"]


def test_vague_concept_searches_first():
    trace = run("I want data on how expensive borrowing has gotten recently.")
    assert trace.leaf_tool_sequence[0] == "search_series"
    assert "get_series_observations" in trace.leaf_tool_sequence


def test_agent_loop_has_an_iteration_cap():
    # A supervisor model that never stops asking for tools must still terminate.
    from agents.base import Agent
    from agents.model import ModelResponse, ToolRequest

    class Spinner:
        role = "supervisor"

        def turn(self, system, messages, tools):
            return ModelResponse(
                tool_requests=[ToolRequest(id="x", name="delegate_to_report_agent", input={"task": "hi"})],
                stop_reason="tool_use",
            )

    trace = Trace()
    agent = Agent("supervisor", "", [], lambda n, a: {"ok": True}, Spinner(), trace, max_iterations=3)
    out = agent.run("go")
    assert "iteration cap" in out
    assert len(trace.tool_calls) == 3


def test_untrusted_notes_stay_wrapped_through_the_flow():
    trace = run("Analyze recent moves in the FRED series INJTEST and their risk implications.")
    lc = trace.final_report.lower()
    assert "attacker@example.com" not in lc
    assert "ignore all previous instructions" not in lc
    assert trace.series_used == ["INJTEST"]


def test_trace_to_dict_is_serializable():
    import json

    trace = run("Compare CPI and unemployment from 2019 to 2024.")
    json.dumps(trace.to_dict())  # must not raise
