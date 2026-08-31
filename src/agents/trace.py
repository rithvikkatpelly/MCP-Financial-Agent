"""
Execution trace for a single supervisor run.

One `Trace` is threaded through the supervisor and every specialist agent.
It is the single source of truth the evaluation harness reads: which tools
were called, in what order, with what arguments, whether they errored, and
how many tokens were spent.
"""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    agent: str
    name: str
    arguments: dict
    ok: bool
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class Delegation:
    to: str
    task: str


@dataclass
class Trace:
    query: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    delegations: list[Delegation] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: float = field(default_factory=time.monotonic)
    final_report: str = ""
    # Populated by the risk agent so evals can check it without parsing prose.
    risk_signal: str | None = None

    # --- recording -----------------------------------------------------
    def record_tool_call(
        self, agent: str, name: str, arguments: dict, result: dict, latency_ms: float
    ) -> None:
        err = result.get("error") if isinstance(result, dict) else None
        self.tool_calls.append(
            ToolCall(
                agent=agent,
                name=name,
                arguments=arguments,
                ok=err is None,
                error=err,
                latency_ms=latency_ms,
            )
        )

    def record_delegation(self, to: str, task: str) -> None:
        self.delegations.append(Delegation(to=to, task=task))

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    # --- views -------------------------------------------------------
    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000.0

    # The four real FRED tools — everything else in tool_calls is a
    # supervisor `delegate_to_*` call.
    LEAF_TOOLS = (
        "search_series", "get_series_observations", "compare_series", "get_series_metadata",
    )

    @property
    def tool_sequence(self) -> list[str]:
        return [c.name for c in self.tool_calls]

    @property
    def leaf_tool_sequence(self) -> list[str]:
        """FRED tool calls only, in execution order — what the evals grade."""
        return [c.name for c in self.tool_calls if c.name in self.LEAF_TOOLS]

    def leaf_calls(self, agent: str | None = None) -> list["ToolCall"]:
        calls = [c for c in self.tool_calls if c.name in self.LEAF_TOOLS]
        return [c for c in calls if agent is None or c.agent == agent]

    @property
    def series_used(self) -> list[str]:
        """Every FRED series ID that was actually fetched — the grounding set."""
        seen: list[str] = []
        for c in self.tool_calls:
            if not c.ok:
                continue
            if c.name == "get_series_observations":
                sid = c.arguments.get("series_id")
                if sid and sid.upper() not in seen:
                    seen.append(sid.upper())
            elif c.name == "compare_series":
                for sid in c.arguments.get("series_ids", []):
                    if sid.upper() not in seen:
                        seen.append(sid.upper())
        return seen

    @property
    def had_error(self) -> bool:
        return any(not c.ok for c in self.tool_calls)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "tool_sequence": self.tool_sequence,
            "leaf_tool_sequence": self.leaf_tool_sequence,
            "tool_calls": [vars(c) for c in self.tool_calls],
            "delegations": [vars(d) for d in self.delegations],
            "series_used": self.series_used,
            "risk_signal": self.risk_signal,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "final_report": self.final_report,
        }
