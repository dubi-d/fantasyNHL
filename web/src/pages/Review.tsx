import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiUrl, request, type ReviewOptions } from "../api";
import { Field, Page, Select, useTeamOptions } from "../components/controls";
import { useView, ViewPanel } from "../components/View";
import { useSession } from "../session";

const COMPARE_MAX = 4;
const VIEWS = [
  { group: "Players", value: "leaders", label: "Category leaderboard" },
  { group: "Players", value: "compare", label: "Compare players" },
  { group: "League", value: "origins", label: "Roster origins" },
  { group: "League", value: "outlook", label: "Category outlook" },
  { group: "Draft", value: "draft-grades", label: "Draft grades vs ADP" },
  { group: "Draft", value: "draft-return", label: "Draft hits & busts" },
  { group: "Transactions", value: "pickups", label: "Waiver pickups" },
  { group: "Transactions", value: "trades", label: "Trade haul" },
  { group: "One team", value: "team", label: "Team roster" },
  { group: "One team", value: "gaps", label: "Drop candidates & free agents" },
];
const SOURCES = [
  { value: "draft", label: "As drafted" },
  { value: "current", label: "Current" },
];

export function Review() {
  const { meta, stats } = useSession();
  const teams = useTeamOptions();
  const [view, setView] = useState("leaders");
  const [scope, setScope] = useState("all");
  const [team, setTeam] = useState("0");
  const [group, setGroup] = useState("F");
  const [sort, setSort] = useState("Score");
  const [cells, setCells] = useState("pct");
  const [source, setSource] = useState("current");
  const [players, setPlayers] = useState<number[]>([]);

  const optionsUrl = apiUrl(`/leagues/${meta.id}/review/options`, { stats });
  const options = useQuery({
    queryKey: [optionsUrl],
    queryFn: () => request<ReviewOptions>(optionsUrl),
  }).data;
  const groups = options?.groups ?? [];
  const sorts = groups.find((entry) => entry.key === group)?.sorts ?? ["Score"];
  const cellChoices = options?.cells ?? [];
  // choices of another group or stats setting fall back to the defaults
  const usedSort = sorts.includes(sort) ? sort : "Score";
  const usedCells = cellChoices.some((c) => c.key === cells) ? cells : "pct";
  const sourced = options?.drafted && (view === "outlook" || view === "team");

  const params = {
    stats,
    ...(view === "leaders" && {
      scope,
      team: scope === "team" ? team : null,
      group,
      sort: usedSort,
      cells: usedCells,
    }),
    ...(view === "compare" && { players }),
    ...(sourced && { source }),
    ...((view === "team" || view === "gaps") && { team }),
  };
  const ready = view !== "compare" || players.length >= 2;
  const query = useView(`/review/${view}`, params, ready);

  return (
    <Page
      title="Players, rosters & draft"
      controls={
        <>
          <Field label="View">
            <select value={view} onChange={(event) => setView(event.target.value)}>
              {[...new Set(VIEWS.map((entry) => entry.group))].map((name) => (
                <optgroup key={name} label={name}>
                  {VIEWS.filter((entry) => entry.group === name).map((entry) => (
                    <option key={entry.value} value={entry.value}>
                      {entry.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>
          {view === "leaders" && (
            <>
              <Select
                label="Players"
                value={scope}
                options={[
                  { value: "all", label: "Whole pool" },
                  { value: "fa", label: "Free agents" },
                  { value: "team", label: "One team" },
                ]}
                onChange={setScope}
              />
              <Select
                label="Position"
                value={group}
                options={groups.map((entry) => ({
                  value: entry.key,
                  label: entry.label,
                }))}
                onChange={setGroup}
              />
              <Select
                label="Sort by"
                value={usedSort}
                options={sorts.map((name) => ({ value: name, label: name }))}
                onChange={setSort}
              />
              <Select
                label="Cells show"
                value={usedCells}
                options={cellChoices.map((choice) => ({
                  value: choice.key,
                  label: choice.label,
                }))}
                onChange={setCells}
              />
            </>
          )}
          {(view === "team" ||
            view === "gaps" ||
            (view === "leaders" && scope === "team")) && (
            <Select label="Team" value={team} options={teams} onChange={setTeam} />
          )}
          {sourced && (
            <Select
              label="Rosters"
              value={source}
              options={SOURCES}
              onChange={setSource}
            />
          )}
          {view === "compare" && options && (
            <PlayerPicker
              choices={options.players}
              picked={players}
              onChange={setPlayers}
            />
          )}
        </>
      }
    >
      {ready ? (
        <ViewPanel query={query} />
      ) : (
        <p className="note note-info">Pick two to four skaters or goalies.</p>
      )}
    </Page>
  );
}

/** Pick players by name; skaters and goalies cannot be mixed. */
function PlayerPicker({
  choices,
  picked,
  onChange,
}: {
  choices: ReviewOptions["players"];
  picked: number[];
  onChange: (ids: number[]) => void;
}) {
  const [text, setText] = useState("");
  const chosen = picked.flatMap(
    (id) => choices.find((choice) => choice.id === id) ?? [],
  );
  const open = choices.filter(
    (choice) =>
      !picked.includes(choice.id) &&
      (chosen.length === 0 || choice.goalie === chosen[0].goalie),
  );
  const type = (value: string) => {
    const match = open.find((choice) => choice.label === value);
    if (match) onChange([...picked, match.id]);
    setText(match ? "" : value);
  };
  return (
    <Field label={`Players (${picked.length} of 2-${COMPARE_MAX})`}>
      <div className="picker">
        {chosen.map((choice) => (
          <button
            key={choice.id}
            title="Remove"
            onClick={() => onChange(picked.filter((id) => id !== choice.id))}
          >
            {choice.label} ×
          </button>
        ))}
        {picked.length < COMPARE_MAX && (
          <>
            <input
              list="player-choices"
              placeholder="Type a name…"
              value={text}
              onChange={(event) => type(event.target.value)}
            />
            <datalist id="player-choices">
              {open.map((choice) => (
                <option key={choice.id} value={choice.label} />
              ))}
            </datalist>
          </>
        )}
      </div>
    </Field>
  );
}
