import type { Frequency } from "../api/types";
import { FREQUENCIES, Field } from "./common";

export interface Range {
  start_date: string;
  end_date: string;
  frequency: Frequency;
}

export function RangeControls({
  range,
  onChange,
}: {
  range: Range;
  onChange: (next: Range) => void;
}) {
  return (
    <div className="row">
      <Field label="start_date">
        <input
          type="date"
          value={range.start_date}
          onChange={(e) => onChange({ ...range, start_date: e.target.value })}
        />
      </Field>
      <Field label="end_date">
        <input
          type="date"
          value={range.end_date}
          onChange={(e) => onChange({ ...range, end_date: e.target.value })}
        />
      </Field>
      <Field label="frequency">
        <select
          value={range.frequency}
          onChange={(e) => onChange({ ...range, frequency: e.target.value as Frequency })}
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.value} — {f.label}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}
