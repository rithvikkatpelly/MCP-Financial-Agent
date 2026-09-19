import { useEffect, useState } from "react";
import { getMetadata } from "../api/client";
import type { ExplorerRequest, OpenExplorer } from "../explorer";
import { useAsyncAction } from "../useAsyncAction";
import { Chip, ErrorNotice, Skeleton, ToolTag } from "./common";
import { SeriesPicker } from "./controls";

const loadDetails = (id: string) => getMetadata(id.trim().toUpperCase());

export function DetailsPanel({ request, open }: { request: ExplorerRequest | null; open: OpenExplorer }) {
  const [seriesId, setSeriesId] = useState("UNRATE");
  const { data, error, loading, run } = useAsyncAction(loadDetails);

  useEffect(() => {
    if (request?.kind !== "details") return;
    setSeriesId(request.id);
    run(request.id);
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="panel-body">
      <p className="panel-caption">
        What a series measures, its units, and when it was last updated.
        <ToolTag>GET /metadata/{"{series_id}"}</ToolTag>
      </p>

      <form
        className="controls"
        onSubmit={(e) => {
          e.preventDefault();
          run(seriesId);
        }}
      >
        <SeriesPicker value={seriesId} onChange={setSeriesId} />
        <button type="submit" className="btn btn-lime" disabled={loading || !seriesId.trim()}>
          {loading ? "Loading…" : "Show details"}
        </button>
      </form>

      {loading && <Skeleton height={220} />}
      {error != null && <ErrorNotice error={error} />}
      {data && (
        <div className="result">
          <div className="result-head">
            <div>
              <h3>{data.title}</h3>
              <div className="chips">
                <Chip tone="lime">{data.series_id}</Chip>
                <Chip>{data.units}</Chip>
                <Chip>{data.frequency}</Chip>
                <Chip>Updated {data.last_updated.slice(0, 10)}</Chip>
              </div>
            </div>
            <div className="result-actions">
              <button type="button" className="btn btn-lime btn-sm" onClick={() => open({ kind: "chart", id: data.series_id })}>
                Chart this series
              </button>
            </div>
          </div>
          <figure className="notes">
            <figcaption>Source notes from {data.notes.untrusted_source.replace(/_/g, " ")}</figcaption>
            <blockquote>{data.notes.untrusted_source_text || "No notes provided."}</blockquote>
            <p className="notes-disclaimer">
              🛡 {data.notes.note} It's displayed here as quoted text and never acted on.
            </p>
          </figure>
        </div>
      )}
      {!data && !loading && error == null && <p className="empty">Choose a series to see what it measures.</p>}
    </div>
  );
}
