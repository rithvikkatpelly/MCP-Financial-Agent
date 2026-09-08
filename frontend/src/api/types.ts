// Mirrors backend/app/schemas.py. The observation `value` is a string
// because that is exactly what FRED returns.

export type Frequency = "d" | "w" | "m" | "q" | "a";

export interface SeriesMatch {
  series_id: string;
  title: string;
  frequency: string;
  units: string;
}

export interface SearchResponse {
  results: SeriesMatch[];
}

export interface Observation {
  date: string;
  value: string;
}

export interface CostInfo {
  estimated_tokens: number;
  budget_remaining: number;
  note?: string;
}

export interface ObservationsResponse {
  series_id: string;
  observations: Observation[];
  _cost?: CostInfo;
  note?: string;
}

export interface CompareResponse {
  series: Record<string, Observation[]>;
  _cost?: CostInfo;
  note?: string;
}

export interface UntrustedText {
  untrusted_source: string;
  untrusted_source_text: string;
  note: string;
}

export interface MetadataResponse {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  last_updated: string;
  notes: UntrustedText;
}

// The structured error the API puts under `detail` (from src/tools.py).
export interface ApiErrorBody {
  error: string;
  detail?: string;
  suggestion?: string;
}
