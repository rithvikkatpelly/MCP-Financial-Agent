"""
The multi-agent pipeline, wired end to end.

    run_query(user_query)
        → orchestrator.plan_query   (NL query → QueryPlan, 1..N FetchRequests)
        → data_agent.fetch_all      (QueryPlan → one Data Agent per series,
                                     run concurrently, → [DataAgentResult])
        → analysis_agent.analyze    ([DataAgentResult] → AnalysisResult)
        → PipelineResult

Every hand-off passes a typed dataclass — never raw strings or conversation
history. For each stage the orchestration layer records the input, the
output, an estimated cost (into one `cost_tracker.RunCost` for the whole run),
and wall time. The per-stage trace is also appended to `agent_trace.log`
(git-ignored) for inspection afterward.

Partial failure: if some Data Agents fail (bad series ID, FRED error) but at
least one succeeds, the run still completes on the successful results and the
final answer notes which series failed and why.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cost_tracker
from agents import analysis_agent, data_agent, orchestrator
from agents.analysis_agent import AnalysisResult
from agents.data_agent import DataAgentResult
from agents.orchestrator import QueryPlan

_DEFAULT_TRACE_PATH = Path(__file__).parent.parent / "agent_trace.log"


def _trace_path() -> Path:
    return Path(os.environ.get("AGENT_TRACE_PATH", _DEFAULT_TRACE_PATH))


@dataclass
class StageTrace:
    stage: str
    input_summary: str
    output_summary: str
    cost: dict          # this stage's StageCost.as_dict()
    wall_seconds: float
    calls: int = 1      # >1 for the parallel Data Agent stage


@dataclass
class PipelineResult:
    user_query: str
    plan: QueryPlan | None = None
    data: list[DataAgentResult] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    trace: list[StageTrace] = field(default_factory=list)
    run_cost: cost_tracker.RunCost = field(default_factory=cost_tracker.RunCost)
    wall_seconds: float = 0.0
    parallel: bool = True
    error: str | None = None

    # Orchestrator refusals that aren't failures of the pipeline itself — the
    # orchestrator correctly declined to guess.
    _ORCHESTRATOR_REFUSALS = ("cannot_fulfill", "needs_clarification")

    @property
    def answer(self) -> str:
        if self.plan is not None and self.plan.clarification:
            return self.plan.clarification
        if self.analysis and self.analysis.answer:
            return self.analysis.answer
        if self.error in self._ORCHESTRATOR_REFUSALS:
            return self.plan.detail if self.plan else self.error
        return f"No answer produced ({self.error})." if self.error else "No answer produced."

    @property
    def status(self) -> str:
        if self.error in self._ORCHESTRATOR_REFUSALS:
            return self.error
        if self.error:
            return "failed"
        if any(not r.ok for r in self.data):
            return "partial"
        return "ok"

    @property
    def failures(self) -> list[dict]:
        return [
            {"series_id": r.series_id, "reason": r.failure_reason}
            for r in self.data
            if not r.ok
        ]

    @property
    def cost(self) -> dict:
        """Per-agent breakdown + the running total for the whole run."""
        return self.run_cost.as_dict()

    @property
    def total_estimated_usd(self) -> float:
        return self.run_cost.total_usd

    def result_for(self, series_id: str) -> DataAgentResult | None:
        return next((r for r in self.data if r.series_id == series_id), None)

    def to_dict(self) -> dict:
        return {
            "user_query": self.user_query,
            "status": self.status,
            "answer": self.answer,
            "error": self.error,
            "parallel": self.parallel,
            "wall_seconds": round(self.wall_seconds, 4),
            "failures": self.failures,
            "cost": self.cost,
            "plan": asdict(self.plan) if self.plan else None,
            "data": [asdict(r) for r in self.data],
            "analysis": asdict(self.analysis) if self.analysis else None,
            "trace": [asdict(t) for t in self.trace],
        }


def _serialize(obj) -> str:
    """What one agent hands the next, as a string, for token estimation."""
    if isinstance(obj, list):
        return json.dumps([asdict(o) for o in obj], default=str)
    return json.dumps(asdict(obj), default=str)


def _log(stage: StageTrace) -> None:
    line = json.dumps(
        {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **asdict(stage)}, default=str
    )
    try:
        with open(_trace_path(), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # best-effort, mirrors audit_log / cost_tracker


def _plan_summary(p: QueryPlan) -> str:
    if not p.ok:
        return f"error={p.error}"
    return f"[{p.mode}] " + ", ".join(
        f"{f.series_id}[{f.start_date}..{f.end_date}/{f.frequency}]" for f in p.fetches
    )


def _data_summary(results: list[DataAgentResult]) -> str:
    return "; ".join(
        f"{r.series_id}="
        + (f"{r.series.observation_count}pts" if r.ok else f"FAIL({r.failure_reason})")
        for r in results
    )


def _record(
    result: PipelineResult,
    stage: str,
    costs: list[cost_tracker.StageCost],
    in_summary: str,
    out_summary: str,
    wall_seconds: float,
) -> None:
    """Record one pipeline stage: fold every StageCost into the run total
    (one per parallel Data Agent), and emit a single aggregated trace entry."""
    for c in costs:
        result.run_cost.record(c)
    agg = {
        "stage": stage,
        "calls": len(costs),
        "input_tokens": sum(c.input_tokens for c in costs),
        "output_tokens": sum(c.output_tokens for c in costs),
        "estimated_usd": round(sum(c.usd for c in costs), 6),
    }
    trace = StageTrace(stage, in_summary, out_summary, agg, round(wall_seconds, 4), len(costs))
    result.trace.append(trace)
    _log(trace)


def run_query(
    user_query: str,
    *,
    plan: QueryPlan | None = None,
    parallel: bool = True,
) -> PipelineResult:
    """Run the full pipeline. `plan` overrides the orchestrator (for replaying
    or hand-crafting a plan); `parallel=False` runs the Data Agents one at a
    time (same code path — used to benchmark the difference)."""
    result = PipelineResult(user_query=user_query, parallel=parallel)
    run_started = time.monotonic()
    sc = cost_tracker.stage_cost

    # 1. Orchestrator ------------------------------------------------
    if plan is None:
        t0 = time.monotonic()
        plan = orchestrator.plan_query(user_query)
        wall, suffix = time.monotonic() - t0, ""
    else:
        wall, suffix = 0.0, " (supplied)"
    result.plan = plan
    _record(result, "orchestrator", [sc("orchestrator", user_query, _serialize(plan))],
            user_query, _plan_summary(plan) + suffix, wall)
    if not plan.ok:
        result.error = plan.error
        result.wall_seconds = time.monotonic() - run_started
        return result

    # 2. Data Agents — one per series, concurrently -----------------
    batch = data_agent.fetch_all(plan, parallel=parallel)
    result.data = batch.results
    plan_json = _serialize(plan)
    produced = _serialize(batch.results)
    # One StageCost per Data Agent instance → RunCost sums them, per_agent()
    # shows the call count.
    data_costs = [sc("data_agent", plan_json, _serialize(r)) for r in batch.results]
    _record(result, "data_agent", data_costs,
            _plan_summary(plan), _data_summary(batch.results), batch.wall_seconds)

    if not batch.ok_results:
        result.error = "all_data_agents_failed"
        result.analysis = analysis_agent.analyze(batch.results)  # fills the failure note
        result.wall_seconds = time.monotonic() - run_started
        return result

    # 3. Analysis Agent — no tool access --------------------------
    t0 = time.monotonic()
    analysis = analysis_agent.analyze(batch.results)
    result.analysis = analysis
    _record(result, "analysis_agent", [sc("analysis_agent", produced, _serialize(analysis))],
            _data_summary(batch.results), analysis.answer, time.monotonic() - t0)

    if not analysis.ok:
        result.error = analysis.error

    result.wall_seconds = time.monotonic() - run_started
    return result
