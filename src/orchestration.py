"""
The phase-1 pipeline, wired end to end.

    run_query(user_query)
        → orchestrator.plan_query   (NL query        → QueryPlan)
        → data_agent.fetch          (QueryPlan       → DataAgentResult)
        → analysis_agent.analyze    (DataAgentResult → AnalysisResult)
        → PipelineResult

Sequential, no parallelism. Every hand-off passes a typed dataclass — never
raw strings or conversation history. For each stage the orchestration layer
records the input, the output, and an estimated cost into a single
`cost_tracker.RunCost` for the whole run; the per-stage trace is also
appended to `agent_trace.log` (git-ignored) for inspection afterward.
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
    cost: dict  # this stage's StageCost.as_dict()


@dataclass
class PipelineResult:
    user_query: str
    plan: QueryPlan | None = None
    data: DataAgentResult | None = None
    analysis: AnalysisResult | None = None
    trace: list[StageTrace] = field(default_factory=list)
    run_cost: cost_tracker.RunCost = field(default_factory=cost_tracker.RunCost)
    error: str | None = None

    @property
    def answer(self) -> str:
        if self.analysis and self.analysis.answer:
            return self.analysis.answer
        return f"No answer produced ({self.error})." if self.error else "No answer produced."

    @property
    def cost(self) -> dict:
        """Per-agent breakdown + the running total for the whole run."""
        return self.run_cost.as_dict()

    @property
    def total_estimated_usd(self) -> float:
        return self.run_cost.total_usd

    def to_dict(self) -> dict:
        return {
            "user_query": self.user_query,
            "answer": self.answer,
            "error": self.error,
            "cost": self.cost,
            "plan": asdict(self.plan) if self.plan else None,
            "data": asdict(self.data) if self.data else None,
            "analysis": asdict(self.analysis) if self.analysis else None,
            "trace": [asdict(t) for t in self.trace],
        }


def _serialize(obj) -> str:
    """What one agent hands the next, as a string, for token estimation."""
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


def _data_summary(d: DataAgentResult) -> str:
    return "; ".join(
        f"{s.series_id}={s.observation_count}pts" + (f" err={s.error}" if s.error else "")
        for s in d.series
    ) or f"errors={d.errors}"


def _record(result: PipelineResult, stage: str, sent: str, produced: str,
            in_summary: str, out_summary: str) -> None:
    cost = result.run_cost.add(stage, sent, produced)
    trace = StageTrace(stage, in_summary, out_summary, cost.as_dict())
    result.trace.append(trace)
    _log(trace)


def run_query(user_query: str) -> PipelineResult:
    result = PipelineResult(user_query=user_query)

    # 1. Orchestrator -------------------------------------------------
    plan = orchestrator.plan_query(user_query)
    result.plan = plan
    _record(result, "orchestrator", user_query, _serialize(plan),
            user_query, _plan_summary(plan))
    if not plan.ok:
        result.error = plan.error
        return result

    # 2. Data Agent (the only stage with tool access) ---------------
    data = data_agent.fetch(plan)
    result.data = data
    _record(result, "data_agent", _serialize(plan), _serialize(data),
            _plan_summary(plan), _data_summary(data))
    if not data.ok:
        result.error = "data_agent_failed"
        return result

    # 3. Analysis Agent (no tool access) --------------------------
    analysis = analysis_agent.analyze(data)
    result.analysis = analysis
    _record(result, "analysis_agent", _serialize(data), _serialize(analysis),
            _data_summary(data), analysis.answer)
    if not analysis.ok:
        result.error = analysis.error

    return result
