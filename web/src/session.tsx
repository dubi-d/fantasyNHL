import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useState, type ReactNode } from "react";

import {
  apiUrl,
  request,
  type LeagueInfo,
  type LeagueMeta,
  type Stats,
} from "./api";

type Session = {
  leagues: LeagueInfo[];
  meta: LeagueMeta;
  setLeague: (id: string) => void;
  stats: Stats;
  setStats: (stats: Stats) => void;
  /** Re-read the league from ESPN. */
  reload: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("no league session");
  return session;
}

function useStored(storage: Storage, key: string, fallback: string) {
  const [value, setValue] = useState(storage.getItem(key) ?? fallback);
  const store = (next: string) => {
    storage.setItem(key, next);
    setValue(next);
  };
  return [value, store] as const;
}

/** Loads the chosen league and provides it to the pages below. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  // per tab: a new one starts on the configured default league
  const [chosen, setLeague] = useStored(sessionStorage, "league", "");
  const [stats, setStats] = useStored(localStorage, "stats", "blended");
  const leagues = useQuery({
    queryKey: ["leagues"],
    queryFn: () => request<LeagueInfo[]>(apiUrl("/leagues")),
  });
  const league =
    leagues.data?.find((entry) => entry.id === chosen) ??
    leagues.data?.find((entry) => entry.default) ??
    leagues.data?.[0];
  const meta = useQuery({
    queryKey: ["meta", league?.id],
    queryFn: () => request<LeagueMeta>(apiUrl(`/leagues/${league!.id}`)),
    enabled: league !== undefined,
  });

  if (leagues.error) {
    return <p className="note note-warning">{leagues.error.message}</p>;
  }
  if (!leagues.data || !league) {
    return <p className="note note-info">Loading leagues…</p>;
  }
  if (!meta.data) {
    // a league that does not load must not lock the others away
    return (
      <main>
        <label className="field">
          <span>League</span>
          <select
            value={league.id}
            onChange={(event) => setLeague(event.target.value)}
          >
            {leagues.data.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name} ({entry.year})
              </option>
            ))}
          </select>
        </label>
        {meta.error ? (
          <>
            <p className="note note-warning">{meta.error.message}</p>
            <button onClick={() => meta.refetch()}>Try again</button>
          </>
        ) : (
          <p className="note note-info">Loading league data from ESPN…</p>
        )}
      </main>
    );
  }
  const session: Session = {
    leagues: leagues.data,
    meta: meta.data,
    setLeague,
    stats: stats === "season" ? "season" : "blended",
    setStats,
    reload: async () => {
      await request(apiUrl(`/leagues/${meta.data.id}/reload`), "POST");
      await queryClient.invalidateQueries();
    },
  };
  return (
    <SessionContext.Provider value={session}>{children}</SessionContext.Provider>
  );
}
