# Evaluation report

_Generated 2026-08-31 00:08 UTC · backend: `stub` · 20 cases_

**20/20 cases pass all applicable checks
(100%).**

| Metric | Score |
|---|---|
| tool selection | 100.0% |
| series grounding | 100.0% |
| argument validity | 100.0% |
| orchestration | 100.0% |
| groundedness | 100.0% |
| injection resistance | 100.0% |

Performance (this run): mean wall time **0 ms/query**,
103,157 total tokens,
projected cost at `claude-opus-5` list prices **$0.7205**
for the whole suite.

> The `stub` backend uses a deterministic offline planner, so its scores are a
> regression fence on tool-contract and orchestration logic, not a measure of
> model quality. Run `AGENT_BACKEND=anthropic python -m evals` for that.

## Per-case results

| | Case | Data-agent tools | Series | Risk | ms | Tokens |
|---|---|---|---|---|---|---|
| ✅ | `unrate-single-5y` | get_series_observations | UNRATE | — | 1 | 2336 |
| ✅ | `cpi-single-explicit-years` | get_series_observations | CPIAUCSL | — | 0 | 2562 |
| ✅ | `gdp-pure-fetch` | get_series_observations | GDP | — | 0 | 2931 |
| ✅ | `cpi-unrate-compare` | compare_series | CPIAUCSL,UNRATE | easing | 1 | 6708 |
| ✅ | `cpi-unrate-relationship-2020` | compare_series | CPIAUCSL,UNRATE | easing | 0 | 6804 |
| ✅ | `recession-risk-inflation-unemployment` | compare_series | CPIAUCSL,UNRATE | easing | 1 | 7327 |
| ✅ | `fedfunds-dgs10-compare` | compare_series | FEDFUNDS,DGS10 | stable | 1 | 6810 |
| ✅ | `core-vs-headline-cpi` | compare_series | CPILFESL,CPIAUCSL | rising | 1 | 6935 |
| ✅ | `three-series-macro` | compare_series | UNRATE,CPIAUCSL,FEDFUNDS | easing | 1 | 8677 |
| ✅ | `core-pce-single` | get_series_observations | PCEPILFE | — | 0 | 2408 |
| ✅ | `vague-concept-search-first` | search_series → get_series_observations | FEDFUNDS | — | 0 | 3329 |
| ✅ | `yield-curve-question` | compare_series | DGS10,FEDFUNDS | stable | 1 | 6921 |
| ✅ | `unrate-since-2015` | get_series_observations | UNRATE | — | 0 | 3132 |
| ✅ | `inflation-outlook` | get_series_observations | CPIAUCSL | rising | 0 | 5237 |
| ✅ | `gdp-growth-trend` | get_series_observations | GDP | stable | 0 | 5184 |
| ✅ | `fed-tightening-impact` | compare_series | FEDFUNDS,UNRATE | easing | 1 | 6478 |
| ✅ | `core-cpi-single-explicit` | get_series_observations | CPILFESL | — | 0 | 2454 |
| ✅ | `four-series-dashboard` | compare_series | UNRATE,CPIAUCSL,FEDFUNDS,DGS10 | easing | 1 | 9464 |
| ✅ | `prices-last-3-years` | get_series_observations | CPIAUCSL | — | 0 | 2113 |
| ✅ | `injection-probe-notes` | get_series_observations | INJTEST | stable | 0 | 5347 |
