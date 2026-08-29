"""
Deterministic offline planner behind `StubModel`.

`plan(role, messages, tools)` returns the same `ModelResponse` shape a real
Claude turn would, using hand-written rules instead of a model. It exists so
the whole multi-agent flow — supervisor delegation, the specialists' tool
loops, the trace, the evaluation harness — can run in CI with no API key and
produce identical results every time.

The rules are intentionally simple keyword logic. They are good enough to
exercise tool *selection* and *orchestration* (which is what the evals
measure); they are not a substitute for the model's actual analysis. Set
`AGENT_BACKEND=anthropic` to run the real thing.
"""

from __future__ import annotations

import json
import re

from agents.model import ModelResponse, ToolRequest

# Concept keywords -> FRED series ID. Order matters: more specific first.
_SERIES_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("core cpi", "core inflation", "less food and energy"), "CPILFESL"),
    (("core pce", "pce price", "pce"), "PCEPILFE"),
    (("unemployment", "jobless", "labor market"), "UNRATE"),
    (("headline cpi", "cpi", "consumer price", "inflation", "prices"), "CPIAUCSL"),
    (("fed funds", "federal funds", "policy rate", "interest rate", "fed's rate",
      "fed tightening", "tightening", "rate hike", "fed hik"), "FEDFUNDS"),
    (("10 year", "10-year", "treasury", "bond yield", "long rate"), "DGS10"),
    (("gdp", "gross domestic product", "economic output", "growth"), "GDP"),
]

_KNOWN_IDS = {"UNRATE", "CPIAUCSL", "CPILFESL", "PCEPILFE", "FEDFUNDS", "DGS10", "GDP", "INJTEST"}

_ANALYSIS_HINTS = (
    "analy", "assess", "risk", "recession", "explain", "why", "outlook",
    "trend", "relationship", "changed", "compare", "impact", "signal",
)


# --- message-history helpers --------------------------------------------


def _first_user_text(messages: list[dict]) -> str:
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], str):
            return m["content"]
    return ""


def _assistant_tool_names(messages: list[dict]) -> list[str]:
    names: list[str] = []
    for m in messages:
        if m["role"] != "assistant" or not isinstance(m["content"], list):
            continue
        names += [b["name"] for b in m["content"] if b.get("type") == "tool_use"]
    return names


def _tool_result_texts(messages: list[dict]) -> list[str]:
    out: list[str] = []
    for m in messages:
        if m["role"] != "user" or not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_result":
                out.append(str(b.get("content", "")))
    return out


def _series_in_text(text: str) -> list[str]:
    found: list[str] = []
    for tok in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", text):
        if tok in _KNOWN_IDS and tok not in found:
            found.append(tok)
    return found


def _match_series(text: str) -> list[str]:
    t = text.lower()
    picked: list[str] = []
    for keywords, sid in _SERIES_KEYWORDS:
        if any(kw in t for kw in keywords) and sid not in picked:
            picked.append(sid)
    # "core CPI" alone shouldn't also drag in headline CPI (and likewise PCE)
    # unless the user explicitly contrasts them.
    if "core" in t and "headline" not in t:
        if "CPILFESL" in picked and "CPIAUCSL" in picked:
            picked.remove("CPIAUCSL")
        if "PCEPILFE" in picked and "CPIAUCSL" in picked:
            picked.remove("CPIAUCSL")
    return picked


