import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

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
  /** Why the league shown could not be refreshed, if it could not. */
  refreshError: string | null;
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

/** Loads the league the address names (#/<league>/<page>) and provides it
 * to the pages below. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [stats, setStats] = useStored(localStorage, "stats", "blended");
  const leagues = useQuery({
    queryKey: ["leagues"],
    queryFn: () => request<LeagueInfo[]>(apiUrl("/leagues")),
  });
  const [, first = "", ...page] = location.pathname.split("/");
  const league = leagues.data?.find((entry) => entry.id === first);
  const meta = useQuery({
    queryKey: ["meta", league?.id],
    queryFn: () => request<LeagueMeta>(apiUrl(`/leagues/${league!.id}`)),
    enabled: league !== undefined,
  });
  const leagueId = league?.id;
  useEffect(() => {
    // per tab: a new one starts on the configured default league
    if (leagueId) sessionStorage.setItem("league", leagueId);
  }, [leagueId]);

  if (leagues.error) {
    return <p className="note note-warning">{leagues.error.message}</p>;
  }
  if (!leagues.data) {
    return <p className="note note-info">Loading leagues…</p>;
  }
  if (leagues.data.length === 0) {
    return (
      <p className="note note-warning">
        No leagues are configured: add one to config.yaml and restart the
        server.
      </p>
    );
  }
  if (!league) {
    // an address without league: this tab's last one, else the default
    const last = sessionStorage.getItem("league");
    const start =
      leagues.data.find((entry) => entry.id === last) ??
      leagues.data.find((entry) => entry.default) ??
      leagues.data[0];
    const rest = location.pathname === "/" ? "" : location.pathname;
    return <Navigate replace to={`/${start.id}${rest}${location.search}`} />;
  }
  // the choices of a page belong to its league: they are not carried over
  const setLeague = (id: string) => navigate(`/${id}/${page.join("/")}`);
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
    refreshError: meta.error?.message ?? null,
  };
  return (
    <SessionContext.Provider value={session}>{children}</SessionContext.Provider>
  );
}
