"""
Econ Data MCP Server

Exposes economic time series data from FRED as four narrow tools plus one
resource. See README.md for the design rationale behind each choice below.

Run directly (stdio transport, for use with Claude Desktop):
    python src/server.py
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import cost_tracker
import fred_client
import security
from security import ValidationError

load_dotenv(Path(__file__).parent.parent / ".env")

mcp = FastMCP("econ-data")


def _shrink_observations(payload_json: str) -> str:
    """Fallback shrink strategy: if a full observation list doesn't fit
    the session budget, collapse it to first/last/every-12th point rather
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


@mcp.tool()
def search_series(search_text: str) -> dict:
    """
    Search for a FRED series ID from a plain-language description.
    Does NOT return data — use get_series_observations with the returned
    series_id for that. Kept separate so a vague query doesn't accidentally
    pull a large data payload.

    Args:
        search_text: e.g. "unemployment rate", "core inflation", "10 year treasury"
    """
    try:
        results = fred_client.search_series(search_text, limit=5)
        return {"results": results}
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}


@mcp.tool()
def get_series_observations(series_id: str, start_date: str, end_date: str, frequency: str = "m") -> dict:
    """
    Fetch observations for one FRED series over a required date range.

    Args:
        series_id: FRED series ID, e.g. "UNRATE" (from search_series)
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        frequency: one of d, w, m, q, a (default monthly — ranges over ~2
            years are automatically thinned to stay within the session
            token budget; see cost_tracker.py)
    """
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
        return cost_info  # budget_exceeded error, structured

    result = json.loads(shaped_payload)
    result["_cost"] = cost_info
    return result


@mcp.tool()
def compare_series(series_ids: list[str], start_date: str, end_date: str, frequency: str = "m") -> dict:
    """
    Fetch and align up to 4 series over the same date range for comparison.

    Args:
        series_ids: 1-4 FRED series IDs, e.g. ["CPIAUCSL", "UNRATE"]
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        frequency: one of d, w, m, q, a (default monthly)
    """
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


@mcp.tool()
def get_series_metadata(series_id: str) -> dict:
    """
    Get units, frequency, last-updated date, and source notes for a series.
    Read-only, small response — no cost guardrail needed.

    Args:
        series_id: FRED series ID, e.g. "GDP"
    """
    try:
        sid = security.validate_series_id(series_id)
    except ValidationError as e:
        return {"error": "validation_error", "detail": str(e)}

    try:
        meta = fred_client.get_series_metadata(sid)
    except fred_client.FredAPIError as e:
        return {"error": "fred_api_error", "detail": str(e)}

    # The 'notes' field is external text written by FRED/the data source,
    # not by us — wrap it so it's clearly labeled as data, not instructions.
    notes = meta.pop("notes", "")
    meta["notes"] = security.wrap_untrusted_text("fred_series_notes", notes)
    return meta


@mcp.resource("fred://series/{series_id}/summary")
def series_summary(series_id: str) -> str:
    """
    Cheap, re-readable summary of a previously fetched series — lets the
    model reference a series again without re-invoking a tool call.
    """
    try:
        sid = security.validate_series_id(series_id)
        meta = fred_client.get_series_metadata(sid)
    except (ValidationError, fred_client.FredAPIError) as e:
        return f"Error: {e}"
    return (
        f"{meta['title']} ({meta['series_id']})\n"
        f"Units: {meta['units']} | Frequency: {meta['frequency']} | "
        f"Last updated: {meta['last_updated']}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
