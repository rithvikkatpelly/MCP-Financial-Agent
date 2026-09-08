import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Observation } from "../api/types";

const COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706"];

/** Merge one-or-more named series (each `[{date, value}]`) into the row shape
 * recharts wants: `[{ date, <seriesId>: number, ... }]`, keyed by date. */
function toRows(series: Record<string, Observation[]>): Record<string, string | number>[] {
  const byDate = new Map<string, Record<string, string | number>>();
  for (const [name, observations] of Object.entries(series)) {
    for (const { date, value } of observations) {
      const row = byDate.get(date) ?? { date };
      const n = Number(value);
      if (!Number.isNaN(n)) row[name] = n;
      byDate.set(date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

export function SeriesChart({ series }: { series: Record<string, Observation[]> }) {
  const rows = toRows(series);
  const names = Object.keys(series);

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
          <YAxis tick={{ fontSize: 11 }} width={56} />
          <Tooltip />
          {names.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={COLORS[i % COLORS.length]}
              dot={false}
              strokeWidth={2}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {names.length > 1 && (
        <p className="chart-hint">
          Series share one axis — read levels per series, not across them.
        </p>
      )}
    </div>
  );
}
