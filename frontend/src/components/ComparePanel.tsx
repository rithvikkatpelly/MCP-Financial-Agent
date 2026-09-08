import { useCallback, useMemo, useState } from "react";
import { compareSeries } from "../api/client";
import { yearsAgo, today } from "../dates";
import { useAsyncAction } from "../useAsyncAction";
import { CostBadge, DataTable, ErrorNotice, Field } from "./common";
import { RangeControls, type Range } from "./RangeControls";
import { SeriesChart } from "./SeriesChart";

export function ComparePanel() {
  const [raw, setRaw] = useState("UNRATE, CPIAUCSL");
  const [range, setRange] = useState<Range>({
    start_date: yearsAgo(5),
    end_date: today(),
    frequency: "m",
  });

  const ids = useMemo(
    () =>
      raw
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean),
    [raw],
  );

  const { data, error, loading, run } = useAsyncAction(
    useCallback(() => compareSeries(ids, range), [ids, range]),
  );

  const rows = useMemo(() => {
    if (!data) return [];
    const names = Object.keys(data.series);
    const byDate = new Map<string, Record<string, string>>();
    for (const name of names) {
      for (const { date, value } of data.series[name]) {
        const row = byDate.get(date) ?? {};
        row[name] = value;
        byDate.set(date, row);
      }
    }
    return [...byDate.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, vals]) => [date, ...names.map((n) => vals[n] ?? "")]);
  }, [data]);

  return (
    <section className="panel">
      <h2>compare_series</h2>
      <p className="panel-caption">
        2–4 series aligned over one date range. Capped at 4 to keep the response
        bounded.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="row">
          <Field label="series_ids (comma-separated, max 4)">
            <input value={raw} onChange={(e) => setRaw(e.target.value)} />
          </Field>
        </div>
        <RangeControls range={range} onChange={setRange} />
        <button type="submit" disabled={loading || ids.length < 2}>
          {loading ? "Comparing…" : "Compare"}
        </button>
        {ids.length < 2 && <span className="hint">Enter at least 2 series IDs.</span>}
      </form>

      {error != null && <ErrorNotice error={error} />}

      {data && (
        <>
          <SeriesChart series={data.series} />
          <CostBadge cost={data._cost} note={data.note} />
          <DataTable columns={["date", ...Object.keys(data.series)]} rows={rows} />
        </>
      )}
    </section>
  );
}
