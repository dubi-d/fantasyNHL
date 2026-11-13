import type { components } from "./schema";

type Schemas = components["schemas"];
export type View = Schemas["ViewModel"];
export type Block = View["blocks"][number];
export type Table = Schemas["TableBlock"];
export type Row = Schemas["Row"];
export type Note = Schemas["NoteBlock"];
export type LeagueInfo = Schemas["LeagueInfo"];
export type LeagueMeta = Schemas["LeagueMeta"];
export type ReviewOptions = Schemas["ReviewOptions"];
export type CalibrationInfo = Schemas["CalibrationInfo"];
export type Stats = "blended" | "season";

type Value = string | number | boolean | null | undefined;
export type Params = Record<string, Value | Array<string | number>>;

/** An API address; empty parameters are left out, arrays repeat the key. */
export function apiUrl(path: string, params: Params = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      query.append(key, String(item));
    }
  }
  const text = query.toString();
  return `/api${path}${text ? `?${text}` : ""}`;
}

export async function request<T>(
  url: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(url, {
    method,
    // the backend only accepts state changes sent as JSON
    headers: method === "GET" ? undefined : { "Content-Type": "application/json" },
    body: method === "GET" ? undefined : JSON.stringify(body ?? {}),
  }).catch(() => {
    throw new Error("The fantasyNHL server cannot be reached. Is it still running?");
  });
  if (!response.ok) {
    const detail = await response.json().then(
      (error) => error.detail,
      () => response.statusText,
    );
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json();
}
