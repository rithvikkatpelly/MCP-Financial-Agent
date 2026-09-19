import { useState, type KeyboardEvent } from "react";
import { CURATED, type CuratedSeries } from "../catalog";
import type { OpenExplorer } from "../explorer";
import { describeChange, formatValue } from "../format";
import type { Snapshot, SnapshotMap } from "../useSnapshots";
import { PALETTE } from "./SeriesChart";
import { Sparkline } from "./Sparkline";

const CARD_COLORS = [...PALETTE, "#a78bfa", "#60a5fa", "#f87171"];

function SeriesCard({
  series,
  snap,
  loading,
  color,
}: {
  series: CuratedSeries;
  snap: Snapshot | null | undefined;
  loading: boolean;
  color: string;
}) {
  const ready = snap && snap.values.length > 1;
  const first = ready ? snap.values[0] : 0;
  const last = ready ? snap.values[snap.values.length - 1] : 0;
  const change = ready ? describeChange(first, last, snap.units) : null;
  const arrow = change?.direction === "up" ? "▲" : change?.direction === "down" ? "▼" : "•";

  return (
    <>
      <div className="cf-art" style={{ background: `linear-gradient(160deg, ${color}2e, transparent 70%)` }}>
        {ready ? (
          <Sparkline values={snap.values} color={color} />
        ) : (
          <div className={loading ? "skeleton skeleton-fill" : "cf-empty"}>{loading ? "" : "No data"}</div>
        )}
        {ready && <span className="badge">as of {snap.dates[snap.dates.length - 1].slice(0, 7)}</span>}
      </div>
      <h3>{series.name}</h3>
      <div className="cf-meta">
        <span className="mono">{series.id}</span>
        {change && (
          <span className={`chg chg-${change.direction}`}>
            {arrow} {change.label}
          </span>
        )}
      </div>
      <p className="cf-blurb">{series.blurb}</p>
      <div className="cf-foot">
        <span className="mono muted">Latest</span>
        <strong>{ready ? formatValue(last, snap.units) : "—"}</strong>
      </div>
    </>
  );
}

export function Hero({
  items,
  loading,
  open,
}: {
  items: SnapshotMap;
  loading: boolean;
  open: OpenExplorer;
}) {
  const [index, setIndex] = useState(Math.floor(CURATED.length / 2));
  const clamp = (i: number) => Math.max(0, Math.min(CURATED.length - 1, i));

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft") setIndex((i) => clamp(i - 1));
    if (e.key === "ArrowRight") setIndex((i) => clamp(i + 1));
  };

  return (
    <section id="top" className="hero">
      <div className="hero-fx" aria-hidden="true">
        <span className="fx fx-1">%</span>
        <span className="fx fx-2">$</span>
        <span className="fx fx-3">↗</span>
        <span className="fx fx-star fx-4" />
        <span className="fx fx-star fx-5" />
      </div>
      <div className="container hero-copy">
        <h1>
          US economic data,
          <br />
          <em>made readable</em>
        </h1>
        <p>
          Chart unemployment, inflation, interest rates and GDP straight from the Federal Reserve's FRED database —
          no spreadsheets, no series IDs to memorise.
        </p>
        <div className="hero-cta">
          <a className="btn btn-lime btn-lg" href="#explore">
            Explore the data <span aria-hidden="true">↗</span>
          </a>
          <a className="btn btn-light btn-lg" href="#how">
            How it works <span aria-hidden="true">↗</span>
          </a>
        </div>
      </div>

      <div
        className="cf"
        role="group"
        aria-roledescription="carousel"
        aria-label="Featured economic indicators"
        tabIndex={0}
        onKeyDown={onKey}
      >
        <div className="cf-stage">
          {CURATED.map((s, i) => {
            const d = i - index;
            const center = d === 0;
            return (
              <button
                key={s.id}
                type="button"
                className={`cf-card${center ? " is-center" : ""}`}
                style={{ "--d": d, "--abs": Math.abs(d) } as React.CSSProperties}
                aria-label={center ? `Open ${s.name} chart` : `Show ${s.name}`}
                aria-hidden={Math.abs(d) > 3}
                tabIndex={Math.abs(d) > 3 ? -1 : 0}
                onClick={() => (center ? open({ kind: "chart", id: s.id }) : setIndex(i))}
              >
                <SeriesCard series={s} snap={items[s.id]} loading={loading} color={CARD_COLORS[i % CARD_COLORS.length]} />
              </button>
            );
          })}
        </div>

        <div className="cf-nav">
          <button type="button" className="icon-btn" aria-label="Previous indicator" onClick={() => setIndex((i) => clamp(i - 1))} disabled={index === 0}>
            ←
          </button>
          <ol className="cf-dots">
            {CURATED.map((s, i) => (
              <li key={s.id}>
                <button type="button" className={i === index ? "on" : ""} aria-label={`${i + 1}: ${s.name}`} aria-current={i === index} onClick={() => setIndex(i)}>
                  {i + 1}
                </button>
              </li>
            ))}
          </ol>
          <button type="button" className="icon-btn" aria-label="Next indicator" onClick={() => setIndex((i) => clamp(i + 1))} disabled={index === CURATED.length - 1}>
            →
          </button>
        </div>
        <p className="cf-hint">Click the centre card to chart it · ← → keys to browse</p>
      </div>
    </section>
  );
}
