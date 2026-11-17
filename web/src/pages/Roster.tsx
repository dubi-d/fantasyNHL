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
  // rosters as drafted exist only once the league has drafted
  const options = useReviewOptions();
  const drafted = options.data?.drafted ?? false;
  const asDrafted = page.get("source") === "draft";
  const source = drafted && asDrafted ? "draft" : "current";

  // the upper view follows the Rosters choice, the lower one is always today
  const upper = useView(
    oneTeam ? "/review/team" : "/review/outlook",
    { stats, team, source: source === "draft" ? source : null },
    // a linked "as drafted" is not asked for as current first
    !asDrafted || !options.isPending,
  );
  const lower = useView(oneTeam ? "/review/gaps" : "/review/origins", {
    stats,
    team,
  });

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
        </>
      }
    >
      <ViewStack queries={[upper, lower]} />
    </Page>
  );
}
