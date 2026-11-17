import {
  Page,
  Select,
  useReviewOptions,
  useTeamOptions,
} from "../components/controls";
import { useView, ViewStack } from "../components/View";
import { clamp, usePageParams } from "../params";
import { useSession } from "../session";

const VIEWS = [
  { value: "league", label: "League" },
  { value: "team", label: "One team" },
];
const SOURCES = [
  { value: "draft", label: "As drafted" },
  { value: "current", label: "Current" },
];

export function Roster() {
  const { stats } = useSession();
  const teams = useTeamOptions();
  const page = usePageParams();
  const oneTeam = page.get("view") === "team";
  const team = oneTeam ? clamp(page.get("team", "0"), 0, teams.length - 1) : null;
  const options = useReviewOptions();
  // rosters as drafted exist only once the league has drafted
  const drafted = options.data?.drafted ?? false;
  const asDrafted = page.get("source") === "draft";
  const source = drafted && asDrafted ? "draft" : "current";
  // one team's players come with the columns of the player ranking
  const cellChoices = options.data?.cells ?? [];
  const chosen = oneTeam ? page.get("cells") : "";
  const cells = cellChoices.some((c) => c.key === chosen) ? chosen : "pct";
  // a linked choice the options decide on is not asked for before them
  const known = !options.isPending;

  // the upper view follows the Rosters choice, the lower one is always today
  const upper = useView(
    oneTeam ? "/review/team" : "/review/outlook",
    {
      stats,
      team,
      cells: oneTeam ? cells : null,
      source: source === "draft" ? source : null,
    },
    known || !(asDrafted || chosen),
  );
  const lower = useView(
    oneTeam ? "/review/gaps" : "/review/origins",
    { stats, team, cells: oneTeam ? cells : null },
    known || !chosen,
  );

  return (
    <Page
      title="Roster"
      controls={
        <>
          <Select
            label="View"
            value={oneTeam ? "team" : "league"}
            options={VIEWS}
            onChange={(next) => page.set({ view: next })}
          />
          {team !== null && (
            <Select
              label="Team"
              value={team}
              options={teams}
              onChange={(next) => page.set({ team: next })}
            />
          )}
          {drafted && (
            <Select
              label="Rosters"
              value={source}
              options={SOURCES}
              onChange={(next) => page.set({ source: next })}
            />
          )}
          {oneTeam && cellChoices.length > 0 && (
            <Select
              label="Cells show"
              value={cells}
              options={cellChoices.map((choice) => ({
                value: choice.key,
                label: choice.label,
              }))}
              onChange={(next) => page.set({ cells: next })}
            />
          )}
        </>
      }
    >
      <ViewStack queries={[upper, lower]} />
    </Page>
  );
}
