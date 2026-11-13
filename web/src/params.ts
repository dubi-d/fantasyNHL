import { useSearchParams } from "react-router-dom";

type Value = string | number | null;
export type Patch = Record<string, Value | Array<string | number>>;

/** The choices of a page, kept in the address: they survive a reload,
 * follow back and forward, and can be linked to. */
export function usePageParams() {
  const [params, setParams] = useSearchParams();
  return {
    /** A single choice; ``fallback`` while the address names none. */
    get: (name: string, fallback = "") => params.get(name) ?? fallback,
    list: (name: string) => params.getAll(name),
    /** Change several choices at once; null, "" and [] remove one.
     * ``replace`` keeps values passed through (typing) out of the history. */
    set: (patch: Patch, replace = false) => {
      const next = new URLSearchParams(params);
      for (const [name, value] of Object.entries(patch)) {
        next.delete(name);
        for (const item of Array.isArray(value) ? value : [value]) {
          if (item !== null && item !== "") next.append(name, String(item));
        }
      }
      setParams(next, { replace });
    },
  };
}

/** A number typed by the user, held within its bounds. */
export function clamp(value: string | number, low: number, high: number) {
  const number = Number(value);
  return Math.max(low, Math.min(high, Number.isFinite(number) ? number : low));
}
