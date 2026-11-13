import { useState } from "react";

import {
  Group,
  Page,
  Select,
  useTeamOptions,
  useWeekOptions,
} from "../components/controls";
import { RemoteView, useView, ViewPanel } from "../components/View";
import { useSession } from "../session";

const PAGE_SIZE = 15;

type PlanMeta = {
  roster?: string[];
  days?: { period: number; label: string }[];
  finished?: boolean;
  has_open_days?: boolean;
};

export function StreamingPlanner() {
  const { meta, stats } = useSession();
  const weeks = useWeekOptions();
  const teams = useTeamOptions();
  const [week, setWeek] = useState(String(meta.current_week));
  const stored = localStorage.getItem("team") ?? "";
  const [team, setTeam] = useState(
    teams.some((option) => String(option.value) === stored) ? stored : "0",
  );
  const [streamers, setStreamers] = useState<string[]>([]);
  const [simulate, setSimulate] = useState("");
  const [candidates, setCandidates] = useState(false);

  // streamers and the simulated day belong to one team's week
  const choose = (nextWeek: string, nextTeam: string) => {
    localStorage.setItem("team", nextTeam);
    setWeek(nextWeek);
    setTeam(nextTeam);
    setStreamers([]);
    setSimulate("");
  };
  const params = { week, team, streamers, simulate };
  const plan = useView("/streaming/plan", params);
  const info = (plan.data?.meta ?? {}) as PlanMeta;
  const toggle = (name: string) =>
    setStreamers(
      streamers.includes(name)
        ? streamers.filter((other) => other !== name)
        : [...streamers, name],
    );

  return (
    <Page
      title="Streaming planner"
      controls={
        <>
          <Select
            label="Matchup"
            value={week}
            options={weeks}
            onChange={(next) => choose(next, team)}
          />
          <Select
            label="Your team"
            value={team}
            options={teams}
            onChange={(next) => choose(week, next)}
          />
          {info.finished && (
            <Select
              label="Week is over — simulate it from"
              value={simulate}
              options={[
                { value: "", label: "No, just show the roster grid" },
                ...(info.days ?? []).map((day) => ({
                  value: day.period,
                  label: `Plan as if today were ${day.label}`,
                })),
              ]}
              onChange={setSimulate}
            />
          )}
          {(!info.finished || simulate !== "") && (
            <Group label="Streamers (droppable roster spots)">
              <div className="checks">
                {(info.roster ?? []).map((name) => (
                  <label key={name}>
                    <input
                      type="checkbox"
                      checked={streamers.includes(name)}
                      onChange={() => toggle(name)}
                    />
                    {name}
                  </label>
                ))}
              </div>
            </Group>
          )}
        </>
      }
    >
      <ViewPanel query={plan} />
      {info.has_open_days && (
        <label className="toggle">
          <input
            type="checkbox"
            checked={candidates}
            onChange={() => setCandidates(!candidates)}
          />
          Show free agent candidates for the open days
        </label>
      )}
      {info.has_open_days && candidates && (
        <RemoteView
          path="/streaming/candidates"
          params={{ ...params, stats }}
          pageSize={PAGE_SIZE}
        />
      )}
    </Page>
  );
}
