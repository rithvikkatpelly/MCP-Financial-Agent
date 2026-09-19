function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function today(): string {
  return iso(new Date());
}

export function yearsAgo(n: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - n);
  return iso(d);
}

/** Range choices. "20Y" rather than "Max": the API refuses windows over 25
 * years, and 20 leaves headroom. */
export const RANGE_PRESETS = [
  { key: "1y", label: "1Y", years: 1 },
  { key: "5y", label: "5Y", years: 5 },
  { key: "10y", label: "10Y", years: 10 },
  { key: "20y", label: "20Y", years: 20 },
] as const;

export type RangeKey = (typeof RANGE_PRESETS)[number]["key"] | "custom";

export interface RangeSelection {
  key: RangeKey;
  start: string;
  end: string;
}

export function presetRange(key: Exclude<RangeKey, "custom">): RangeSelection {
  const years = RANGE_PRESETS.find((p) => p.key === key)!.years;
  return { key, start: yearsAgo(years), end: today() };
}

export function yearsBetween(start: string, end: string): number {
  return (new Date(end).getTime() - new Date(start).getTime()) / (365.25 * 24 * 3600 * 1000);
}
