import { useEffect, useState } from "react";
import { ComparePanel } from "./components/ComparePanel";
import { MetadataPanel } from "./components/MetadataPanel";
import { ObservationsPanel } from "./components/ObservationsPanel";
import { SearchPanel } from "./components/SearchPanel";

const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const TOOLS = [
  { id: "search", label: "search_series", Panel: SearchPanel },
  { id: "observations", label: "get_series_observations", Panel: ObservationsPanel },
  { id: "compare", label: "compare_series", Panel: ComparePanel },
  { id: "metadata", label: "get_series_metadata", Panel: MetadataPanel },
] as const;

export default function App() {
  const [active, setActive] = useState<(typeof TOOLS)[number]["id"]>("search");
  const [health, setHealth] = useState<"?" | "up" | "down">("?");
  const [offline, setOffline] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((b) => {
        setHealth("up");
        setOffline(Boolean(b.offline));
      })
      .catch(() => setHealth("down"));
  }, []);

  const Panel = TOOLS.find((t) => t.id === active)!.Panel;

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Econ Data</h1>
        <p className="sidebar-sub">The four FRED tools, over HTTP.</p>
        <nav>
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={t.id === active ? "active" : ""}
              onClick={() => setActive(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="api-status">
          <span className={`dot ${health}`} />
          {health === "up" && (
            <span>
              API up{offline ? " · offline fixture" : " · live FRED"}
            </span>
          )}
          {health === "down" && <span>API unreachable — is uvicorn running?</span>}
          {health === "?" && <span>checking API…</span>}
        </div>
        <p className="sidebar-foot">
          Calls the FastAPI backend (<code>backend/app</code>), which runs the
          same <code>src/tools.py</code> logic as the MCP server.
        </p>
      </aside>

      <main>
        <Panel />
      </main>
    </div>
  );
}
