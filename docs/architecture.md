# Architecture

## Two surfaces, one tool implementation

```
                        ┌───────────────────────────┐
Claude Desktop ───MCP──▶ │  server.py (FastMCP)      │
                        │   rate limit + audit log  │
                        └────────────┬──────────────┘
                                     │
                                     ▼
                        ┌───────────────────────────┐
                        │  tools.py                 │   ← single implementation
                        │   validate → FRED → cost  │      of the 4 tools
                        │   guard → shape           │
                        └────────────┬──────────────┘
                                     │
                                     ▼
                        ┌───────────────────────────┐
                        │  fred_client.py           │
                        │   cache · offline fixture │
                        └────────────┬──────────────┘
                                     │
                        ┌────────────┴──────────────┐
                        │  catalog.py               │  ← which series exist,
                        │   aliases · search terms  │     shared by fixture,
                        └───────────────────────────┘     stub planner, evals
                                     ▲
                        ┌────────────┴──────────────┐
User query ───────────▶ │  agents/ (orchestrator)   │
                        └───────────────────────────┘
```

`server.py` and `agents/` never re-implement a tool — they both call
`tools.py`. That is what keeps the MCP contract and the agent contract from
drifting.

## The multi-agent layer

```
                    ┌── Economic Data Agent   tools: search_series,
                    │                          get_series_observations,
                    │                          compare_series, get_series_metadata
                    │
User ─▶ Supervisor ─┼── Research Agent         tools: get_series_metadata
       (delegates)  │
                    ├── Risk Agent             tools: none — reads indicators,
                    │                          emits RISK_SIGNAL + rationale
                    │
                    └── Report Agent           tools: none — grounded write-up
                                     │
                                     ▼
                              Final answer + Evidence
```

* Every agent — supervisor included — runs the **same tool-use loop**
  ([`agents/base.py`](../src/agents/base.py)). The supervisor's "tools" are
  four `delegate_to_*` calls; a specialist's tools are the real FRED tools.
* State between specialists is passed **explicitly** in the task string the
  supervisor writes. Specialists are stateless and independently testable.
* Each agent talks to a `Model` ([`agents/model.py`](../src/agents/model.py)):
  * `AnthropicModel` — a real Claude tool-use turn (`claude-opus-5`).
  * `StubModel` — a deterministic offline planner
    ([`agents/stub.py`](../src/agents/stub.py)) so evals, CI, and the demo
    run with no API key. Same loop code either way; pick with
    `AGENT_BACKEND`.
* A single [`Trace`](../src/agents/trace.py) is threaded through the whole
  run and is the one thing the evaluation harness reads.

## Guardrails, and where they sit

| Guardrail | Layer | File |
|---|---|---|
| Input validation | `tools.py`, before any network call | `security.py` |
| Untrusted-content wrapping | `tools.py`, on every metadata response | `security.py` |
| Token / cost budget | `tools.py`, before returning a payload | `cost_tracker.py` |
| Per-agent iteration cap | agent loop | `agents/base.py` |
| Rate limiting | MCP boundary only | `rate_limit.py` |
| Audit logging | every `call_tool` | `audit_log.py` |

## Evaluation

[`evals/`](../evals) replays [`dataset.jsonl`](../evals/dataset.jsonl)
through the supervisor and grades each run on tool selection, series
grounding, argument validity, orchestration, groundedness, and injection
resistance. `python -m evals` writes [`evals/REPORT.md`](../evals/REPORT.md)
and exits non-zero on any regression, so CI fails loudly.
