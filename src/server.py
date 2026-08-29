"""
Econ Data MCP Server

Exposes economic time series data from FRED as four narrow tools plus one
resource. The tool logic lives in `tools.py` so the MCP surface here and the
multi-agent orchestrator in `agents/` share one implementation. See README.md
for the design rationale.

Run directly (stdio transport, for use with Claude Desktop):
    python src/server.py
"""

from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import audit_log
import fred_client
import rate_limit
import security
import tools

load_dotenv(Path(__file__).parent.parent / ".env")

mcp = FastMCP("econ-data")

# One stdio server process serves one client, so a fixed client id is fine
# here; a multi-tenant deployment would key this on the transport/session.
_CLIENT_ID = "mcp-stdio"


def _guarded(tool_name: str, arguments: dict) -> dict:
    """Rate-limit the untrusted MCP boundary, then run (and audit-log) the
    shared tool implementation."""
    rejected = rate_limit.guard(_CLIENT_ID, tool_name)
    if rejected is not None:
        audit_log.record("rate_limited", caller=_CLIENT_ID, tool=tool_name)
        return rejected
    return tools.call_tool(tool_name, arguments, caller=_CLIENT_ID)


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
    return _guarded("search_series", {"search_text": search_text})


@mcp.tool()
def get_series_observations(
    series_id: str, start_date: str, end_date: str, frequency: str = "m"
) -> dict:
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
    return _guarded("get_series_observations", {
        "series_id": series_id, "start_date": start_date,
        "end_date": end_date, "frequency": frequency,
    })


@mcp.tool()
def compare_series(
    series_ids: list[str], start_date: str, end_date: str, frequency: str = "m"
) -> dict:
    """
    Fetch and align up to 4 series over the same date range for comparison.

    Args:
        series_ids: 1-4 FRED series IDs, e.g. ["CPIAUCSL", "UNRATE"]
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        frequency: one of d, w, m, q, a (default monthly)
    """
    return _guarded("compare_series", {
        "series_ids": series_ids, "start_date": start_date,
        "end_date": end_date, "frequency": frequency,
    })


@mcp.tool()
def get_series_metadata(series_id: str) -> dict:
    """
    Get units, frequency, last-updated date, and source notes for a series.
    Read-only, small response — no cost guardrail needed.

    Args:
        series_id: FRED series ID, e.g. "GDP"
    """
    return _guarded("get_series_metadata", {"series_id": series_id})


@mcp.resource("fred://series/{series_id}/summary")
def series_summary(series_id: str) -> str:
    """
    Cheap, re-readable summary of a previously fetched series — lets the
    model reference a series again without re-invoking a tool call.
    """
    try:
        sid = security.validate_series_id(series_id)
        meta = fred_client.get_series_metadata(sid)
    except (security.ValidationError, fred_client.FredAPIError) as e:
        return f"Error: {e}"
    return (
        f"{meta['title']} ({meta['series_id']})\n"
        f"Units: {meta['units']} | Frequency: {meta['frequency']} | "
        f"Last updated: {meta['last_updated']}"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
