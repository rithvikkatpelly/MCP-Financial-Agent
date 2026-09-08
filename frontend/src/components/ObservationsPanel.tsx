import { useCallback, useState } from "react";
import { getMetadata, getObservations } from "../api/client";
import type { MetadataResponse, ObservationsResponse } from "../api/types";
import { yearsAgo, today } from "../dates";
import { useAsyncAction } from "../useAsyncAction";
import { CostBadge, DataTable, ErrorNotice, Field } from "./common";
import { RangeControls, type Range } from "./RangeControls";
import { SeriesChart } from "./SeriesChart";

interface Result {
  obs: ObservationsResponse;
  meta: MetadataResponse | null;
}

export function ObservationsPanel() {
  const [seriesId, setSeriesId] = useState("UNRATE");
  const [range, setRange] = useState<Range>({
    start_date: yearsAgo(5),
    end_date: today(),
    frequency: "m",
  });

  const { data, error, loading, run } = useAsyncAction<Result>(
    useCallback(async () => {
      const id = seriesId.trim().toUpperCase();
      // Metadata is best-effort — a failure there shouldn't hide the chart.
      const [obs, meta] = await Promise.all([
        getObservations(id, range),
        getMetadata(id).catch(() => null),
      ]);
      return { obs, meta };
    }, [seriesId, range]),
  );

  return (
    <section className="panel">
      <h2>get_series_observations</h2>
      <p className="panel-caption">
        One series over a required date range. Long ranges are thinned to the
        session token budget; a range that still doesn't fit is refused.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="row">
          <Field label="series_id">
            <input value={seriesId} onChange={(e) => setSeriesId(e.target.value)} />
          </Field>
        </div>
        <RangeControls range={range} onChange={setRange} />
        <button type="submit" disabled={loading || !seriesId.trim()}>
          {loading ? "Fetching…" : "Fetch"}
        </button>
      </form>

      {error != null && <ErrorNotice error={error} />}

      {data && (
        <>
          <div className="chart-with-meta">
            <SeriesChart series={{ [data.obs.series_id]: data.obs.observations }} />
            {data.meta && (
              <aside className="meta-card">
                <div>
                  <span>Units</span>
                  <strong>{data.meta.units}</strong>
                </div>
                <div>
                  <span>Frequency</span>
                  <strong>{data.meta.frequency}</strong>
                </div>
                <div>
                  <span>Last updated</span>
                  <strong>{data.meta.last_updated}</strong>
                </div>
              </aside>
            )}
          </div>
          <CostBadge cost={data.obs._cost} note={data.obs.note} />
          <DataTable
            columns={["date", "value"]}
            rows={data.obs.observations.map((o) => [o.date, o.value])}
          />
        </>
      )}
    </section>
  );
}
