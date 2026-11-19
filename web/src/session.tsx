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

/** The first part of the one address that names no league. */
export const HISTORY = "history";

type Session = {
  leagues: LeagueInfo[];
  meta: LeagueMeta;
  stats: Stats;
  setStats: (stats: Stats) => void;
  /** Re-read the league from ESPN. */
  reload: () => Promise<void>;
  /** Why the league shown could not be refreshed, if it could not. */
  refreshError: string | null;
};

/** What every page has, whether a league is loaded or not. */
type Shell = {
  leagues: LeagueInfo[];
  /** The league the address names; none on the history page. */
  league?: LeagueInfo;
  /** The league the menu leads into: that of the address, else this
   * tab's last one. None only when none is configured. */
  home?: LeagueInfo;
  setLeague: (id: string) => void;
  /** The league of the address once it is loaded. */
  session: Session | null;
  /** Why it did not load, if it did not. */
  problem: string | null;
  retry: () => void;
};

const ShellContext = createContext<Shell | null>(null);

export function useShell(): Shell {
  const shell = useContext(ShellContext);
  if (!shell) throw new Error("no session provider");
  return shell;
}

/** The loaded league, for the pages that belong to one. */
export function useSession(): Session {
  const { session } = useShell();
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

/** Knows the leagues and loads the one the address names
 * (#/<league>/<page>); the history page (#/history) names none and loads
 * none. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [stats, setStats] = useStored(localStorage, "stats", "blended");
  // per tab: a new one starts on the configured default league
  const [last, setLast] = useStored(sessionStorage, "league", "");
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
    if (leagueId) setLast(leagueId);
  }, [leagueId]);

  if (leagues.error) {
    return <p className="note note-warning">{leagues.error.message}</p>;
  }
  if (!leagues.data) {
    return <p className="note note-info">Loading leagues…</p>;
  }
  const home =
    league ??
    leagues.data.find((entry) => entry.id === last) ??
    leagues.data.find((entry) => entry.default) ??
    leagues.data[0];
  if (!league && home && first !== HISTORY) {
    // an address without league: this tab's last one, else the default
    const rest = location.pathname === "/" ? "" : location.pathname;
    return <Navigate replace to={`/${home.id}${rest}${location.search}`} />;
  }
  const setLeague = (id: string) =>
    // the choices of a page belong to its league: they are not carried over
    league ? navigate(`/${id}/${page.join("/")}`) : setLast(id);
  const shell: Shell = {
    leagues: leagues.data,
    league,
    home,
    setLeague,
    session: meta.data
      ? {
          leagues: leagues.data,
          meta: meta.data,
          stats: stats === "season" ? "season" : "blended",
          setStats,
          reload: async () => {
            await request(apiUrl(`/leagues/${meta.data.id}/reload`), "POST");
            await queryClient.invalidateQueries();
          },
          refreshError: meta.error?.message ?? null,
        }
      : null,
    problem: meta.data ? null : (meta.error?.message ?? null),
    retry: () => void meta.refetch(),
  };
  return <ShellContext.Provider value={shell}>{children}</ShellContext.Provider>;
}
