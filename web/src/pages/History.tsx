import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiUrl, request, type HistoryOptions } from "../api";
import { Field, Page, Select } from "../components/controls";
import { useViewAt, ViewPanel } from "../components/View";
import { usePageParams } from "../params";

const COLUMNS = [
  { value: "fantasy", label: "Fantasy categories" },
  { value: "all", label: "All" },
];
const CELLS = [
  { value: "total", label: "Season totals" },
  { value: "rate", label: "Per game" },
];

/** A player's stored NHL seasons. It belongs to no league and asks
 * nothing from ESPN. */
export function PlayerHistory() {
  const page = usePageParams();
  const player = page.get("player");
  const columns = page.get("columns") === "all" ? "all" : "fantasy";
  const cells = page.get("cells") === "rate" ? "rate" : "total";

  const url = apiUrl("/history/players");
  const optionsQuery = useQuery({
    queryKey: [url],
    queryFn: () => request<HistoryOptions>(url),
  });
  const options = optionsQuery.data;
  const seasons = options?.seasons ?? [];
  const stored = options === undefined || seasons.length > 0;
  const query = useViewAt(
    apiUrl("/history/player", { player, columns, cells }),
    player !== "" && stored,
  );

  return (
    <Page
      title="Player history"
      controls={
        options &&
        stored && (
          <>
            <PlayerSearch
              choices={options.players}
              picked={player}
              onPick={(id) => page.set({ player: id })}
            />
            <Select
              label="Columns"
              value={columns}
              options={COLUMNS}
              onChange={(next) => page.set({ columns: next === "all" ? next : null })}
            />
            <Select
              label="Cells show"
              value={cells}
              options={CELLS}
              onChange={(next) => page.set({ cells: next === "rate" ? next : null })}
            />
          </>
        )
      }
    >
      {optionsQuery.error ? (
        <>
          <p className="note note-warning">{optionsQuery.error.message}</p>
          <button onClick={() => optionsQuery.refetch()}>Try again</button>
        </>
      ) : !options ? (
        <p className="note note-info">Loading…</p>
      ) : !stored ? (
        <p className="note note-info">
          No NHL seasons are stored yet. Download some with{" "}
          <code>fantasy-nhl-history</code> (see the README) and reload this page.
        </p>
      ) : player ? (
        <ViewPanel query={query} />
      ) : (
        <p className="note note-info">
          Pick a player to see his seasons. Stored: {seasons[0]}
          {seasons.length > 1 && ` to ${seasons[seasons.length - 1]}`}.
        </p>
      )}
    </Page>
  );
}

/** Find a player by name: a listed label, typed or chosen, picks him. */
function PlayerSearch({
  choices,
  picked,
  onPick,
}: {
  choices: HistoryOptions["players"];
  picked: string;
  onPick: (id: number) => void;
}) {
  // what is being typed; otherwise the field names the picked player
  const [text, setText] = useState<string | null>(null);
  const current = choices.find((choice) => String(choice.id) === picked)?.label ?? "";
  const type = (value: string) => {
    const match = choices.find((choice) => choice.label === value);
    if (match) onPick(match.id);
    setText(match ? null : value);
  };
  return (
    <Field label="Player">
      <input
        list="history-players"
        size={30}
        placeholder="Type a name…"
        value={text ?? current}
        onChange={(event) => type(event.target.value)}
        // typing replaces the name that stands there
        onFocus={(event) => event.target.select()}
        onBlur={() => setText(null)}
      />
      <datalist id="history-players">
        {choices.map((choice) => (
          <option key={choice.id} value={choice.label} />
        ))}
      </datalist>
    </Field>
  );
}
