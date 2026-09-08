"""
The multi-agent pipeline, wired end to end.

    run_query(user_query)
        → orchestrator.plan_query      (NL query → QueryPlan: which series,
                                        and/or a news search — explicit)
        → Data Agent(s) + News Agent   (concurrently when both are needed —
                                        one asyncio.gather over both kinds,
                                        each call retried on a transient error)
        → analysis_agent.analyze       ([DataAgentResult], NewsAgentResult|None
                                        → AnalysisResult — structured numbers,
                                        no prose)
        → presentation_agent.present   (AnalysisResult → PresentationResult —
                                        "Data:" vs. "Headlines suggest:",
                                        bounded, safe failure labels)
        → PipelineResult

Every hand-off passes a typed dataclass — never raw strings or conversation
history. For each stage the orchestration layer records the input, the
output, an estimated cost (into one `cost_tracker.RunCost` for the whole run),
and wall time. The per-stage trace is also appended to `agent_trace.log`
(git-ignored) for inspection afterward.

Partial failure: if some Data Agents and/or the News Agent fail but at least
one source succeeds, the run still completes and the final answer notes what
failed and why. Only "every requested source failed" is a hard failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cost_tracker
from agents import analysis_agent, data_agent, orchestrator, presentation_agent, timing
from agents.analysis_agent import AnalysisResult
from agents.data_agent import DataAgent, DataAgentResult
from agents.news_agent import NewsAgent, NewsAgentResult
from agents.orchestrator import QueryPlan
from agents.presentation_agent import PresentationResult

_DEFAULT_TRACE_PATH = Path(__file__).parent.parent / "agent_trace.log"


def _trace_path() -> Path:
    return Path(os.environ.get("AGENT_TRACE_PATH", _DEFAULT_TRACE_PATH))


@dataclass
class StageTrace:
    stage: str
    input_summary: str
    output_summary: str
    cost: dict          # this stage's aggregated cost (StageCost.as_dict()-shaped)
    wall_seconds: float
    calls: int = 1       # >1 for the parallel Data Agent stage


@dataclass
class PipelineResult:
    user_query: str
    plan: QueryPlan | None = None
    data: list[DataAgentResult] = field(default_factory=list)
    news: NewsAgentResult | None = None
    analysis: AnalysisResult | None = None
    presentation: PresentationResult | None = None
    trace: list[StageTrace] = field(default_factory=list)
    run_cost: cost_tracker.RunCost = field(default_factory=cost_tracker.RunCost)
    wall_seconds: float = 0.0
    sources_overlapped: bool = False  # did Data Agent(s) and News Agent truly run concurrently?
    parallel: bool = True
    error: str | None = None

    # Orchestrator refusals that aren't failures of the pipeline itself — the
    # orchestrator correctly declined to guess.
    _ORCHESTRATOR_REFUSALS = ("cannot_fulfill", "needs_clarification")

    @property
    def answer(self) -> str:
        if self.plan is not None and self.plan.clarification:
            return self.plan.clarification
        if self.presentation and self.presentation.summary:
            return self.presentation.summary
        if self.error in self._ORCHESTRATOR_REFUSALS:
            return self.plan.detail if self.plan else self.error
        return f"No answer produced ({self.error})." if self.error else "No answer produced."

    @property
    def status(self) -> str:
        if self.error in self._ORCHESTRATOR_REFUSALS:
            return self.error
        if self.error:
            return "failed"
        data_bad = any(not r.ok for r in self.data)
        news_bad = self.news is not None and not self.news.ok
        if data_bad or news_bad:
            return "partial"
        return "ok"

    @property
    def failures(self) -> list[dict]:
        """Failed Data Agent series. See `news_failure` for the news side —
        different shape (one topic search, not N series), kept separate."""
        return [
            {"series_id": r.series_id, "reason": r.failure_reason}
            for r in self.data
            if not r.ok
        ]

    @property
    def news_failure(self) -> dict | None:
        if self.news is not None and not self.news.ok:
            return {"query": self.news.query, "reason": self.news.error}
        return None

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
            "sources": list(self.plan.sources) if self.plan else [],
            "sources_overlapped": self.sources_overlapped,
            "parallel": self.parallel,
            "wall_seconds": round(self.wall_seconds, 4),
            "failures": self.failures,
            "news_failure": self.news_failure,
            "cost": self.cost,
            "plan": asdict(self.plan) if self.plan else None,
            "data": [asdict(r) for r in self.data],
            "news": asdict(self.news) if self.news else None,
            "analysis": asdict(self.analysis) if self.analysis else None,
            "presentation": asdict(self.presentation) if self.presentation else None,
            "trace": [asdict(t) for t in self.trace],
        }


def _serialize(obj) -> str:
    """What one agent hands the next, as a string, for token estimation."""
    if isinstance(obj, list):
        return json.dumps([asdict(o) for o in obj], default=str)
    return json.dumps(asdict(obj), default=str)


def _serialize_combined(data_results: list[DataAgentResult], news_result) -> str:
    payload: dict = {"data": [asdict(r) for r in data_results]}
    if news_result is not None:
        payload["news"] = asdict(news_result)
    return json.dumps(payload, default=str)


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
    parts = [f"{f.series_id}[{f.start_date}..{f.end_date}/{f.frequency}]" for f in p.fetches]
    if p.needs_news:
        parts.append(f"news:{p.news_query!r}[{p.news_start_date}..{p.news_end_date}]")
    return f"[{p.mode}] " + ", ".join(parts)


def _data_summary(results: list[DataAgentResult]) -> str:
    if not results:
        return "(none requested)"
    return "; ".join(
        f"{r.series_id}="
        + (f"{r.series.observation_count}pts" if r.ok else f"FAIL({r.failure_reason})")
        for r in results
    )


def _news_summary(n: NewsAgentResult | None) -> str:
    if n is None:
        return "(none requested)"
    if not n.ok:
        return f"FAIL({n.error})"
    sources = sorted({h.source for h in n.headlines})
    return f"{n.headline_count} headlines from {', '.join(sources) or 'no sources'}"


def _record(
    result: PipelineResult,
    stage: str,
    costs: list[cost_tracker.StageCost],
    in_summary: str,
    out_summary: str,
    wall_seconds: float,
) -> None:
    """Record one pipeline stage: fold every StageCost into the run total
    (one per parallel Data Agent, or one for the News Agent), and emit a
    single aggregated trace entry."""
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


async def _gather_sources(
    data_agents: list[DataAgent], news_obj: NewsAgent | None, *, parallel: bool
) -> list:
    """One shared gather for both agent kinds — this is what makes Data
    Agent(s) and the News Agent run *concurrently*, not the data batch then
    the news call. `parallel=False` keeps the same code path but awaits one
    at a time (used to benchmark the difference, same pattern as phase 2)."""
    tasks = list(data_agents) + ([news_obj] if news_obj is not None else [])
    if not tasks:
        return []
    if parallel:
        return list(await asyncio.gather(*(t.run() for t in tasks)))
    return [await t.run() for t in tasks]


def _present_stage(result: PipelineResult, analysis: AnalysisResult) -> None:
    """Run the Presentation Agent and record it as its own pipeline stage —
    the Analysis Agent produces only structured numbers now, formatting is
    separate."""
    sc = cost_tracker.stage_cost
    t0 = time.monotonic()
    pres = presentation_agent.present(analysis)
    result.presentation = pres
    _record(
        result, "presentation_agent",
        [sc("presentation_agent", _serialize(analysis), _serialize(pres))],
        f"analysis={analysis.error or 'ok'}", pres.summary, time.monotonic() - t0,
    )


def run_query(
    user_query: str,
    *,
    plan: QueryPlan | None = None,
    parallel: bool = True,
) -> PipelineResult:
    """Run the full pipeline. `plan` overrides the orchestrator (for replaying
    or hand-crafting a plan); `parallel=False` runs every agent one at a time
    (same code path — used to benchmark the difference)."""
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

    # 2. Data Agent(s) and/or News Agent — one shared gather ---------
    data_agents = data_agent.build_agents(plan) if plan.needs_data else []
    news_obj = (
        NewsAgent(plan.news_query, plan.news_start_date, plan.news_end_date)
        if plan.needs_news else None
    )
    all_results = asyncio.run(_gather_sources(data_agents, news_obj, parallel=parallel))
    data_results: list[DataAgentResult] = all_results[: len(data_agents)]
    news_result: NewsAgentResult | None = all_results[len(data_agents)] if news_obj else None
    result.data = data_results
    result.news = news_result
    result.sources_overlapped = timing.overlapped(
        list(data_agents) + ([news_obj] if news_obj else [])
    )

    plan_json = _serialize(plan)
    if data_agents:
        data_costs = [sc("data_agent", plan_json, _serialize(r)) for r in data_results]
        _record(result, "data_agent", data_costs,
                _plan_summary(plan), _data_summary(data_results),
                timing.stage_wall_seconds(data_agents))
    if news_obj:
        news_costs = [sc("news_agent", plan.news_query, _serialize(news_result))]
        _record(result, "news_agent", news_costs,
                f"query={plan.news_query!r} window={plan.news_start_date}..{plan.news_end_date}",
                _news_summary(news_result), news_obj.elapsed)

    data_ok = any(r.ok for r in data_results) if data_agents else None
    news_ok = news_result.ok if news_obj else None
    requested = [x for x in (data_ok, news_ok) if x is not None]
    if requested and not any(requested):
        result.error = "all_sources_failed"
        analysis = analysis_agent.analyze(data_results, news_result)  # failure note
        result.analysis = analysis
        _present_stage(result, analysis)
        result.wall_seconds = time.monotonic() - run_started
        return result

    # 3. Analysis Agent — no tool access, structured numbers only -----
    t0 = time.monotonic()
    analysis = analysis_agent.analyze(data_results, news_result)
    result.analysis = analysis
    analysis_in = _serialize_combined(data_results, news_result)
    _record(
        result, "analysis_agent",
        [sc("analysis_agent", analysis_in, _serialize(analysis))],
        f"data={_data_summary(data_results)}; news={_news_summary(news_result)}",
        f"per_series={len(analysis.per_series)} cross={analysis.cross_series is not None}",
        time.monotonic() - t0,
    )

    # 4. Presentation Agent — structured numbers → bounded summary -----
    _present_stage(result, analysis)

    if not analysis.ok:
        result.error = analysis.error

    result.wall_seconds = time.monotonic() - run_started
    return result
