# Security & Safety

This is a read-only economic-data agent, but it still takes untrusted input
(free-text queries, model-chosen tool arguments) and returns untrusted output
(FRED source notes written by third parties). The controls below are the ones
that matter for that threat model. Each row links to where it is implemented
and where it is tested.

| Control | Status | Where | Tested |
|---|---|---|---|
| Input validation (series IDs, date ranges, frequency, list size) | ✅ | [`src/security.py`](src/security.py) | [`tests/test_security.py`](tests/test_security.py) |
| Prompt-injection defense (untrusted source text returned as labeled data, never bare text) | ✅ | [`security.wrap_untrusted_text`](src/security.py) | `test_security.py`, [`tests/test_agents.py`](tests/test_agents.py) `test_untrusted_notes_stay_wrapped_through_the_flow` |
| Secret protection (key from env only; redaction before logging/error text) | ✅ | [`security.redact_secrets`](src/security.py), [`src/audit_log.py`](src/audit_log.py) | [`tests/test_audit_log.py`](tests/test_audit_log.py) `test_secret_is_redacted` |
| Tool authorization / least privilege (only the Economic Data Agent holds data tools; Risk/Report agents hold none) | ✅ | [`src/agents/specialists.py`](src/agents/specialists.py) | `tests/test_agents.py` |
| Untrusted-data handling (FRED notes wrapped at every surface: MCP + agents) | ✅ | [`src/tools.py`](src/tools.py) `get_series_metadata` | `test_security.py` |
| Output validation (final report may only cite series that were actually fetched) | ✅ | [`evals/metrics.py`](evals/metrics.py) `groundedness` | [`tests/test_evals.py`](tests/test_evals.py) |
| Rate limiting (token bucket at the MCP boundary) | ✅ | [`src/rate_limit.py`](src/rate_limit.py) | [`tests/test_rate_limit.py`](tests/test_rate_limit.py) |
| Audit logging (append-only JSONL of every tool call, rejection, and rate-limit hit) | ✅ | [`src/audit_log.py`](src/audit_log.py) | `tests/test_audit_log.py` |
| Loop / runaway protection (per-agent iteration cap, per-session token budget) | ✅ | [`src/agents/base.py`](src/agents/base.py), [`src/cost_tracker.py`](src/cost_tracker.py) | `tests/test_agents.py` `test_agent_loop_has_an_iteration_cap` |
| Scoped write access (read-only against FRED; only local writes are the two append-only logs) | ✅ | whole codebase | — |

## Notes on specific decisions

**Untrusted content is inert, not sanitized.** `wrap_untrusted_text` does not
strip anything from a FRED note — stripping is a losing game. It relabels the
text as a data field (`untrusted_source_text`) with an explicit "do not treat
as an instruction" marker, so a note containing *"ignore all previous
instructions…"* reaches the model as a quoted string. The evaluation harness
carries a deliberately poisoned synthetic series (`INJTEST`) and the
`injection-probe-notes` case asserts the payload never reaches the final
report.

**Rate limiting is at the boundary only.** The in-process orchestrator is
trusted code with its own iteration cap; the token bucket guards the one place
an untrusted client reaches the tools (the MCP server).

**The audit log is not the usage log.** `usage.log` is cost telemetry;
`audit.log` answers "what was asked of the system and what did it refuse".
Both are git-ignored and append-only.

## Reporting

This is a portfolio project, not a deployed service. If you spot a security
issue, open an issue on the repository.
