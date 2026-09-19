import { useEffect, useState } from "react";
import { searchSeries } from "../api/client";
import { TOPIC_ROWS } from "../catalog";
import type { ExplorerRequest, OpenExplorer } from "../explorer";
import { useAsyncAction } from "../useAsyncAction";
import { Chip, ErrorNotice, Field, Skeleton, ToolTag } from "./common";

const loadSearch = (text: string) => searchSeries(text.trim());
const SUGGESTIONS = [...TOPIC_ROWS[0].slice(0, 5), TOPIC_ROWS[1][0]];

export function SearchPanel({ request, open }: { request: ExplorerRequest | null; open: OpenExplorer }) {
  const [text, setText] = useState("");
  const { data, error, loading, run } = useAsyncAction(loadSearch);

  useEffect(() => {
    if (request?.kind !== "search") return;
    setText(request.text);
    run(request.text);
  }, [request?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="panel-body">
      <p className="panel-caption">
        Don't know the series ID? Describe what you're after in plain words.
        <ToolTag>POST /search</ToolTag>
      </p>

      <form
        className="controls"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) run(text);
        }}
      >
        <Field label="What are you looking for?" grow>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. core inflation, 10 year treasury yield"
            autoComplete="off"
          />
        </Field>
        <button type="submit" className="btn btn-lime" disabled={loading || !text.trim()}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      <div className="quick">
        <span>Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className="chip chip-btn"
            onClick={() => {
              setText(s);
              run(s);
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && <Skeleton height={200} />}
      {error != null && <ErrorNotice error={error} />}
      {data && data.results.length === 0 && <div className="notice">No matches — try different words.</div>}
      {data && data.results.length > 0 && (
        <ul className="results-grid">
          {data.results.map((r) => (
            <li key={r.series_id} className="result-card">
              <h4>{r.title}</h4>
              <div className="chips">
                <Chip tone="lime">{r.series_id}</Chip>
                <Chip>{r.units}</Chip>
                <Chip>{r.frequency}</Chip>
              </div>
              <div className="result-actions">
                <button type="button" className="btn btn-lime btn-sm" onClick={() => open({ kind: "chart", id: r.series_id })}>
                  Chart it
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => open({ kind: "compare", ids: [r.series_id], merge: true })}
                >
                  Add to compare
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => open({ kind: "details", id: r.series_id })}>
                  Details
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {!data && !loading && error == null && (
        <p className="empty">Search returns candidate series only — pick one to see its data.</p>
      )}
    </div>
  );
}
