import { TOPIC_ROWS } from "../catalog";
import type { OpenExplorer } from "../explorer";

export function Marquee({ open }: { open: OpenExplorer }) {
  return (
    <section className="marquee" aria-labelledby="ask-title">
      <h2 id="ask-title" className="marquee-title">
        Ask about <em>anything</em>
      </h2>
      <p className="marquee-sub">Tap a topic to find the matching data series.</p>
      {TOPIC_ROWS.map((row, r) => (
        <div key={r} className={`marquee-row ${r % 2 ? "rev" : ""}`}>
          {/* The list is doubled so the loop is seamless; the copy is hidden from assistive tech. */}
          {[0, 1].map((copy) => (
            <div key={copy} className="marquee-track" aria-hidden={copy === 1}>
              {row.map((t) => (
                <button key={t} type="button" tabIndex={copy === 1 ? -1 : 0} className="topic" onClick={() => open({ kind: "search", text: t })}>
                  <i aria-hidden="true">{t[0].toUpperCase()}</i>
                  {t}
                </button>
              ))}
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
