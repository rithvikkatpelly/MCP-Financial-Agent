"""FastAPI entry point for the Econ Data API.

A second, independently deployable interface over the *same* tool logic the
MCP server uses. Every endpoint delegates to ``src/tools.py`` — the one
implementation that composes ``fred_client`` (fetch + cache), ``security``
(input validation), and ``cost_tracker`` (the per-session token guardrail).
The MCP server (``src/server.py``) is a sibling caller of that module and is
completely unaffected by this package.

    validate (security)  ->  fetch (fred_client)  ->  guardrail (cost_tracker)
    ->  tools.py returns {"error": code, ...} on failure, never raises
    ->  this layer maps that dict to an HTTP status code

Run it (from the backend/ directory):

    uvicorn app.main:app --reload

Interactive docs at http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import fred_client
import tools
from app.schemas import (
    CompareRequest,
    MetadataResponse,
    ObservationsRequest,
    SearchRequest,
    SearchResponse,
)
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "HTTP interface over the same FRED tool logic as the MCP server "
        "(src/server.py). Offline synthetic fixture unless FRED_API_KEY is set."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Structured-error translation ----------------------------------------

# tools.* returns {"error": <code>, ...} instead of raising. Map each code to
# the HTTP status that fits it; anything unrecognised is a 500.
_ERROR_STATUS = {
    "validation_error": 422,
    "bad_arguments": 422,
    "series_not_found": 404,
    "fred_api_error": 502,
    "news_api_error": 502,
    "session_budget_exceeded": 429,
    "unknown_tool": 500,
}


def _unwrap(result: dict) -> dict:
    """Return ``result`` on success; raise ``HTTPException`` with the
    structured error dict as ``detail`` on failure."""
    if "error" not in result:
        return result

    err = dict(result)
    detail_text = str(err.get("detail") or "").lower()
    # Offline: an unknown series surfaces as a generic fred_api_error from the
    # fixture ("No synthetic fixture for series 'X'"). That's really a 404.
    if err["error"] == "fred_api_error" and (
        "synthetic fixture" in detail_text or "no metadata found" in detail_text
    ):
        err = {
            "error": "series_not_found",
            "detail": err.get("detail"),
            "suggestion": "Call POST /search to find a valid series ID.",
        }

    raise HTTPException(status_code=_ERROR_STATUS.get(err["error"], 500), detail=err)


# --- Endpoints — one per MCP tool ---------------------------------------


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness check. ``offline`` reflects whether FRED calls are served from
    the synthetic fixture (no ``FRED_API_KEY``) or the live API."""
    return {"status": "ok", "offline": fred_client._offline()}


@app.post("/search", response_model=SearchResponse, tags=["tools"])
def search(req: SearchRequest) -> dict:
    """`search_series` — plain-language concept → candidate series IDs. Never
    returns observations."""
    return _unwrap(tools.search_series(req.search_text))


@app.post("/observations", tags=["tools"])
def observations(req: ObservationsRequest) -> dict:
    """`get_series_observations` — one series over a required date range.
    Returns ``{"series_id", "observations": [{"date","value"}], "_cost"}``.
    Long ranges are thinned to fit the token budget (a ``"note"`` says so);
    a range that still doesn't fit is a 429."""
    return _unwrap(
        tools.get_series_observations(
            req.series_id, req.start_date, req.end_date, req.frequency
        )
    )


@app.post("/compare", tags=["tools"])
def compare(req: CompareRequest) -> dict:
    """`compare_series` — 2–4 series aligned over one date range. Returns
    ``{"series": {series_id: [{"date","value"}]}, "_cost"}``."""
    return _unwrap(
        tools.compare_series(
            req.series_ids, req.start_date, req.end_date, req.frequency
        )
    )


@app.get("/metadata/{series_id}", response_model=MetadataResponse, tags=["tools"])
def metadata(series_id: str) -> dict:
    """`get_series_metadata` — units, frequency, last-updated, source notes.
    ``notes`` comes back wrapped as untrusted data (never an instruction)."""
    return _unwrap(tools.get_series_metadata(series_id))
