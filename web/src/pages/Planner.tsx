import { useRef } from "react";

import type { PlanView } from "../api";
import {
  Group,
  Page,
  Select,
  useTeamOptions,
  useWeekOptions,
} from "../components/controls";
import { currentMeta, RemoteView, useView, ViewPanel } from "../components/View";
import { clamp, usePageParams } from "../params";
import { useSession } from "../session";

const PAGE_SIZE = 15;

export function StreamingPlanner() {
  const { meta, stats } = useSession();
  const page = usePageParams();
  const weeks = useWeekOptions();
  const teams = useTeamOptions();
  const week = clamp(page.get("week", String(meta.current_week)), 1, weeks.length);
  // the team planned last in this league, unless the address names one
  const teamKey = `team:${meta.id}`;
  const team = clamp(
    page.get("team", localStorage.getItem(teamKey) ?? "0"),
    0,
    teams.length - 1,
  );
  const streamers = page.list("streamers");
  const simulate = page.get("simulate");
  const candidates = page.get("candidates") === "1";

  // streamers and the simulated day belong to one team's week
  const choose = (nextWeek: string | number, nextTeam: string | number) => {
    localStorage.setItem(teamKey, String(nextTeam));
    page.set({ week: nextWeek, team: nextTeam, streamers: null, simulate: null });
  };
  const params = { week, team, streamers, simulate };
  const plan = useView<PlanView>("/streaming/plan", params);
  // the roster and days offered are those of this team's week: kept while
  // its plan reloads, never taken from the plan of another one
  const known = useRef<{ of: string; meta: PlanView["meta"] }>(undefined);
  const of = `${week}/${team}`;
  const current = currentMeta(plan);
  if (current) known.current = { of, meta: current };
  const info = known.current?.of === of ? known.current.meta : undefined;
  const toggle = (id: string) =>
    page.set({
      streamers: streamers.includes(id)
        ? streamers.filter((other) => other !== id)
        : [...streamers, id],
    });

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
          {info?.finished && (
            <Select
              label="Week is over — simulate it from"
              value={simulate}
              options={[
                { value: "", label: "No, just show the roster grid" },
                ...info.days.map((day) => ({
                  value: day.period,
                  label: `Plan as if today were ${day.label}`,
                })),
              ]}
              onChange={(next) => page.set({ simulate: next, streamers: null })}
            />
          )}
          {info && (!info.finished || simulate !== "") && (
            <Group label="Streamers (droppable roster spots)">
              <div className="checks">
                {info.roster.map((player) => (
                  <label key={player.id}>
                    <input
                      type="checkbox"
                      checked={streamers.includes(String(player.id))}
                      onChange={() => toggle(String(player.id))}
                    />
                    {player.name}
                  </label>
                ))}
              </div>
            </Group>
          )}
        </>
      }
    >
      <ViewPanel query={plan} />
      {info?.has_open_days && (
        <label className="toggle">
          <input
            type="checkbox"
            checked={candidates}
            onChange={() => page.set({ candidates: candidates ? null : 1 })}
          />
          Show free agent candidates for the open days
        </label>
      )}
      {info?.has_open_days && candidates && (
        <RemoteView
          path="/streaming/candidates"
          params={{ ...params, stats }}
          pageSize={PAGE_SIZE}
        />
      )}
    </Page>
  );
}
