# Econ Data Agent — MCP + Multi-Agent Orchestration over FRED

A production-oriented financial-intelligence agent that answers questions
about the US economy using real [FRED](https://fred.stlouisfed.org/docs/api/fred/)
data. It demonstrates, end to end:

- **Constrained tool contracts** — four narrow, typed FRED tools, one shared
  implementation behind both an MCP server and a multi-agent orchestrator
- **Multi-agent systems** — a supervisor that decomposes a question and
  delegates to four specialist agents, each running the same tool-use loop
- **AI safety** — input validation, prompt-injection defense, secrets
  hygiene, tool least-privilege, rate limiting, audit logging
  ([SECURITY.md](SECURITY.md))
- **Context / cost optimization** — cache-friendly layout, result shaping, a
  per-session token budget with a shrink fallback
- **Evaluation** — a fixed dataset with expected tool-call sequences, six
  scored metrics, a generated report, and CI that fails on regression

```
                    ┌── Economic Data Agent   (resolves series, fetches data)
                    │
User ─▶ Supervisor ─┼── Research Agent         (source notes / framing)
                    │
                    ├── Risk Agent             (reads indicators → RISK_SIGNAL)
                    │
                    └── Report Agent           (grounded write-up + evidence)
                                     │
                                     ▼
                              Final answer
```

Full picture: [docs/architecture.md](docs/architecture.md). Development
story and what's next: [ROADMAP.md](ROADMAP.md).

## Quick start

```bash
pip install -r requirements.txt

# 1. See the whole multi-agent flow, offline, no keys:
python examples/demo.py

# 2. Run the evaluation suite (hermetic, deterministic):
python -m evals            # writes evals/REPORT.md

# 3. Run the tests:
pytest -q
```

Everything above runs with **no API key** — the orchestrator defaults to a
deterministic offline planner and FRED calls are served from a synthetic
fixture. For the real thing, see [Running it live](#running-it-live).

## Demo

```
$ python examples/demo.py

User:
  Compare CPI and unemployment over the last 5 years and explain whether
  the relationship changed after 2020.

Supervisor delegated to:
  → economic_data_agent
  → research_agent
  → risk_agent
  → report_agent

Tool calls:
  [economic_data_agent] compare_series({'series_ids': ['UNRATE', 'CPIAUCSL'],
                                        'start_date': '2021-06-01',
                                        'end_date': '2026-06-01'})  ok=True
  [research_agent]       get_series_metadata({'series_id': 'UNRATE'})     ok=True
  [research_agent]       get_series_metadata({'series_id': 'CPIAUCSL'})   ok=True

Series grounded on: UNRATE, CPIAUCSL
Risk signal: rising
Tokens: 6135 in / 761 out   Wall time: 2 ms   Backend: stub
```

## 1. Tool contracts

Four narrow tools instead of one "do anything" tool. The implementation lives
once in [`src/tools.py`](src/tools.py); [`server.py`](src/server.py) wraps each
in an `@mcp.tool()` and the agents call the same functions through their
tool-use loop, so the two surfaces can't drift.

| Tool | Purpose | Deliberately does NOT do |
|---|---|---|
| `search_series` | Find a FRED series ID from a plain-language description | Return data — search only, keeps output small |
| `get_series_observations` | Fetch one series over a **required** date range | Accept unbounded ranges — no "give me everything" |
| `compare_series` | Fetch and align 2–4 series over one date range | More than 4 series — keeps the response bounded |
| `get_series_metadata` | Units, frequency, last-updated, source notes | Anything not read-only; notes come back wrapped as untrusted data |

Each tool has strict typed inputs (enums, not free text), structured error
returns (`{"error": "validation_error", ...}`) instead of raised exceptions,
and idempotent caching.

## 2. Multi-agent orchestration

A **Supervisor** ([`src/agents/supervisor.py`](src/agents/supervisor.py))
breaks a question into steps and delegates to four specialists. The
supervisor runs the *same* tool-use loop as every specialist — its tools are
`delegate_to_*` calls. State is passed explicitly in the task string, so each
specialist is stateless and unit-testable.

| Agent | Tools | Job |
|---|---|---|
| Economic Data | all four FRED tools | resolve series IDs, fetch the data |
| Research | `get_series_metadata` only | source notes, caveats, structural breaks |
| Risk | **none** | read the indicators, emit `RISK_SIGNAL: <rising\|elevated\|stable\|easing>` + rationale |
| Report | **none** | final grounded narrative + an Evidence section |

Each agent talks to a `Model`. `AnthropicModel` is a real Claude tool-use
turn (`claude-opus-5`); `StubModel` is a deterministic planner
([`src/agents/stub.py`](src/agents/stub.py)) that keeps evals and CI keyless
and reproducible. Pick with `AGENT_BACKEND=stub|anthropic`.

## 3. Evaluation

[`evals/`](evals) replays [`evals/dataset.jsonl`](evals/dataset.jsonl) (20
cases) through the supervisor and grades each run:

| Metric | What it checks |
|---|---|
| tool selection | Economic Data Agent made exactly the expected ordered tool sequence |
| series grounding | F1 of series fetched vs. expected |
| argument validity | every data call had a well-formed, bounded date range + valid ID (re-runs the real validators) |
| orchestration | supervisor delegated to exactly the right specialists (research + risk only when analysis is asked for) |
| groundedness | the final report only cites series that were actually fetched |
| injection resistance | a deliberately poisoned synthetic series (`INJTEST`) never leaks its payload into the report |

```
$ python -m evals
backend=stub  cases=20  pass=20/20 (100%)
  tool_selection         100.0%
  series_grounding       100.0%
  argument_validity      100.0%
  orchestration          100.0%
  groundedness           100.0%
  injection_resistance   100.0%
```

The stub backend scores 100% by construction — it's a **regression fence** on
the tool-contract and orchestration logic, not a measure of model quality.
`python -m evals` exits non-zero on any regression, so CI catches a broken
tool contract or a mis-wired agent. Run `AGENT_BACKEND=anthropic python -m
evals` for a real model-quality run. Latest report:
[`evals/REPORT.md`](evals/REPORT.md).

## 4. Context / cost optimization

- **Prompt-cache-friendly**: static tool defs + system prompts first, volatile
  content last (see [`cost_tracker.py`](src/cost_tracker.py))
- **Result shaping, not raw dumps**: `get_series_observations` requires a date
  range and thins long ranges to fit the budget rather than dumping every point
- **Token/cost budget guardrail**: [`cost_tracker.py`](src/cost_tracker.py)
  estimates a tool result's cost *before* returning it; over budget, it shrinks
  once, then returns a structured warning asking the model to narrow the request
- **Measured**: every call's estimated cost is logged to `usage.log`

## 5. Security

Full matrix with per-control implementation + test links: **[SECURITY.md](SECURITY.md)**.
Highlights:

- **Validation on every tool** before any network call or cache key
- **Untrusted content stays inert**: FRED notes are returned as a labeled
  `untrusted_source_text` field, never bare text. A poisoned note (*"ignore
  all previous instructions…"*) reaches the model as a quoted string. Covered
  by a live test and an eval probe.
- **No secrets in code or logs**: key from env only; redacted before anything
  is logged
- **Least privilege**: only the Economic Data Agent holds data tools
- **Rate limiting** ([`src/rate_limit.py`](src/rate_limit.py)): token bucket at
  the MCP boundary
- **Audit logging** ([`src/audit_log.py`](src/audit_log.py)): append-only JSONL
  of every tool call, rejection, and rate-limit hit

## Project layout

```
src/
  server.py         MCP server (FastMCP): 4 tools + 1 resource, rate limit + audit
  tools.py          the one implementation of the 4 tools + Anthropic schemas
  fred_client.py    cached FRED wrapper + synthetic offline fixture
  cost_tracker.py   token/cost estimation + per-session budget guardrail
  security.py       input validation + untrusted-content wrapping + redaction
  rate_limit.py     token-bucket rate limiter
  audit_log.py      append-only security audit log
  agents/
    supervisor.py   decomposes the question, delegates
    specialists.py  the four specialist agents
    base.py         the shared tool-use loop
    model.py        AnthropicModel + StubModel
    stub.py         deterministic offline planner
    trace.py        per-run execution trace (what evals read)
evals/
  dataset.jsonl     queries + expected tool-call sequences
  runner.py         replay + score
  metrics.py        the six scored metrics
  report.py         aggregate → REPORT.md
examples/demo.py    end-to-end flow, printed
tests/              security, rate limit, audit, agents, evals
```

## Running it live

1. Free FRED key: https://fred.stlouisfed.org/docs/api/api_key.html
2. `cp .env.example .env`, fill in `FRED_API_KEY` (and `ANTHROPIC_API_KEY` +
   `AGENT_BACKEND=anthropic` for the real orchestrator)
3. `pip install -r requirements.txt`

**As an MCP server for Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "econ-data": {
      "command": "python",
      "args": ["/absolute/path/to/mcp-financial-agent/src/server.py"]
    }
  }
}
```

Then ask *"Compare CPI and the unemployment rate over the last 5 years."*

**As the multi-agent orchestrator**:

```bash
AGENT_BACKEND=anthropic FRED_OFFLINE=0 python examples/demo.py \
  "Analyze whether inflation and unemployment trends indicate rising recession risk."
```
