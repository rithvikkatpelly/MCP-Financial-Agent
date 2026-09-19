import { API_BASE_URL } from "../api/client";
import { REPO_URL } from "../catalog";
import { Sparkline } from "./Sparkline";

const DEMO = [
  [4, 5, 4.6, 6, 5.4, 7, 6.6, 8],
  [8, 7, 7.4, 5.5, 6, 4.5, 5, 3.5],
  [3, 4.5, 4, 5.5, 5, 6.5, 8, 7.5],
];

export function CtaBanner() {
  return (
    <section className="cta" aria-labelledby="cta-title">
      <div className="cta-copy">
        <h2 id="cta-title">
          One data layer.
          <br />
          Two ways to use it.
        </h2>
        <p>The same tools behind this page are available over HTTP, and as an MCP server for Claude Desktop.</p>
        <div className="hero-cta">
          <a className="btn btn-dark" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
            Open the API docs <span aria-hidden="true">↗</span>
          </a>
          <a className="btn btn-dark" href={REPO_URL} target="_blank" rel="noreferrer">
            View on GitHub <span aria-hidden="true">↗</span>
          </a>
        </div>
      </div>
      <div className="cta-art" aria-hidden="true">
        {DEMO.map((v, i) => (
          <div key={i} className={`mini mini-${i}`}>
            <Sparkline values={v} color="#141414" fill={false} strokeWidth={2.5} />
            <span />
          </div>
        ))}
      </div>
    </section>
  );
}
