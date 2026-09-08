import { useCallback, useState } from "react";
import { searchSeries } from "../api/client";
import { useAsyncAction } from "../useAsyncAction";
import { DataTable, ErrorNotice, Field } from "./common";

export function SearchPanel() {
  const [text, setText] = useState("unemployment rate");
  const { data, error, loading, run } = useAsyncAction(
    useCallback(() => searchSeries(text.trim()), [text]),
  );

  return (
    <section className="panel">
      <h2>search_series</h2>
      <p className="panel-caption">
        Plain-language concept → candidate series IDs. Never returns observations.
      </p>

      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <Field label="search_text">
          <input value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <button type="submit" disabled={loading || !text.trim()}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error != null && <ErrorNotice error={error} />}
      {data && data.results.length === 0 && <p>No matching series.</p>}
      {data && data.results.length > 0 && (
        <DataTable
          columns={["series_id", "title", "frequency", "units"]}
          rows={data.results.map((r) => [r.series_id, r.title, r.frequency, r.units])}
        />
      )}
    </section>
  );
}
