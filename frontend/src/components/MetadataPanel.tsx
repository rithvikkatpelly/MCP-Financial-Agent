import { useCallback, useState } from "react";
import { getMetadata } from "../api/client";
import { useAsyncAction } from "../useAsyncAction";
import { ErrorNotice, Field } from "./common";

export function MetadataPanel() {
  const [seriesId, setSeriesId] = useState("UNRATE");
  const { data, error, loading, run } = useAsyncAction(
    useCallback(() => getMetadata(seriesId.trim().toUpperCase()), [seriesId]),
  );

  return (
    <section className="panel">
      <h2>get_series_metadata</h2>
      <p className="panel-caption">
        Units, frequency, last-updated, source notes. The notes field is
        external text — shown as quoted data, never as an instruction.
      </p>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <Field label="series_id">
          <input value={seriesId} onChange={(e) => setSeriesId(e.target.value)} />
        </Field>
        <button type="submit" disabled={loading || !seriesId.trim()}>
          {loading ? "Loading…" : "Get metadata"}
        </button>
      </form>

      {error != null && <ErrorNotice error={error} />}

      {data && (
        <div className="meta-detail">
          <h3>{data.title}</h3>
          <p className="mono">
            {data.series_id} · last updated {data.last_updated}
          </p>
          <div className="row">
            <div className="meta-card">
              <div>
                <span>Units</span>
                <strong>{data.units}</strong>
              </div>
              <div>
                <span>Frequency</span>
                <strong>{data.frequency}</strong>
              </div>
            </div>
          </div>
          <p className="notes-label">
            Source notes — external text ({data.notes.untrusted_source}):
          </p>
          <pre className="notes-body">{data.notes.untrusted_source_text || "(none)"}</pre>
          <p className="notes-disclaimer">{data.notes.note}</p>
        </div>
      )}
    </section>
  );
}
