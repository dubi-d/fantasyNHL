import { useState } from "react";

import type { ReviewOptions } from "../api";
import {
  Group,
  Page,
  Select,
  useReviewOptions,
  useTeamOptions,
} from "../components/controls";
import { useView, ViewPanel } from "../components/View";
import { clamp, usePageParams } from "../params";
import { useSession } from "../session";

const COMPARE_MAX = 4;
const VIEWS = [
  { value: "leaders", label: "Player ranking" },
  { value: "compare", label: "Compare players" },
];

export function Players() {
  const { stats } = useSession();
  const teams = useTeamOptions();
  const page = usePageParams();
  const compare = page.get("view") === "compare";
  const scope = page.get("scope", "all");
  const team = clamp(page.get("team", "0"), 0, teams.length - 1);
  const group = page.get("group", "F");
  const sort = page.get("sort", "Score");
  const cells = page.get("cells", "pct");
  const players = page.list("players").map(Number);

  const optionsQuery = useReviewOptions();
  const options = optionsQuery.data;
  const groups = options?.groups ?? [];
  const sorts = groups.find((entry) => entry.key === group)?.sorts ?? ["Score"];
  const cellChoices = options?.cells ?? [];
  // choices of another group or stats setting fall back to the defaults
  const usedSort = sorts.includes(sort) ? sort : "Score";
  const usedCells = cellChoices.some((c) => c.key === cells) ? cells : "pct";

  const params = compare
    ? { stats, players, cells: usedCells }
    : {
        stats,
        scope,
        team: scope === "team" ? team : null,
        group,
        sort: usedSort,
        cells: usedCells,
      };
  const ready = !compare || players.length >= 2;
  const query = useView(
    compare ? "/review/compare" : "/review/leaders",
    params,
    ready,
  );

  return (
    <Page
      title="Players"
      controls={
        <>
          <Select
            label="View"
            value={compare ? "compare" : "leaders"}
            options={VIEWS}
            onChange={(next) => page.set({ view: next })}
          />
          {!compare && (
            <>
              <Select
                label="Players"
                value={scope}
                options={[
                  { value: "all", label: "Whole pool" },
                  { value: "fa", label: "Free agents" },
                  { value: "team", label: "One team" },
                ]}
                onChange={(next) => page.set({ scope: next })}
              />
              {scope === "team" && (
                <Select
                  label="Team"
                  value={team}
                  options={teams}
                  onChange={(next) => page.set({ team: next })}
                />
              )}
              <Select
                label="Position"
                value={group}
                options={groups.map((entry) => ({
                  value: entry.key,
                  label: entry.label,
                }))}
                onChange={(next) => page.set({ group: next })}
              />
              <Select
                label="Sort by"
                value={usedSort}
                options={sorts.map((name) => ({ value: name, label: name }))}
                onChange={(next) => page.set({ sort: next })}
              />
            </>
          )}
          <Select
            label="Cells show"
            value={usedCells}
            options={cellChoices.map((choice) => ({
              value: choice.key,
              label: choice.label,
            }))}
            onChange={(next) => page.set({ cells: next })}
          />
          {compare && options && (
            <PlayerPicker
              choices={options.players}
              picked={players}
              onChange={(ids) => page.set({ players: ids })}
            />
          )}
        </>
      }
    >
      {optionsQuery.error ? (
        <>
          <p className="note note-warning">{optionsQuery.error.message}</p>
          <button onClick={() => optionsQuery.refetch()}>Try again</button>
        </>
      ) : !options ? (
        <p className="note note-info">Loading…</p>
      ) : ready ? (
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
    <Group label={`Players (${picked.length} of 2-${COMPARE_MAX})`}>
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
              aria-label="Add a player"
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
    </Group>
  );
}
