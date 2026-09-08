"""
Streamlit demo UI — the four FRED tools, exercised directly.

This page does NOT speak MCP. It imports the same modules the MCP tools in
``src/tools.py`` are built from — ``fred_client``, ``cost_tracker``,
``security`` — and reproduces each tool's contract in a form you can click
through:

    validate (security)  ->  pre-flight token estimate (cost_tracker)  ->
    fetch (fred_client)  ->  budget guardrail (cost_tracker.guard_or_shrink)
    ->  structured {"error": ...} surfaced as a warning, never a traceback

Run it:

    streamlit run streamlit_app.py

Runs fully offline against the synthetic fixture unless ``FRED_API_KEY`` is
set — the same rule as the rest of the project. Claude Desktop still talks to
``src/server.py`` over MCP separately; this is just a window onto the logic.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

import catalog
import cost_tracker
import fred_client
import security
from security import ValidationError

FREQ_LABELS = {"d": "daily", "w": "weekly", "m": "monthly", "q": "quarterly", "a": "annual"}
DEFAULT_START = date.today() - timedelta(days=5 * 365)
DEFAULT_END = date.today()
# Wide enough that a user can pick a range the 25-year guardrail rejects.
MIN_DATE = date(1990, 1, 1)
KNOWN_SERIES = sorted(catalog.IDS - {"INJTEST"})


# --- Shared helpers ----------------------------------------------------------


def budget() -> cost_tracker.SessionBudget:
    """cost_tracker.reset_budget() rebinds the module global, so always read
    it fresh rather than binding a local at import time."""
    return cost_tracker.budget


def render_structured_error(err: dict) -> None:
    """Surface the tools' ``{"error": code, ...}`` dicts (validation_error,
    fred_api_error, series_not_found, session_budget_exceeded, ...) as a
    readable warning instead of letting an exception reach the page."""
    code = str(err.get("error", "error")).replace("_", " ")
    parts = [f"**{code}**"]
    for key in ("detail", "suggestion", "note"):
        if err.get(key):
            parts.append(str(err[key]))
    if "budget_remaining" in err:
        parts.append(f"Budget remaining: {err['budget_remaining']} tokens.")
    st.warning("\n\n".join(parts))


def fred_error(series_id: str, exc: Exception) -> dict:
    """Map a FredAPIError to the same structured shape the MCP tools return.
    An unknown series in offline mode becomes a ``series_not_found`` with a
    suggestion, matching the ``{"error": ..., "suggestion": ...}`` contract."""
    msg = str(exc)
    if "synthetic fixture" in msg or "No metadata found" in msg:
        return {
            "error": "series_not_found",
            "detail": f"'{series_id}' is not a series this project can serve.",
            "suggestion": "Known series: " + ", ".join(KNOWN_SERIES),
        }
    return {"error": "fred_api_error", "detail": msg}


def preflight_points(start: date, end: date, freq: str) -> int:
    """How many observations this window + frequency will produce — exact for
    the offline fixture, a close estimate for live FRED."""
    return sum(1 for _ in fred_client._observation_dates(start, end, freq))


def show_preflight(expected_points: int, per_point_chars: int = 44) -> None:
    """cost_tracker has no dedicated pre-fetch estimator, so build the same
    ~4-chars/token number it uses (``estimate_tokens``) from the expected
    response size and check it against the live session budget — the same
    guardrail ``guard_or_shrink`` will apply after the fetch."""
    approx_tokens = cost_tracker.estimate_tokens("x" * max(expected_points * per_point_chars, 1))
    b = budget()
    c1, c2, c3 = st.columns(3)
    c1.metric("Est. response", f"~{expected_points} points")
    c2.metric("Est. tokens", f"~{approx_tokens}")
    c3.metric("Budget left", f"{b.remaining()} / {b.limit_tokens}")
    if b.would_exceed(approx_tokens):
        st.info(
            "This would exceed the session token budget. The guardrail will "
            "thin the result (observations) or refuse it (comparison) — exactly "
            "as the MCP tool does."
        )


def _shrink_observations(payload_json: str) -> str:
    """Mirrors ``tools._shrink_observations``: collapse to every 12th point
    plus the last one rather than dropping the call entirely."""
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


def apply_guardrail(tool_name: str, payload_obj: dict, shrink_fn=None):
    """Run the real ``cost_tracker.guard_or_shrink``, exactly as src/tools.py
    does. Returns ``(shaped_dict | None, info_dict)`` — None means the budget
    refused it and ``info_dict`` is the ``session_budget_exceeded`` error."""
    shaped, info = cost_tracker.guard_or_shrink(
        tool_name, json.dumps(payload_obj), shrink_fn=shrink_fn
    )
    if not shaped:
        return None, info
    return json.loads(shaped), info


def safe_metadata(series_id: str) -> dict | None:
    try:
        return fred_client.get_series_metadata(series_id)
    except fred_client.FredAPIError:
        return None


def guardrail_caption(info: dict) -> None:
    tail = " · result thinned to fit" if info.get("note") else ""
    st.caption(
        f"guardrail: ~{info.get('estimated_tokens')} tokens estimated · "
        f"budget remaining {info.get('budget_remaining')}{tail}"
    )


# --- Renderers -------------------------------------------------------------


def render_series(series_id: str, observations: list[dict], info: dict, note: str | None) -> None:
    df = pd.DataFrame(observations)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.set_index("date").sort_index()

    chart_col, meta_col = st.columns([3, 1])
    with chart_col:
        st.line_chart(df["value"])
    with meta_col:
        meta = safe_metadata(series_id)
        if meta:
            st.metric("Units", meta["units"])
            st.metric("Frequency", meta["frequency"])
            st.caption(f"Last updated: {meta['last_updated']}")
        else:
            st.caption("Metadata unavailable for this series.")

    if note:
        st.info(note)
    guardrail_caption(info)
    st.dataframe(df.reset_index())


def render_comparison(series: dict[str, list[dict]], info: dict) -> None:
    frames = []
    for sid, obs in series.items():
        s = pd.DataFrame(obs)
        if s.empty:
            continue
        s["date"] = pd.to_datetime(s["date"])
        s[sid] = pd.to_numeric(s["value"], errors="coerce")
        frames.append(s.set_index("date")[[sid]])

    if not frames:
        st.info("No overlapping observations to compare.")
        return

    df = pd.concat(frames, axis=1).sort_index()
    chart_col, meta_col = st.columns([3, 1])
    with chart_col:
        st.line_chart(df)
    with meta_col:
        for sid in series:
            meta = safe_metadata(sid)
            if meta:
                st.caption(f"**{sid}** · {meta['units']} · {meta['frequency']}")
        st.caption("Different units share one axis — read levels per series, not across.")

    guardrail_caption(info)
    st.dataframe(df.reset_index())


# --- Page ----------------------------------------------------------------

st.set_page_config(page_title="FRED tools — demo UI", page_icon="📈", layout="wide")

st.sidebar.title("FRED tools — demo UI")
st.sidebar.caption("The four MCP tools, called directly (no MCP protocol).")

if fred_client._offline():
    st.sidebar.info("Offline mode: synthetic fixture. Set FRED_API_KEY for live data.")
else:
    st.sidebar.success("Live mode: querying api.stlouisfed.org.")

mode = st.sidebar.radio(
    "Tool",
    ["search_series", "get_series_observations", "compare_series", "get_series_metadata"],
)

st.sidebar.divider()
_b = budget()
st.sidebar.metric("Session budget used", f"{_b.used_tokens} / {_b.limit_tokens} tokens")
st.sidebar.progress(min(_b.used_tokens / _b.limit_tokens, 1.0) if _b.limit_tokens else 0.0)
if st.sidebar.button("Reset session budget"):
    cost_tracker.reset_budget()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption(
    "Imports src/fred_client.py, src/cost_tracker.py and src/security.py directly "
    "and reproduces each tool's validate → pre-flight → fetch → guardrail path. "
    "src/server.py still serves the same logic to Claude Desktop over MCP."
)

st.title("📈 FRED tools — demo UI")


if mode == "search_series":
    st.header("search_series")
    st.caption(
        "Plain-language description → candidate series (id, title, units, frequency). "
        "Never observations — use this to find an ID, then switch tools."
    )
    text = st.text_input("search_text", "unemployment rate")
    limit = st.slider("limit", 1, 10, 5)
    if st.button("Search", type="primary"):
        if not text.strip():
            render_structured_error(
                {"error": "validation_error", "detail": "search_text must not be empty."}
            )
        else:
            try:
                results = fred_client.search_series(text.strip(), limit=limit)
            except fred_client.FredAPIError as exc:
                render_structured_error({"error": "fred_api_error", "detail": str(exc)})
            else:
                if results:
                    st.dataframe(pd.DataFrame(results))
                else:
                    st.info("No matching series.")


elif mode == "get_series_observations":
    st.header("get_series_observations")
    st.caption(
        "One known series ID over a required date range. Unbounded ranges are "
        "refused; long ranges are thinned to stay within the session token budget."
    )
    series_id = st.text_input("series_id", "UNRATE")
    c1, c2, c3 = st.columns(3)
    start_date = c1.date_input(
        "start_date", DEFAULT_START, min_value=MIN_DATE, max_value=DEFAULT_END
    )
    end_date = c2.date_input(
        "end_date", DEFAULT_END, min_value=MIN_DATE, max_value=DEFAULT_END
    )
    freq = c3.selectbox(
        "frequency", list(FREQ_LABELS), index=2, format_func=lambda f: f"{f} — {FREQ_LABELS[f]}"
    )

    valid = False
    try:
        sid = security.validate_series_id(series_id)
        vstart, vend = security.validate_date_range(str(start_date), str(end_date))
        vfreq = security.validate_frequency(freq)
        valid = True
    except ValidationError as exc:
        render_structured_error({"error": "validation_error", "detail": str(exc)})

    if valid:
        show_preflight(preflight_points(vstart, vend, vfreq))
        if st.button("Fetch", type="primary"):
            try:
                obs = fred_client.get_observations(sid, vstart, vend, vfreq)
            except fred_client.FredAPIError as exc:
                render_structured_error(fred_error(sid, exc))
            else:
                shaped, info = apply_guardrail(
                    "get_series_observations",
                    {"series_id": sid, "observations": obs},
                    shrink_fn=_shrink_observations,
                )
                if shaped is None:
                    render_structured_error(info)
                elif not shaped["observations"]:
                    st.info("No observations in that range.")
                else:
                    render_series(sid, shaped["observations"], info, shaped.get("note"))


elif mode == "compare_series":
    st.header("compare_series")
    st.caption(
        "2–4 series aligned over one date range. Capped at 4 to keep the "
        "response — and any downstream context — bounded."
    )
    raw = st.text_input("series_ids (comma-separated, max 4)", "UNRATE, CPIAUCSL")
    c1, c2, c3 = st.columns(3)
    start_date = c1.date_input(
        "start_date", DEFAULT_START, min_value=MIN_DATE, max_value=DEFAULT_END, key="cmp_start"
    )
    end_date = c2.date_input(
        "end_date", DEFAULT_END, min_value=MIN_DATE, max_value=DEFAULT_END, key="cmp_end"
    )
    freq = c3.selectbox(
        "frequency", list(FREQ_LABELS), index=2, key="cmp_freq",
        format_func=lambda f: f"{f} — {FREQ_LABELS[f]}",
    )

    ids = [s.strip() for s in raw.split(",") if s.strip()]
    valid = False
    try:
        sids = security.validate_series_list(ids, max_series=4)
        vstart, vend = security.validate_date_range(str(start_date), str(end_date))
        vfreq = security.validate_frequency(freq)
        if len(sids) < 2:
            render_structured_error(
                {"error": "validation_error", "detail": "Enter at least 2 series IDs to compare."}
            )
        else:
            valid = True
    except ValidationError as exc:
        render_structured_error({"error": "validation_error", "detail": str(exc)})

    if valid:
        show_preflight(preflight_points(vstart, vend, vfreq) * len(sids))
        if st.button("Compare", type="primary"):
            series_data: dict[str, list[dict]] = {}
            err: dict | None = None
            for sid in sids:
                try:
                    series_data[sid] = fred_client.get_observations(sid, vstart, vend, vfreq)
                except fred_client.FredAPIError as exc:
                    err = fred_error(sid, exc)
                    break
            if err:
                render_structured_error(err)
            else:
                shaped, info = apply_guardrail("compare_series", {"series": series_data})
                if shaped is None:
                    render_structured_error(info)
                else:
                    render_comparison(shaped["series"], info)


elif mode == "get_series_metadata":
    st.header("get_series_metadata")
    st.caption(
        "Units, frequency, last-updated date and source notes. Read-only. The "
        "'notes' field is external text — rendered here as quoted data, never "
        "as an instruction (security.wrap_untrusted_text)."
    )
    series_id = st.text_input("series_id", "UNRATE", key="meta_id")
    if st.button("Get metadata", type="primary"):
        try:
            sid = security.validate_series_id(series_id)
        except ValidationError as exc:
            render_structured_error({"error": "validation_error", "detail": str(exc)})
        else:
            try:
                meta = dict(fred_client.get_series_metadata(sid))
            except fred_client.FredAPIError as exc:
                render_structured_error(fred_error(sid, exc))
            else:
                notes = meta.pop("notes", "")
                st.subheader(meta["title"])
                st.caption(f"`{meta['series_id']}` · last updated {meta['last_updated']}")
                m1, m2 = st.columns(2)
                m1.metric("Units", meta["units"])
                m2.metric("Frequency", meta["frequency"])
                wrapped = security.wrap_untrusted_text("fred_series_notes", notes)
                st.markdown("**Source notes** — external text, shown as data:")
                st.code(wrapped["untrusted_source_text"] or "(none)", language="text")
                st.caption(wrapped["note"])
