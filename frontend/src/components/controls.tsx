import { useId } from "react";
import type { Frequency } from "../api/types";
import { CURATED, CURATED_BY_ID } from "../catalog";
import { RANGE_PRESETS, presetRange, today, type RangeSelection } from "../dates";
import { FREQ_OPTIONS } from "../format";
import { Field } from "./common";

/** Text box that suggests the featured series but accepts any FRED ID. */
export function SeriesPicker({
  label = "Series",
  value,
  onChange,
  grow = true,
}: {
  label?: string;
  value: string;
  onChange: (v: string) => void;
  grow?: boolean;
}) {
  const listId = useId();
  const known = CURATED_BY_ID[value.trim().toUpperCase()];
  return (
    <Field label={label} grow={grow} hint={known ? known.name : "Pick one, or type any FRED series ID"}>
      <input
        value={value}
        list={listId}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. UNRATE"
        autoComplete="off"
        spellCheck={false}
        aria-label={label}
      />
      <datalist id={listId}>
        {CURATED.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </datalist>
    </Field>
  );
}

export function RangePicker({
  value,
  onChange,
}: {
  value: RangeSelection;
  onChange: (next: RangeSelection) => void;
}) {
  return (
    <div className="field">
      <span className="field-label">Time range</span>
      <div className="seg" role="group" aria-label="Time range">
        {RANGE_PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            className={value.key === p.key ? "on" : ""}
            aria-pressed={value.key === p.key}
            onClick={() => onChange(presetRange(p.key))}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          className={value.key === "custom" ? "on" : ""}
          aria-pressed={value.key === "custom"}
          onClick={() => onChange({ ...value, key: "custom" })}
        >
          Custom
        </button>
      </div>
      {value.key === "custom" && (
        <div className="row date-row">
          <input
            type="date"
            aria-label="Start date"
            value={value.start}
            min="1990-01-01"
            max={value.end}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
          />
          <span aria-hidden="true">→</span>
          <input
            type="date"
            aria-label="End date"
            value={value.end}
            max={today()}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </div>
      )}
    </div>
  );
}

export function FrequencySelect({
  value,
  onChange,
}: {
  value: "auto" | Frequency;
  onChange: (v: "auto" | Frequency) => void;
}) {
  return (
    <Field label="Detail">
      <select value={value} onChange={(e) => onChange(e.target.value as "auto" | Frequency)}>
        <option value="auto">Automatic (recommended)</option>
        {FREQ_OPTIONS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
