import { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/client";
import type { ExplorerRequest, OpenExplorer } from "../explorer";
import { ChartPanel } from "./ChartPanel";
import { ComparePanel } from "./ComparePanel";
import { DetailsPanel } from "./DetailsPanel";
import { SearchPanel } from "./SearchPanel";

const TABS = [
  { id: "chart", label: "Chart a series" },
  { id: "compare", label: "Compare" },
  { id: "search", label: "Find a series" },
  { id: "details", label: "Series details" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function Explorer({ request, open }: { request: ExplorerRequest | null; open: OpenExplorer }) {
  const [active, setActive] = useState<TabId>("chart");

  useEffect(() => {
    if (request) setActive(request.kind);
  }, [request]);

  return (
    <section id="explore" className="section" aria-labelledby="explore-title">
      <div className="section-head">
        <h2 id="explore-title" className="section-title">
          Explore the <em>data</em>
        </h2>
        <a className="link-arrow" href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
          API docs <span aria-hidden="true">↗</span>
        </a>
      </div>

      <div className="tabs" role="tablist" aria-label="Explorer tools">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={active === t.id}
            aria-controls={`panel-${t.id}`}
            className={active === t.id ? "on" : ""}
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="explorer">
        {/* All four stay mounted (just hidden) so switching tabs keeps your results. */}
        <div role="tabpanel" id="panel-chart" aria-labelledby="tab-chart" hidden={active !== "chart"}>
          <ChartPanel request={request} open={open} />
        </div>
        <div role="tabpanel" id="panel-compare" aria-labelledby="tab-compare" hidden={active !== "compare"}>
          <ComparePanel request={request} />
        </div>
        <div role="tabpanel" id="panel-search" aria-labelledby="tab-search" hidden={active !== "search"}>
          <SearchPanel request={request} open={open} />
        </div>
        <div role="tabpanel" id="panel-details" aria-labelledby="tab-details" hidden={active !== "details"}>
          <DetailsPanel request={request} open={open} />
        </div>
      </div>
    </section>
  );
}
