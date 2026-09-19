import { useEffect, useId, useState } from "react";
import { compareSeries, getMetadata } from "../api/client";
import type { CompareResponse, Frequency, MetadataResponse } from "../api/types";
import { COMPARISONS, CURATED, CURATED_BY_ID } from "../catalog";
import { presetRange, yearsBetween, type RangeSelection } from "../dates";
import type { ExplorerRequest } from "../explorer";
import {
  FREQ_OPTIONS,
  autoFrequency,
  coarsest,
  describeChange,
  downloadCsv,
  formatValue,
  freqFromLabel,
  summarize,
} from "../format";
import { useAsyncAction } from "../useAsyncAction";
import { Chip, DataTable, ErrorNotice, Field, Skeleton, ToolTag } from "./common";
import { FrequencySelect, RangePicker } from "./controls";
import { PALETTE, SeriesChart } from "./SeriesChart";

type FreqChoice = "auto" | Frequency;
const MAX_SERIES = 4;

interface CompareResult {
  ids: string[];
  cmp: CompareResponse;
  metas: (MetadataResponse | null)[];
  freq: Frequency;
}

async function loadCompare(ids: string[], range: RangeSelection, choice: FreqChoice): Promise<CompareResult> {
  const metas = await Promise.all(ids.map((id) => getMetadata(id).catch(() => null)));
  // Compared series must share one frequency, and FRED can only lower it — so
  // "automatic" means the coarsest of the group.
  const freq =
    choice === "auto"
      ? autoFrequency(coarsest(metas.map((m) => freqFromLabel(m?.frequency))), yearsBetween(range.start, range.end))
      : choice;
  const cmp = await compareSeries(ids, { start_date: range.start, end_date: range.end, frequency: freq });
  return { ids, cmp, metas, freq };
}

function nameFor(id: string, meta: MetadataResponse | null): string {
  const n = CURATED_BY_ID[id]?.name ?? meta?.title ?? id;
  return n.length > 34 ? `${n.slice(0, 33)}…` : n;
}

const clean = (s: string) => s.trim().toUpperCase();

export function ComparePanel({ request }: { request: ExplorerRequest | null }) {
  const [ids, setIds] = useState<string[]>(["UNRATE", "CPIAUCSL"]);
  const [draft, setDraft] = useState("");
  const [range, setRange] = useState<RangeSelection>(() => presetRange("5y"));
  const [freq, setFreq] = useState<FreqChoice>("auto");
  const [rebase, setRebase] = useState(true);
  const { data, error, loading, run } = useAsyncAction(loadCompare);
  const listId = useId();

  useEffect(() => {
    if (request?.kind !== "compare") return;
    const incoming = request.ids.map(clean);
    const next = request.merge
      ? [...new Set([...ids, ...incoming])].slice(0, MAX_SERIES)
      : incoming.slice(0, MAX_SERIES);
    const fresh = presetRange("5y");
    setIds(next);
    setRange(fresh);
    setFreq("auto");
    if (next.length >= 2) run(next, fresh, "auto");
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = () => {
    const id = clean(draft);
    if (id && !ids.includes(id) && ids.length < MAX_SERIES) setIds([...ids, id]);
    setDraft("");
  };

  return (
    <div className="panel-body">
      <p className="panel-caption">
        Put 2–{MAX_SERIES} indicators on one chart.
        <ToolTag>POST /compare</ToolTag>
      </p>

      <form
        className="controls"
        onSubmit={(e) => {
          e.preventDefault();
          run(ids, range, freq);
        }}
      >
        <div className="field field-wide">
          <span className="field-label">Series to compare</span>
          <div className="pill-input">
            {ids.map((id, i) => (
              <span key={id} className="pill" style={{ borderColor: PALETTE[i % PALETTE.length] }}>
                <i style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden="true" />
                {CURATED_BY_ID[id]?.name ?? id}
                <button type="button" aria-label={`Remove ${id}`} onClick={() => setIds(ids.filter((x) => x !== id))}>
                  ×
                </button>
              </span>
            ))}
            {ids.length < MAX_SERIES && (
              <>
                <input
                  value={draft}
                  list={listId}
                  placeholder={ids.length ? "Add another…" : "Add a series ID…"}
                  aria-label="Add a series"
                  autoComplete="off"
                  spellCheck={false}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      add();
                    }
                  }}
                />
                <datalist id={listId}>
                  {CURATED.filter((s) => !ids.includes(s.id)).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </datalist>
                <button type="button" className="btn btn-ghost btn-sm" onClick={add} disabled={!draft.trim()}>
                  Add
                </button>
              </>
            )}
          </div>
          <span className="field-hint">
            {ids.length < 2 ? "Add at least two series." : `${ids.length} of ${MAX_SERIES} selected.`}
          </span>
        </div>
        <RangePicker value={range} onChange={setRange} />
        <FrequencySelect value={freq} onChange={setFreq} />
        <Field label="Scale">
          <span className="check">
            <input type="checkbox" checked={rebase} onChange={(e) => setRebase(e.target.checked)} />
            Rebase to 100
          </span>
          <span className="field-hint">Best when units differ</span>
        </Field>
        <button type="submit" className="btn btn-lime" disabled={loading || ids.length < 2}>
          {loading ? "Comparing…" : "Compare"}
        </button>
      </form>

      <div className="quick">
        <span>Try:</span>
        {COMPARISONS.map((c) => (
          <button
            key={c.title}
            type="button"
            className="chip chip-btn"
            onClick={() => {
              setIds(c.ids);
              run(c.ids, range, freq);
            }}
          >
            {c.title}
          </button>
        ))}
      </div>

      {loading && <Skeleton height={430} />}
      {error != null && <ErrorNotice error={error} />}
      {data && <CompareResultView result={data} rebase={rebase} />}
      {!data && !loading && error == null && (
        <p className="empty">Pick two or more series and press <strong>Compare</strong>.</p>
      )}
    </div>
  );
}

