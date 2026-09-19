import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Observation } from "../api/types";

export const PALETTE = ["#ddf247", "#5eead4", "#fb923c", "#f472b6"];

type Row = Record<string, string | number>;

/** One row per date, one column per series. With `normalize`, each series is
 * rebased to 100 at its first value — the only honest way to draw series with
 * different units (a rate near 4 and an index near 300) on one axis. */
function toRows(series: Record<string, Observation[]>, normalize: boolean): Row[] {
  const byDate = new Map<string, Row>();
  for (const [name, observations] of Object.entries(series)) {
    let base: number | null = null;
    for (const { date, value } of observations) {
      const n = Number(value);
      if (!Number.isFinite(n)) continue;
      if (base === null) base = n;
      const row = byDate.get(date) ?? { date };
      row[name] = normalize && base !== 0 ? Math.round((n / base) * 10000) / 100 : n;
      byDate.set(date, row);
    }
  }
  return [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

const axisTick = { fontSize: 11, fill: "#9a9a9a" };
const tooltipStyle = {
  background: "#1c1c1c",
  border: "1px solid #2c2c2c",
  borderRadius: 12,
  color: "#fff",
  fontSize: 13,
};

interface SeriesChartProps {
  series: Record<string, Observation[]>;
  normalize?: boolean;
  /** Names shown in the tooltip/legend instead of raw series IDs. */
  labels?: Record<string, string>;
  yLabel?: string;
}

export function SeriesChart({ series, normalize = false, labels = {}, yLabel }: SeriesChartProps) {
  const rows = toRows(series, normalize);
  const names = Object.keys(series);
  const single = names.length === 1;
  const nameOf = (n: string) => labels[n] ?? n;

  const common = {
    data: rows,
    margin: { top: 8, right: 12, bottom: 4, left: 4 },
  };
  const axes = (
    <>
      <CartesianGrid stroke="#2c2c2c" strokeDasharray="3 5" vertical={false} />
      <XAxis dataKey="date" tick={axisTick} minTickGap={56} tickFormatter={(d: string) => d.slice(0, 7)} stroke="#2c2c2c" />
      <YAxis
        tick={axisTick}
        width={56}
        domain={["auto", "auto"]}
        stroke="#2c2c2c"
        tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 })}
        label={
          yLabel
            ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#9a9a9a", fontSize: 11, dx: -2 }
            : undefined
        }
      />
      <Tooltip
        contentStyle={tooltipStyle}
        labelStyle={{ color: "#9a9a9a" }}
        cursor={{ stroke: "#555" }}
        formatter={(v: number, n: string) => [v.toLocaleString(undefined, { maximumFractionDigits: 2 }), nameOf(n)]}
      />
    </>
  );

  return (
    <div className="chart" role="img" aria-label={`Line chart of ${names.map(nameOf).join(", ")}`}>
      <ResponsiveContainer width="100%" height={340}>
        {single ? (
          <AreaChart {...common}>
            <defs>
              <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE[0]} stopOpacity={0.3} />
                <stop offset="100%" stopColor={PALETTE[0]} stopOpacity={0} />
              </linearGradient>
            </defs>
            {axes}
            <Area
              type="monotone"
              dataKey={names[0]}
              stroke={PALETTE[0]}
              strokeWidth={2.5}
              fill="url(#area-fill)"
              dot={false}
              connectNulls
            />
          </AreaChart>
        ) : (
          <LineChart {...common}>
            {axes}
            <Legend formatter={(n: string) => <span style={{ color: "#e5e5e5" }}>{nameOf(n)}</span>} />
            {names.map((name, i) => (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={2.5}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
