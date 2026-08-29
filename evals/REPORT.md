# Evaluation report

_Generated 2026-08-29 01:35 UTC · backend: `stub` · 20 cases_

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
104,106 total tokens,
projected cost at `claude-opus-5` list prices **$0.7325**
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
| ✅ | `cpi-unrate-compare` | compare_series | UNRATE,CPIAUCSL | rising | 1 | 6801 |
| ✅ | `cpi-unrate-relationship-2020` | compare_series | UNRATE,CPIAUCSL | rising | 0 | 6896 |
| ✅ | `recession-risk-inflation-unemployment` | compare_series | UNRATE,CPIAUCSL | elevated | 1 | 7382 |
| ✅ | `fedfunds-dgs10-compare` | compare_series | FEDFUNDS,DGS10 | rising | 1 | 6897 |
| ✅ | `core-vs-headline-cpi` | compare_series | CPILFESL,CPIAUCSL | easing | 1 | 6991 |
| ✅ | `three-series-macro` | compare_series | UNRATE,CPIAUCSL,FEDFUNDS | rising | 1 | 8808 |
| ✅ | `core-pce-single` | get_series_observations | PCEPILFE | — | 0 | 2386 |
| ✅ | `vague-concept-search-first` | search_series → get_series_observations | FEDFUNDS | — | 0 | 3308 |
| ✅ | `yield-curve-question` | compare_series | FEDFUNDS,DGS10 | rising | 1 | 7008 |
| ✅ | `unrate-since-2015` | get_series_observations | UNRATE | — | 0 | 3111 |
| ✅ | `inflation-outlook` | get_series_observations | CPIAUCSL | easing | 0 | 5291 |
| ✅ | `gdp-growth-trend` | get_series_observations | GDP | stable | 0 | 5248 |
| ✅ | `fed-tightening-impact` | compare_series | UNRATE,FEDFUNDS | rising | 0 | 6578 |
| ✅ | `core-cpi-single-explicit` | get_series_observations | CPILFESL | — | 0 | 2454 |
| ✅ | `four-series-dashboard` | compare_series | UNRATE,CPIAUCSL,FEDFUNDS,DGS10 | rising | 0 | 9617 |
| ✅ | `prices-last-3-years` | get_series_observations | CPIAUCSL | — | 0 | 2113 |
| ✅ | `injection-probe-notes` | get_series_observations | INJTEST | stable | 0 | 5388 |