function CompareResultView({ result, rebase }: { result: CompareResult; rebase: boolean }) {
  const { ids, cmp, metas, freq } = result;
  const labels = Object.fromEntries(ids.map((id, i) => [id, nameFor(id, metas[i])]));
  const freqLabel = FREQ_OPTIONS.find((f) => f.value === freq)?.label ?? freq;

  const dates = [...new Set(ids.flatMap((id) => (cmp.series[id] ?? []).map((o) => o.date)))].sort();
  const lookup = Object.fromEntries(ids.map((id) => [id, new Map((cmp.series[id] ?? []).map((o) => [o.date, o.value]))]));
  const rows = dates.map((d) => [d, ...ids.map((id) => lookup[id].get(d) ?? "")]);

  return (
    <div className="result">
      <div className="result-head">
        <div>
          <h3>{ids.map((id) => labels[id]).join(" vs. ")}</h3>
          <div className="chips">
            <Chip>{freqLabel}</Chip>
            {rebase && <Chip>Rebased: start = 100</Chip>}
          </div>
        </div>
        <div className="result-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => downloadCsv("comparison.csv", ["date", ...ids], rows)}>
            Download CSV
          </button>
        </div>
      </div>

      <SeriesChart series={cmp.series} normalize={rebase} labels={labels} yLabel={rebase ? "Index (start = 100)" : undefined} />

      <div className="table-scroll">
        <table className="compact">
          <thead>
            <tr>
              <th>Series</th>
              <th>Latest</th>
              <th>Change over range</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((id, i) => {
              const s = summarize(cmp.series[id] ?? []);
              const units = metas[i]?.units ?? "";
              const chg = s ? describeChange(s.first, s.latest, units) : null;
              return (
                <tr key={id}>
                  <td>
                    <span className="dot" style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden="true" />
                    {labels[id]} <span className="mono muted">{id}</span>
                  </td>
                  <td>{s ? formatValue(s.latest, units) : "—"}</td>
                  <td>{chg ? `${chg.direction === "up" ? "▲" : chg.direction === "down" ? "▼" : "•"} ${chg.label}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {cmp.note && <div className="notice">ℹ︎ {cmp.note}</div>}
      <details className="disclose">
        <summary>View data table ({rows.length} rows)</summary>
        <DataTable columns={["Date", ...ids]} rows={rows} />
      </details>
    </div>
  );
}
