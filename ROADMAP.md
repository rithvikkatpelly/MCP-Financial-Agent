# Roadmap

The project is built in layers, each landing as its own commit so the history
reads as a development story rather than one drop.

### Done

- [x] MCP server with four narrow, typed FRED tools + structured errors
- [x] In-memory idempotency cache
- [x] Context/cost optimization: prompt-cache-friendly layout, result shaping,
      per-session token budget guardrail with a shrink fallback
- [x] Input validation + prompt-injection defense + secrets hygiene
- [x] Security test suite
- [x] **Shared tool implementation** — MCP surface and agent surface call one
      `tools.py`, so they can't drift
- [x] **Multi-agent orchestration** — supervisor + Economic Data / Research /
      Risk / Report specialists, each running the same tool-use loop
- [x] **Model abstraction** — real Claude backend (`claude-opus-5`) plus a
      deterministic offline stub so everything runs keyless in CI
- [x] **Offline FRED fixture** — hermetic evals and tests
- [x] **Evaluation harness** — fixed dataset, expected tool-call sequences,
      six scored metrics, Markdown report, non-zero exit on regression
- [x] **Rate limiting** — token bucket at the MCP boundary
- [x] **Audit logging** — append-only JSONL of every call, rejection, limit hit
- [x] CI: tests + eval suite on every push
- [x] **Sequential agent pipeline** — orchestrator → data agent → analysis
      agent, typed dataclass hand-offs, per-agent + running-total cost
- [x] **Multi-series parallelism** — one Data Agent per series via
      `asyncio.gather`, partial-failure tolerance, cross-series correlation
- [x] **Orchestrator routing eval** — 18 structural cases (single/comparison/
      cap/ambiguous/out-of-scope/injection/vague-date), 15 passing + 3 tracked
      `xfail` gaps

### Next

- [ ] Wire `FetchRequest.search_text` through the Data Agent (act on the
      "route via search_series" routing decision, don't just record it)
- [ ] Search-backed catalog so series outside the fixed 7 are reachable
- [ ] Relative-event and compound date parsing in the orchestrator
- [ ] Swap the dict cache for SQLite + TTL
- [ ] Expand the supervisor eval dataset toward 50 cases; add adversarial queries
- [ ] Live-backend eval run in CI (gated, on a schedule, with a spend cap)
- [ ] A second untrusted-content source (news headlines) to stress the
      injection defense with real-world text
- [ ] Streaming the supervisor's progress (per-delegation events)
- [ ] Deploy the MCP server over HTTP with per-session rate-limit keys
- [ ] Observability: structured spans per agent, exported to a trace viewer
- [ ] A short screen recording in the README
