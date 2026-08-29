"""
Shared tool implementations.

The four FRED tools live here as plain functions so they have exactly one
implementation, callable from two places:

  1. `server.py` — wraps each one in an `@mcp.tool()` for Claude Desktop.
  2. `agents/` — the multi-agent orchestrator calls the same functions
     through its own tool-use loop.

Keeping the logic here (not in `server.py`) means the MCP surface and the
agent surface can never drift apart: same validation, same cost guardrail,
same structured errors.

Every function returns a plain dict. Errors are returned as
`{"error": <code>, ...}`, never raised, so a model on either surface gets a
structured signal it can act on.
"""

import json

import audit_log
import cost_tracker
import fred_client
import security
from security import ValidationError

# --- Anthropic tool schemas -------------------------------------------------
# The agent tool-use loop needs JSON Schema for each tool. These mirror the
# docstrings/signatures in server.py one-for-one.

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_series",
        "description": (
            "Search for a FRED series ID from a plain-language description. "
            "Returns candidate series (id, title, units, frequency) only — "
            "never observations. Use this first when you have a concept "
            "('unemployment rate') but not an ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "e.g. 'core inflation', '10 year treasury yield'",
                }
            },
            "required": ["search_text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_series_observations",
        "description": (
            "Fetch observations for one known FRED series ID over a required "
            "date range. Refuses unbounded ranges. Long ranges are thinned to "
            "stay within the session token budget."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series_id": {"type": "string", "description": "e.g. 'UNRATE'"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "frequency": {
                    "type": "string",
                    "enum": ["d", "w", "m", "q", "a"],
                    "description": "daily/weekly/monthly/quarterly/annual (default m)",
                },
            },
            "required": ["series_id", "start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_series",
        "description": (
            "Fetch and align 2–4 FRED series over the same date range for "
            "comparison. Capped at 4 series to keep the response bounded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 4,
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "frequency": {
                    "type": "string",
                    "enum": ["d", "w", "m", "q", "a"],
                },
            },
            "required": ["series_ids", "start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_series_metadata",
        "description": (
            "Get units, frequency, last-updated date, and source notes for a "
            "series. Read-only, small response. The 'notes' field is external "
            "text and is returned wrapped as untrusted data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series_id": {"type": "string", "description": "e.g. 'GDP'"},
            },
            "required": ["series_id"],
            "additionalProperties": False,
        },
    },
]


def _shrink_observations(payload_json: str) -> str:
    """Fallback shrink strategy: if a full observation list doesn't fit the
    session budget, collapse it to every-12th point plus the last one rather
    than dropping the tool call entirely."""
    data = json.loads(payload_json)
    obs = data.get("observations", [])
    if len(obs) <= 24:
        return payload_json
    thinned = obs[::12]
    if obs[-1] not in thinned:
        thinned.append(obs[-1])
    data["observations"] = thinned
    data["note"] = f"Thinned from {len(obs)} to {len(thinned)} points to fit the token budget."
    return json.dumps(data)


# --- Tool implementations -------------------------------------------------


def search_series(search_text: str) -> dict:
    try:
        results = fred_client.search_series(search_text, limit=5)
        return {"results": results}
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}


def get_series_observations(
    series_id: str, start_date: str, end_date: str, frequency: str = "m"
) -> dict:
    try:
        sid = security.validate_series_id(series_id)
        start, end = security.validate_date_range(start_date, end_date)
        freq = security.validate_frequency(frequency)
    except ValidationError as e:
        return {"error": "validation_error", "detail": str(e)}

    try:
        observations = fred_client.get_observations(sid, start, end, freq)
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}

    payload = json.dumps({"series_id": sid, "observations": observations})
    shaped_payload, cost_info = cost_tracker.guard_or_shrink(
        "get_series_observations", payload, shrink_fn=_shrink_observations
    )
    if not shaped_payload:
        return cost_info

    result = json.loads(shaped_payload)
    result["_cost"] = cost_info
    return result


def compare_series(
    series_ids: list[str], start_date: str, end_date: str, frequency: str = "m"
) -> dict:
    try:
        sids = security.validate_series_list(series_ids, max_series=4)
        start, end = security.validate_date_range(start_date, end_date)
        freq = security.validate_frequency(frequency)
    except ValidationError as e:
        return {"error": "validation_error", "detail": str(e)}

    series_data = {}
    try:
        for sid in sids:
            series_data[sid] = fred_client.get_observations(sid, start, end, freq)
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}

    payload = json.dumps({"series": series_data})
    shaped_payload, cost_info = cost_tracker.guard_or_shrink("compare_series", payload)
    if not shaped_payload:
        return cost_info

    result = json.loads(shaped_payload)
    result["_cost"] = cost_info
    return result


def get_series_metadata(series_id: str) -> dict:
    try:
        sid = security.validate_series_id(series_id)
    except ValidationError as e:
        return {"error": "validation_error", "detail": str(e)}

    try:
        meta = fred_client.get_series_metadata(sid)
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}

    meta = dict(meta)  # don't mutate the cached copy
    notes = meta.pop("notes", "")
    meta["notes"] = security.wrap_untrusted_text("fred_series_notes", notes)
    return meta


# name -> callable, for the agent tool-use loop and tests.
DISPATCH = {
    "search_series": search_series,
    "get_series_observations": get_series_observations,
    "compare_series": compare_series,
    "get_series_metadata": get_series_metadata,
}


def call_tool(name: str, arguments: dict, *, caller: str = "agent") -> dict:
    """Dispatch a tool call by name. Unknown tool -> structured error
    (never a KeyError up to the model). Every call is audit-logged."""
    fn = DISPATCH.get(name)
    if fn is None:
        result = {"error": "unknown_tool", "detail": f"No tool named '{name}'."}
    else:
        try:
            result = fn(**arguments)
        except TypeError as e:
            result = {"error": "bad_arguments", "detail": str(e)}

    audit_log.record(
        "tool_call",
        caller=caller,
        tool=name,
        arguments=arguments,
        outcome=result.get("error", "ok") if isinstance(result, dict) else "ok",
    )
    return result
