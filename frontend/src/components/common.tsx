import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import type { CostInfo } from "../api/types";

export function ErrorNotice({ error }: { error: unknown }) {
  let title = "Something went wrong";
  let detail: string | undefined;
  let suggestion: string | undefined;

  if (error instanceof ApiError) {
    title = error.body?.error?.replace(/_/g, " ") ?? `HTTP ${error.status}`;
    detail = error.body?.detail ?? undefined;
    suggestion = error.body?.suggestion ?? undefined;
  } else if (error instanceof Error) {
    detail = error.message;
  }

  return (
    <div className="notice notice-error" role="alert">
      <strong>{title}</strong>
      {detail && <p>{detail}</p>}
      {suggestion && <p className="notice-suggestion">{suggestion}</p>}
    </div>
  );
}

export function CostBadge({ cost, note }: { cost?: CostInfo; note?: string }) {
  if (!cost && !note) return null;
  return (
    <p className="cost-badge">
      {cost && (
        <>
          guardrail: ~{cost.estimated_tokens} tokens · budget remaining{" "}
          {cost.budget_remaining}
        </>
      )}
      {note && <span className="cost-note"> · {note}</span>}
    </p>
  );
}

export function DataTable({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export const FREQUENCIES: { value: string; label: string }[] = [
  { value: "d", label: "daily" },
  { value: "w", label: "weekly" },
  { value: "m", label: "monthly" },
  { value: "q", label: "quarterly" },
  { value: "a", label: "annual" },
];
