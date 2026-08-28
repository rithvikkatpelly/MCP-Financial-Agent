# Econ Data Agent — MCP Server for FRED Economic Data

An MCP (Model Context Protocol) server that lets Claude query real economic
data from the [FRED API](https://fred.stlouisfed.org/docs/api/fred/) —
GDP, CPI, unemployment, interest rates, etc. — through a small set of
tightly scoped, cost-aware, security-conscious tools.

Built as a portfolio project demonstrating four things production Claude
integrations need to get right: **tool contract design, MCP server
mechanics, context/cost optimization, and security.**

## Why FRED

FRED is free, well-documented, has a generous rate limit, and the data is
naturally structured (time series with clear IDs), which makes it a good
sandbox for showing tool design discipline without fighting a messy API.

## Project layout

```
mcp-financial-agent/
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   ├── server.py          # MCP server + tool definitions
│   ├── fred_client.py      # Thin, cached wrapper around the FRED API
│   ├── cost_tracker.py     # Token/cost estimation + budget guardrail
│   └── security.py         # Input validation + untrusted-content handling
└── tests/
    └── test_security.py    # Prompt-injection and validation tests
```

## 1. Tool contracts

Four narrow tools instead of one "do anything" tool:

| Tool | Purpose | Deliberately does NOT do |
|---|---|---|
| `search_series` | Find a FRED series ID from a plain-language description (e.g. "unemployment rate") | Does not return raw data — search only, keeps output small |
| `get_series_observations` | Fetch observations for a known series ID, with a required date range | Refuses unbounded date ranges (see cost section) — no "give me everything" |
| `compare_series` | Fetch and align 2–4 series over the same date range for comparison | Capped at 4 series to keep the response and the resulting context bounded |
| `get_series_metadata` | Units, frequency, last updated date, source notes | Read-only, no data volume risk |

Each tool has:
- **Strict typed inputs** (enums for frequency/units where FRED supports them, not free text)
- **Explicit, structured error returns** (`{"error": "series_not_found", "suggestion": ...}`) instead of raising raw exceptions up to the model
- **Idempotency** — calling the same tool with the same args twice returns the same result and hits the local cache, not the FRED API twice

## 2. MCP server

Built with the official Python MCP SDK (`FastMCP`). Exposes:
- The four tools above
- One **resource** (`fred://series/{series_id}/summary`) so a fetched series can be referenced and re-read cheaply without re-invoking a tool call

Run it locally and point Claude Desktop's MCP config at `src/server.py` — see "Running it" below.

## 3. Context / cost optimization

- **Prompt caching**: tool definitions and the system prompt are static across a session, so they're cached rather than re-sent per turn (see `cost_tracker.py` notes on cache-eligible content).
- **Result shaping, not raw dumps**: `get_series_observations` requires a `start_date`/`end_date` and defaults to *monthly* granularity summaries for ranges over 2 years, rather than dumping every daily observation into context.
- **Token/cost budget guardrail**: `cost_tracker.py` estimates the token cost of a tool result *before* returning it. If a call would push the running session estimate past a configurable budget (default: a few cents per session), the server returns a structured warning asking the model to narrow the request instead of silently returning it.
- **Measured, not assumed**: the tracker logs actual estimated cost per call to `usage.log`, so the optimization claim ("caching + truncation cut cost by X%") can be demonstrated with real numbers rather than asserted.

## 4. Security

- **Input validation on every tool** — series IDs are validated against FRED's known ID format before hitting the network; dates are parsed and range-checked; no argument is interpolated into a request unsanitized.
- **Untrusted content stays data, not instructions**: FRED series notes/descriptions are external text returned *through* a tool. They're wrapped and explicitly labeled as data in the tool response schema (e.g. `{"untrusted_source_text": "..."}`) so a series description that happened to contain something like "ignore previous instructions" is not treated as a directive. See `tests/test_security.py` for a live injection-attempt test against this.
- **No secrets in code or logs** — the FRED API key is read from an environment variable (`.env`, not committed) and is never included in error messages, logs, or tool outputs.
- **Scoped write access** — the server is read-only against FRED; it never writes to any external system, and the only local write is the append-only `usage.log`.

## Running it

1. Get a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
2. `cp .env.example .env` and fill in `FRED_API_KEY`
3. `pip install -r requirements.txt`
4. Add to Claude Desktop's MCP config (`claude_desktop_config.json`):

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

5. Restart Claude Desktop and ask it something like *"Compare CPI and the unemployment rate over the last 5 years."*

## What I'd build next

- Swap the naive in-memory cache for a small SQLite cache with TTL
- Add a second untrusted-content source (e.g. news headlines) to stress-test the injection defense further
- Add eval cases (a fixed set of queries + expected tool-call sequences) to catch regressions in tool selection
