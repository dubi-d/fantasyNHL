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

function useStored(key: string, fallback: string) {
  const [value, setValue] = useState(localStorage.getItem(key) ?? fallback);
  const store = (next: string) => {
    localStorage.setItem(key, next);
    setValue(next);
  };
  return [value, store] as const;
}

/** Loads the chosen league and provides it to the pages below. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [chosen, setLeague] = useStored("league", "");
  const [stats, setStats] = useStored("stats", "blended");
  const leagues = useQuery({
    queryKey: ["leagues"],
    queryFn: () => request<LeagueInfo[]>(apiUrl("/leagues")),
  });
  const league =
    leagues.data?.find((entry) => entry.id === chosen) ?? leagues.data?.[0];
  const meta = useQuery({
    queryKey: ["meta", league?.id],
    queryFn: () => request<LeagueMeta>(apiUrl(`/leagues/${league!.id}`)),
    enabled: league !== undefined,
  });

  const error = leagues.error ?? meta.error;
  if (error) return <p className="note note-warning">{error.message}</p>;
  if (!leagues.data || !meta.data) {
    return <p className="note note-info">Loading league data from ESPN…</p>;
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
