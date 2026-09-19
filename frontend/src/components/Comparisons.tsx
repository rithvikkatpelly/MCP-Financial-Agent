import { COMPARISONS, CURATED_BY_ID } from "../catalog";
import type { OpenExplorer } from "../explorer";
import type { SnapshotMap } from "../useSnapshots";
import { PALETTE } from "./SeriesChart";
import { Sparkline } from "./Sparkline";

export function Comparisons({ items, loading, open }: { items: SnapshotMap; loading: boolean; open: OpenExplorer }) {
  return (
    <section className="section" aria-labelledby="cmp-title">
      <div className="section-head">
        <h2 id="cmp-title" className="section-title">
          Popular <em>comparisons</em>
        </h2>
        <button type="button" className="link-arrow" onClick={() => open({ kind: "compare", ids: ["UNRATE", "CPIAUCSL"] })}>
          Build your own <span aria-hidden="true">→</span>
        </button>
      </div>
      <div className="grid-3">
        {COMPARISONS.map((c) => {
          // Rebase each line to 100 so different units share one scale.
          const lines = c.ids.map((id) => {
            const v = items[id]?.values;
            return v && v.length > 1 && v[0] !== 0 ? v.map((x) => (x / v[0]) * 100) : null;
          });
          const all = lines.flatMap((l) => l ?? []);
          const domain: [number, number] | undefined = all.length ? [Math.min(...all), Math.max(...all)] : undefined;
          return (
            <button key={c.title} type="button" className="cmp-card" onClick={() => open({ kind: "compare", ids: c.ids })}>
              <div className="cmp-art">
                {lines.some(Boolean) ? (
                  lines.map((l, i) =>
                    l ? <Sparkline key={c.ids[i]} values={l} color={PALETTE[i % PALETTE.length]} domain={domain} fill={false} /> : null,
                  )
                ) : (
                  <div className={loading ? "skeleton skeleton-fill" : "cf-empty"} />
                )}
              </div>
              <h3>{c.title}</h3>
              <p>{c.blurb}</p>
              <div className="cmp-foot">
                <span className="legend">
                  {c.ids.map((id, i) => (
                    <span key={id}>
                      <i style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden="true" />
                      {CURATED_BY_ID[id]?.name ?? id}
                    </span>
                  ))}
                </span>
                <span className="mono muted">{c.ids.length} series</span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
