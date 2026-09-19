import { useEffect, useState } from "react";
import { API_BASE_URL, getMetadata, getObservations } from "../api/client";
import type { Frequency, MetadataResponse, ObservationsResponse } from "../api/types";
import { CURATED_BY_ID } from "../catalog";
import { presetRange, yearsBetween, type RangeSelection } from "../dates";
import type { ExplorerRequest, OpenExplorer } from "../explorer";
import {
  FREQ_OPTIONS,
  autoFrequency,
  describeChange,
  downloadCsv,
  formatValue,
  freqFromLabel,
  summarize,
} from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { Chip, CopyButton, DataTable, ErrorNotice, Skeleton, ToolTag } from "./common";
import { FrequencySelect, RangePicker, SeriesPicker } from "./controls";
import { SeriesChart } from "./SeriesChart";

type FreqChoice = "auto" | Frequency;

interface ChartResult {
  id: string;
  obs: ObservationsResponse;
  meta: MetadataResponse | null;
  freq: Frequency;
  range: RangeSelection;
}

async function loadChart(rawId: string, range: RangeSelection, choice: FreqChoice): Promise<ChartResult> {
  const id = rawId.trim().toUpperCase();
  // Metadata is best-effort: it picks a sensible frequency and supplies units,
  // but a failure there shouldn't hide the chart (the observations call will
  // report a genuinely unknown series itself).
  const meta = await getMetadata(id).catch(() => null);
  const freq =
    choice === "auto"
      ? autoFrequency(freqFromLabel(meta?.frequency), yearsBetween(range.start, range.end))
      : choice;
  const obs = await getObservations(id, { start_date: range.start, end_date: range.end, frequency: freq });
  return { id, obs, meta, freq, range };
}

export function ChartPanel({ request, open }: { request: ExplorerRequest | null; open: OpenExplorer }) {
  const [seriesId, setSeriesId] = useState("UNRATE");
  const [range, setRange] = useState<RangeSelection>(() => presetRange("5y"));
  const [freq, setFreq] = useState<FreqChoice>("auto");
  const { data, error, loading, run } = useAsyncAction(loadChart);

  useEffect(() => {
    if (request?.kind !== "chart") return;
    const fresh = presetRange("5y");
    setSeriesId(request.id);
    setRange(fresh);
    setFreq("auto");
    run(request.id, fresh, "auto");
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="panel-body">
      <p className="panel-caption">
        See how one indicator has moved over time.
        <ToolTag>POST /observations</ToolTag>
      </p>

      <form
        className="controls"
        onSubmit={(e) => {
          e.preventDefault();
          run(seriesId, range, freq);
        }}
      >
        <SeriesPicker value={seriesId} onChange={setSeriesId} />
        <RangePicker value={range} onChange={setRange} />
        <FrequencySelect value={freq} onChange={setFreq} />
        <button type="submit" className="btn btn-lime" disabled={loading || !seriesId.trim()}>
          {loading ? "Loading…" : "Show chart"}
        </button>
      </form>

      {loading && <Skeleton height={430} />}
      {error != null && <ErrorNotice error={error} />}
      {data && <ChartResultView result={data} open={open} />}
      {!data && !loading && error == null && (
        <p className="empty">
          Choose a series and press <strong>Show chart</strong> — or click any card above.
        </p>
      )}
    </div>
  );
}

function ChartResultView({ result, open }: { result: ChartResult; open: OpenExplorer }) {
  const { id, obs, meta, freq, range } = result;
  const units = meta?.units ?? "";
  const title = meta?.title ?? CURATED_BY_ID[id]?.name ?? id;
  const sum = summarize(obs.observations);
  const freqLabel = FREQ_OPTIONS.find((f) => f.value === freq)?.label ?? freq;

  if (!sum) {
    return <div className="notice">No observations in this date range — try a longer one.</div>;
  }

  const change = describeChange(sum.first, sum.latest, units);
  const arrow = change.direction === "up" ? "▲" : change.direction === "down" ? "▼" : "•";
  const curl = `curl -X POST ${API_BASE_URL}/observations \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({
    series_id: id,
    start_date: range.start,
    end_date: range.end,
    frequency: freq,
  })}'`;

  return (
    <div className="result">
      <div className="result-head">
        <div>
          <h3>{title}</h3>
          <div className="chips">
            <Chip tone="lime">{id}</Chip>
            {units && <Chip>{units}</Chip>}
            <Chip>{freqLabel}</Chip>
            {meta && <Chip>Updated {meta.last_updated.slice(0, 10)}</Chip>}
          </div>
        </div>
        <div className="result-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() =>
              downloadCsv(`${id}.csv`, ["date", "value"], obs.observations.map((o) => [o.date, o.value]))
            }
          >
            Download CSV
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => open({ kind: "compare", ids: [id], merge: false })}>
            Compare with…
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => open({ kind: "details", id })}>
            About this series
          </button>
        </div>
      </div>

      <dl className="stats">
        <div>
          <dt>Latest</dt>
          <dd>{formatValue(sum.latest, units)}</dd>
          <dd className="stat-sub">{sum.latestDate}</dd>
        </div>
        <div>
          <dt>Change over range</dt>
          <dd>
            <span className={`chg chg-${change.direction}`}>
              {arrow} {change.label}
            </span>
          </dd>
          <dd className="stat-sub">since {sum.firstDate}</dd>
        </div>
        <div>
          <dt>Highest</dt>
          <dd>{formatValue(sum.high, units)}</dd>
        </div>
        <div>
          <dt>Lowest</dt>
          <dd>{formatValue(sum.low, units)}</dd>
        </div>
      </dl>

      <SeriesChart series={{ [id]: obs.observations }} labels={{ [id]: title }} />

      {obs.note && <div className="notice">ℹ︎ {obs.note}</div>}

      <details className="disclose">
        <summary>View data table ({obs.observations.length} rows)</summary>
        <DataTable columns={["Date", units || "Value"]} rows={obs.observations.map((o) => [o.date, o.value])} />
      </details>
      <details className="disclose">
        <summary>Technical details</summary>
        <div className="tech">
          {obs._cost && (
            <p>
              Response size ≈ {obs._cost.estimated_tokens} tokens · demo allowance remaining{" "}
              {obs._cost.budget_remaining}
            </p>
          )}
          <pre>{curl}</pre>
          <CopyButton text={curl} label="Copy as curl" />
        </div>
      </details>
    </div>
  );
}
