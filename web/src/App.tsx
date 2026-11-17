import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import type { Stats } from "./api";
import { Select } from "./components/controls";
import {
  DraftRecap,
  MatchupPreview,
  PowerRankings,
  SimplePage,
  Transactions,
  WeeklyAwards,
} from "./pages/basic";
import { StreamingPlanner } from "./pages/Planner";
import { Players } from "./pages/Players";
import { Roster } from "./pages/Roster";
import { ScheduleOutlook } from "./pages/Schedule";
import { useSession } from "./session";

// the terminal's menu, its last tool as four pages: group -> (label, path, page)
const MENU = [
  {
    group: "Weekly",
    pages: [
      {
        label: "Weekly scores",
        path: "/weekly/scores",
        element: <SimplePage title="Weekly scores" path="/weekly/scores" />,
      },
      { label: "Weekly awards", path: "/weekly/awards", element: <WeeklyAwards /> },
    ],
  },
  {
    group: "Season standings",
    pages: [
      {
        label: "Accumulated scores",
        path: "/standings/accumulated",
        element: (
          <SimplePage title="Accumulated scores" path="/standings/accumulated" />
        ),
      },
      {
        label: "Luck ranking",
        path: "/standings/luck",
        element: <SimplePage title="Luck ranking" path="/standings/luck" />,
      },
      {
        label: "Power rankings",
        path: "/standings/power-rankings",
        element: <PowerRankings />,
      },
      {
        label: "Category strength",
        path: "/standings/category-profile",
        element: (
          <SimplePage
            title="Category strength profile"
            path="/standings/category-profile"
          />
        ),
      },
    ],
  },
  {
    group: "Roster planning",
    pages: [
      { label: "Matchup preview", path: "/preview", element: <MatchupPreview /> },
      { label: "Streaming planner", path: "/streaming", element: <StreamingPlanner /> },
      { label: "Schedule outlook", path: "/schedule", element: <ScheduleOutlook /> },
    ],
  },
  {
    group: "Players & rosters",
    pages: [
      { label: "Players", path: "/players", element: <Players /> },
      { label: "Roster", path: "/roster", element: <Roster /> },
      { label: "Draft recap", path: "/draft", element: <DraftRecap /> },
      { label: "Transactions", path: "/transactions", element: <Transactions /> },
    ],
  },
];

export function App() {
  const { leagues, meta, setLeague, stats, setStats, reload, refreshError } =
    useSession();
  const [reloading, setReloading] = useState(false);
  const [reloadError, setReloadError] = useState("");
  const refresh = async () => {
    setReloading(true);
    setReloadError("");
    try {
      await reload();
    } catch (error) {
      setReloadError(error instanceof Error ? error.message : String(error));
    } finally {
      setReloading(false);
    }
  };
  const loaded = new Date(meta.loaded_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  const problems = [reloadError, refreshError, ...meta.warnings].filter(Boolean);
  return (
    <div className="layout">
      <nav>
        <h1>fantasyNHL</h1>
        <Select
          label="League"
          value={meta.id}
          options={leagues.map((league) => ({
            value: league.id,
            label: `${league.name} (${league.year})`,
          }))}
          onChange={setLeague}
        />
        <Select
          label="Player stats"
          value={stats}
          options={[
            { value: "blended", label: "Blended (season + projection)" },
            { value: "season", label: "This season only" },
          ]}
          onChange={(next) => setStats(next as Stats)}
        />
        <div className="field">
          <button onClick={refresh} disabled={reloading}>
            {reloading ? "Reloading…" : "Reload from ESPN"}
          </button>
          <span title="When the league was read from ESPN">as of {loaded}</span>
        </div>
        {problems.map((problem) => (
          <p key={problem} className="note note-warning">
            {problem}
          </p>
        ))}
        {MENU.map((entry) => (
          <div key={entry.group}>
            <h3>{entry.group}</h3>
            {entry.pages.map((page) => (
              <NavLink key={page.path} to={`/${meta.id}${page.path}`}>
                {page.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {/* pages start over when the league changes */}
      <main key={meta.id}>
        <Routes>
          {MENU.flatMap((entry) => entry.pages).map((page) => (
            <Route
              key={page.path}
              path={`/:league${page.path}`}
              element={page.element}
            />
          ))}
          <Route
            path="*"
            element={<Navigate replace to={`/${meta.id}/standings/accumulated`} />}
          />
        </Routes>
      </main>
    </div>
  );
}
