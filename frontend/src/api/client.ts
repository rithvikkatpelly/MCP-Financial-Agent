import type {
  ApiErrorBody,
  CompareResponse,
  Frequency,
  MetadataResponse,
  ObservationsResponse,
  SearchResponse,
} from "./types";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Thrown for any non-2xx response. `body` is the structured error the API
 * returns under `detail` (`{error, detail, suggestion}`) when it has one —
 * FastAPI request-validation errors don't, so it can be null.
 */
export class ApiError extends Error {
  status: number;
  body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null, fallback: string) {
    super(body?.detail || body?.error || fallback);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    // The API nests its structured error under `detail`; a plain string
    // detail (FastAPI's own validation errors) has no `error` code.
    const detail = payload?.detail;
    const body: ApiErrorBody | null =
      detail && typeof detail === "object" && "error" in detail
        ? (detail as ApiErrorBody)
        : typeof detail === "string"
          ? { error: "request_error", detail }
          : null;
    throw new ApiError(response.status, body, `Request failed (${response.status})`);
  }

  return response.json() as Promise<T>;
}

export function searchSeries(searchText: string): Promise<SearchResponse> {
  return request<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify({ search_text: searchText }),
  });
}

export interface RangeArgs {
  start_date: string;
  end_date: string;
  frequency: Frequency;
}

export function getObservations(
  seriesId: string,
  range: RangeArgs,
): Promise<ObservationsResponse> {
  return request<ObservationsResponse>("/observations", {
    method: "POST",
    body: JSON.stringify({ series_id: seriesId, ...range }),
  });
}

export function compareSeries(
  seriesIds: string[],
  range: RangeArgs,
): Promise<CompareResponse> {
  return request<CompareResponse>("/compare", {
    method: "POST",
    body: JSON.stringify({ series_ids: seriesIds, ...range }),
  });
}

export function getMetadata(seriesId: string): Promise<MetadataResponse> {
  return request<MetadataResponse>(`/metadata/${encodeURIComponent(seriesId)}`);
}
