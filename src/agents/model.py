"""
Model abstraction for the agent loop.

`Agent` (agents/base.py) only ever talks to a `Model`. Two implementations:

  * `AnthropicModel` — a real Claude tool-use turn via the Anthropic SDK.
  * `StubModel` — a deterministic planner (agents/stub.py) so the evaluation
    harness, CI, and the demo run with no API key and no network.

`make_model(role)` picks one based on the environment: `StubModel` unless
`AGENT_BACKEND=anthropic` (and a key is available).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import cost_tracker

# Default Claude model for live runs. Opus 5 per the project's API guidance.
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "8000"))

# Effort per role: the leaf specialists do bounded, well-specified work and run
# at low effort to keep cost down; the supervisor and report writer get more
# room. (output_config.effort, GA — see the claude-api guidance.)
_EFFORT_BY_ROLE = {
    "supervisor": "medium",
    "report_agent": "medium",
    "economic_data_agent": "low",
    "research_agent": "low",
    "risk_agent": "low",
}


@dataclass
class ToolRequest:
    id: str
    name: str
    input: dict


@dataclass
class ModelResponse:
    text: str = ""
    tool_requests: list[ToolRequest] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_requests)


class Model:
    """Interface. `role` identifies which agent this model is driving."""

    def __init__(self, role: str):
        self.role = role

    def turn(self, system: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
        raise NotImplementedError


class AnthropicModel(Model):
    def __init__(self, role: str, client=None, model: str = ANTHROPIC_MODEL):
        super().__init__(role)
        import anthropic  # local import so the stub path needs no dependency

        self._client = client or anthropic.Anthropic()
        self._model = model

    def turn(self, system: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools or [],
            thinking={"type": "adaptive"},
            output_config={"effort": _EFFORT_BY_ROLE.get(self.role, "medium")},
        )
        if resp.stop_reason == "refusal":
            detail = getattr(resp, "stop_details", None)
            return ModelResponse(
                text=f"[model refused: {getattr(detail, 'category', 'unspecified')}]",
                stop_reason="refusal",
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            )
        text_parts, tool_reqs = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_reqs.append(ToolRequest(id=block.id, name=block.name, input=dict(block.input)))
        return ModelResponse(
            text="\n".join(text_parts).strip(),
            tool_requests=tool_reqs,
            stop_reason=resp.stop_reason or "end_turn",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


class StubModel(Model):
    """Deterministic planner. Delegates the actual decision to agents/stub.py
    so the domain logic lives in one readable place."""

    def turn(self, system: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
        from agents import stub

        resp = stub.plan(self.role, messages, tools)
        # Rough token accounting so cost/usage numbers in the eval report are
        # populated even offline (see cost_tracker's ~4 chars/token heuristic).
        serialized = system + "".join(str(m.get("content", "")) for m in messages)
        resp.input_tokens = cost_tracker.estimate_tokens(serialized)
        resp.output_tokens = cost_tracker.estimate_tokens(
            resp.text + "".join(str(t.input) for t in resp.tool_requests)
        )
        return resp


def make_model(role: str) -> Model:
    backend = os.environ.get("AGENT_BACKEND", "stub").strip().lower()
    if backend == "anthropic":
        return AnthropicModel(role)
    return StubModel(role)
