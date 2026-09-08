"""Request/response models for the Econ Data HTTP API.

The response shapes mirror what ``src/tools.py`` returns one-for-one, so the
HTTP surface stays a thin translation of the shared tool logic rather than a
reshaping of it. ``extra="allow"`` keeps forward-compatible fields the
guardrail may attach (``_cost``, ``note``) without a schema change.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Frequency = Literal["d", "w", "m", "q", "a"]


# --- Requests --------------------------------------------------------------


class SearchRequest(BaseModel):
    # Mirrors the MCP `search_series` tool contract: concept in, candidates
    # out. The result cap (5) is fixed in tools.py, same as the MCP surface.
    search_text: str = Field(
        ..., min_length=1, description="Plain-language concept, e.g. 'core inflation'"
    )


class ObservationsRequest(BaseModel):
    series_id: str = Field(..., description="FRED series ID, e.g. 'UNRATE'")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    frequency: Frequency = "m"


class CompareRequest(BaseModel):
    series_ids: list[str] = Field(..., min_length=1, max_length=4)
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    frequency: Frequency = "m"


# --- Responses ------------------------------------------------------------


class SeriesMatch(BaseModel):
    series_id: str
    title: str
    frequency: str
    units: str


class SearchResponse(BaseModel):
    results: list[SeriesMatch]


class Observation(BaseModel):
    date: str
    value: str  # FRED returns values as strings; "." (missing) is filtered upstream


class ObservationsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")  # _cost, note

    series_id: str
    observations: list[Observation]


class CompareResponse(BaseModel):
    model_config = ConfigDict(extra="allow")  # _cost, note

    series: dict[str, list[Observation]]


class UntrustedText(BaseModel):
    untrusted_source: str
    untrusted_source_text: str
    note: str


class MetadataResponse(BaseModel):
    series_id: str
    title: str
    units: str
    frequency: str
    last_updated: str
    notes: UntrustedText


class ErrorResponse(BaseModel):
    """Body of every 4xx/5xx — the same structured dict ``tools.py`` produces,
    surfaced under ``detail`` by FastAPI."""

    error: str
    detail: str | None = None
    suggestion: str | None = None
