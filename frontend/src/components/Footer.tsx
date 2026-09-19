import { API_BASE_URL } from "../api/client";
import { REPO_URL } from "../catalog";

export function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div>
            <p className="footer-brand">
              Econ<b>Data</b>
            </p>
            <p className="footer-note">
              A friendly front end for FRED economic data, built on the same tool layer as an MCP server.
            </p>
          </div>
          <div>
            <h4>Explore</h4>
            <a href="#explore">Chart a series</a>
            <a href="#explore">Compare series</a>
            <a href="#explore">Find a series</a>
            <a href="#how">How it works</a>
          </div>
          <div>
            <h4>Build</h4>
            <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">API docs</a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">Source on GitHub</a>
            <a href={`${REPO_URL}/blob/main/SECURITY.md`} target="_blank" rel="noreferrer">Security model</a>
            <a href={`${REPO_URL}/blob/main/DEPLOYMENT.md`} target="_blank" rel="noreferrer">Deployment guide</a>
          </div>
        </div>
        <div className="footer-base">
          <p>
            Data: FRED®, Federal Reserve Bank of St. Louis. This product uses the FRED® API but is not endorsed or
            certified by the Federal Reserve Bank of St. Louis. Not investment advice.
          </p>
          <a className="to-top" href="#top" aria-label="Back to top">
            ↑
          </a>
        </div>
      </div>
    </footer>
  );
}