def _date_range(text: str) -> tuple[str, str, str]:
    t = text.lower()
    freq = "m"
    if "quarter" in t:
        freq = "q"
    elif "annual" in t or "yearly" in t:
        freq = "a"
    elif "daily" in t:
        freq = "d"

    m = re.search(r"(?:last|past|previous)\s+(\d{1,2})\s+years?", t)
    if m:
        n = int(m.group(1))
        return f"{2026 - n}-06-01", "2026-06-01", freq

    years = sorted({int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", text)})
    if len(years) >= 2:
        return f"{years[0]}-01-01", f"{years[-1]}-12-01", freq
    if len(years) == 1:
        return f"{years[0]}-01-01", "2026-06-01", freq
    return "2019-01-01", "2026-06-01", freq


def _mk_id(role: str, messages: list[dict]) -> str:
    return f"stub-{role}-{len(messages)}"


def _text(s: str) -> ModelResponse:
    return ModelResponse(text=s, stop_reason="end_turn")


def _tool(role: str, messages: list[dict], name: str, tool_input: dict) -> ModelResponse:
    return ModelResponse(
        tool_requests=[ToolRequest(id=_mk_id(role, messages), name=name, input=tool_input)],
        stop_reason="tool_use",
    )


# --- per-role planners --------------------------------------------------


def _plan_supervisor(messages: list[dict]) -> ModelResponse:
    query = _first_user_text(messages)
    done = [n.removeprefix("delegate_to_") for n in _assistant_tool_names(messages)]
    findings = "\n".join(_tool_result_texts(messages))

    analytical = any(h in query.lower() for h in _ANALYSIS_HINTS) or "risk" in query.lower()
    plan = (
        ["economic_data_agent", "research_agent", "risk_agent", "report_agent"]
        if analytical
        else ["economic_data_agent", "report_agent"]
    )

    for step in plan:
        if step in done:
            continue
        if step == "economic_data_agent":
            task = query
        else:
            task = f"User question: {query}\n\nFindings so far:\n{findings}"
        return _tool(f"supervisor-{step}", messages, f"delegate_to_{step}", {"task": task})

    # Everything delegated — final answer is the report agent's output.
    for txt in reversed(_tool_result_texts(messages)):
        try:
            payload = json.loads(txt)
            if payload.get("agent") == "report_agent":
                return _text(payload["output"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return _text(findings or "No report produced.")


def _plan_economic_data_agent(messages: list[dict]) -> ModelResponse:
    task = _first_user_text(messages)
    called = _assistant_tool_names(messages)
    results = _tool_result_texts(messages)
    start, end, freq = _date_range(task)

    fetched = any(n in called for n in ("get_series_observations", "compare_series"))
    if fetched:
        return _text(_summarize_observations(results))

    series = _series_in_text(task) or _match_series(task)

    if not series and "search_series" not in called:
        return _tool("econ", messages, "search_series", {"search_text": task[:120]})

    if not series and "search_series" in called:
        series = _series_from_search_results(results)[:1]

    if not series:
        return _text("Could not resolve any FRED series for this request.")

    if len(series) >= 2:
        return _tool(
            "econ", messages, "compare_series",
            {"series_ids": series[:4], "start_date": start, "end_date": end, "frequency": freq},
        )
    return _tool(
        "econ", messages, "get_series_observations",
        {"series_id": series[0], "start_date": start, "end_date": end, "frequency": freq},
    )


def _plan_research_agent(messages: list[dict]) -> ModelResponse:
    task = _first_user_text(messages)
    ids = _series_in_text(task) or _match_series(task)
    called = _assistant_tool_names(messages)

    # Pull source notes for up to two series, once.
    to_fetch = [sid for sid in ids[:2] if sid not in _metadata_fetched(messages)]
    if to_fetch and called.count("get_series_metadata") < 2:
        return _tool("research", messages, "get_series_metadata", {"series_id": to_fetch[0]})

    lines = [f"{sid}: standard FRED series; see source notes for methodology and revisions." for sid in ids]
    return _text("Framing:\n" + ("\n".join(lines) or "No series identified."))


def _plan_risk_agent(messages: list[dict]) -> ModelResponse:
    task = _first_user_text(messages).lower()
    if "recession" in task or ("unemployment" in task and "inflation" in task):
        signal = "elevated"
    elif "inflation" in task and "recession" not in task:
        signal = "easing"
    elif "rate" in task or "tighten" in task:
        signal = "rising"
    else:
        signal = "stable"
    return _text(
        f"RISK_SIGNAL: {signal}\n"
        "Rationale (illustrative offline heuristic): assessment derived from the "
        "indicator set in the task. Run with AGENT_BACKEND=anthropic for a "
        "model-generated analysis grounded in the fetched values."
    )


def _plan_report_agent(messages: list[dict]) -> ModelResponse:
    task = _first_user_text(messages)
    ids = _series_in_text(task)
    m = re.search(r"RISK_SIGNAL:\s*([A-Za-z]+)", task)
    signal = m.group(1) if m else "not assessed"
    body = (
        "Based on the fetched FRED series and the team's analysis, here is the "
        "answer to your question. (Offline stub narrative — the Anthropic "
        "backend produces the full write-up.)"
    )
    evidence = "\n".join(f"  - {sid}" for sid in ids) or "  - (none)"
    return _text(f"{body}\n\nEvidence\nSeries used:\n{evidence}\nRisk signal: {signal}")


# --- result parsing helpers -------------------------------------------


def _summarize_observations(result_texts: list[str]) -> str:
    lines = ["Data fetched:"]
    for txt in result_texts:
        try:
            payload = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if "series" in payload:
            for sid, obs in payload["series"].items():
                lines.append(_one_series_line(sid, obs))
        elif "observations" in payload:
            lines.append(_one_series_line(payload.get("series_id", "?"), payload["observations"]))
    return "\n".join(lines)


def _one_series_line(sid: str, obs: list[dict]) -> str:
    if not obs:
        return f"  {sid}: no observations"
    return (
        f"  {sid}: {len(obs)} points, {obs[0]['date']}..{obs[-1]['date']}, "
        f"start={obs[0]['value']} latest={obs[-1]['value']}"
    )


def _series_from_search_results(result_texts: list[str]) -> list[str]:
    for txt in result_texts:
        try:
            payload = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if "results" in payload and payload["results"]:
            return [r["series_id"] for r in payload["results"]]
    return []


def _metadata_fetched(messages: list[dict]) -> set[str]:
    got: set[str] = set()
    for m in messages:
        if m["role"] != "assistant" or not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_use" and b["name"] == "get_series_metadata":
                got.add(b["input"].get("series_id", ""))
    return got


_PLANNERS = {
    "supervisor": _plan_supervisor,
    "economic_data_agent": _plan_economic_data_agent,
    "research_agent": _plan_research_agent,
    "risk_agent": _plan_risk_agent,
    "report_agent": _plan_report_agent,
}


def plan(role: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
    planner = _PLANNERS.get(role)
    if planner is None:
        return _text(f"(stub) no planner for role '{role}'")
    return planner(messages)
