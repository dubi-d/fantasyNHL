import type { ReactNode } from "react";

import { useSession } from "../session";

export type Option = { value: string | number; label: string };

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

/** A labeled dropdown; values travel as strings. */
export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | number;
  options: Option[];
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

/** Fantasy teams as options, valued by team row. */
export function useTeamOptions(): Option[] {
  const { meta } = useSession();
  return meta.teams.map((name, row) => ({ value: row, label: name }));
}

/** Matchup weeks as options; ``completed`` keeps only finished ones. */
export function useWeekOptions(completed = false): Option[] {
  const { meta } = useSession();
  return meta.weeks
    .filter((week) => week.completed || !completed)
    .map((week) => ({ value: week.week, label: week.label }));
}

export function Page({
  title,
  controls,
  children,
}: {
  title: string;
  controls?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <h2>{title}</h2>
      {controls && <div className="controls">{controls}</div>}
      {children}
    </section>
  );
}
