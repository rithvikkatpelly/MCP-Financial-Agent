import type { Frequency, Observation } from "./api/types";

const FREQ_ORDER: Frequency[] = ["d", "w", "m", "q", "a"];

export const FREQ_OPTIONS: { value: Frequency; label: string }[] = [
  { value: "d", label: "Daily" },
  { value: "w", label: "Weekly" },
  { value: "m", label: "Monthly" },
  { value: "q", label: "Quarterly" },
  { value: "a", label: "Annual" },
];

/** FRED's frequency label ("Monthly", "Daily, Close", ...) -> API code. */
export function freqFromLabel(label?: string): Frequency {
  const l = (label ?? "").toLowerCase();
  if (l.startsWith("daily")) return "d";
  if (l.startsWith("week") || l.startsWith("biweek")) return "w";
  if (l.startsWith("quarter")) return "q";
  if (l.startsWith("annual") || l.startsWith("semiannual")) return "a";
  return "m";
}

/** Pick the frequency a person would want: the series' own, except that a
 * long daily/weekly window is rolled up to monthly so the chart stays legible
 * and inside the response budget. */
export function autoFrequency(native: Frequency, years: number): Frequency {
  if ((native === "d" || native === "w") && years > 2) return "m";
  return native;
}

/** Compared series must share one frequency, and FRED can only lower it —
 * so use the coarsest of the group. */
export function coarsest(freqs: Frequency[]): Frequency {
  return freqs.reduce<Frequency>(
    (a, b) => (FREQ_ORDER.indexOf(b) > FREQ_ORDER.indexOf(a) ? b : a),
    "d",
  );
}

export function toNumbers(observations: Observation[]): number[] {
  return observations.map((o) => Number(o.value)).filter((n) => Number.isFinite(n));
}

export function isPercent(units?: string): boolean {
  return /percent/i.test(units ?? "");
}

/** Human-friendly value for a series' units. */
export function formatValue(v: number, units?: string): string {
  if (isPercent(units)) return `${v.toFixed(2)}%`;
  if (/billions of dollars/i.test(units ?? "")) {
    return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}B`;
  }
  return v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 100 ? 1 : 2 });
}

export interface Change {
  /** e.g. "+0.4 pts" for rates, "+3.1%" for levels. */
  label: string;
  direction: "up" | "down" | "flat";
}

/** Rates are compared in percentage points, levels in percent — a move from
 * 4.0% to 4.4% unemployment is "+0.4 pts", not "+10%". */
export function describeChange(first: number, last: number, units?: string): Change {
  const diff = last - first;
  const direction = Math.abs(diff) < 1e-9 ? "flat" : diff > 0 ? "up" : "down";
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  if (isPercent(units)) return { label: `${sign}${Math.abs(diff).toFixed(2)} pts`, direction };
  const pct = first !== 0 ? (Math.abs(diff) / Math.abs(first)) * 100 : 0;
  return { label: `${sign}${pct.toFixed(1)}%`, direction };
}

export interface Summary {
  latest: number;
  latestDate: string;
  first: number;
  firstDate: string;
  high: number;
  low: number;
}

export function summarize(observations: Observation[]): Summary | null {
  const rows = observations
    .map((o) => ({ date: o.date, v: Number(o.value) }))
    .filter((r) => Number.isFinite(r.v));
  if (rows.length === 0) return null;
  const values = rows.map((r) => r.v);
  return {
    latest: rows[rows.length - 1].v,
    latestDate: rows[rows.length - 1].date,
    first: rows[0].v,
    firstDate: rows[0].date,
    high: Math.max(...values),
    low: Math.min(...values),
  };
}

export function downloadCsv(filename: string, header: string[], rows: (string | number)[][]) {
  const esc = (c: string | number) => `"${String(c).replace(/"/g, '""')}"`;
  const csv = [header, ...rows].map((r) => r.map(esc).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
