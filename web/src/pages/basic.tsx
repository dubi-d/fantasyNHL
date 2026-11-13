import { Field, Page, Select, useWeekOptions } from "../components/controls";
import { RemoteView } from "../components/View";
import { clamp, usePageParams } from "../params";
import { useSession } from "../session";

/** A view without choices of its own. */
export function SimplePage({ title, path }: { title: string; path: string }) {
  return (
    <Page title={title}>
      <RemoteView path={path} />
    </Page>
  );
}

export function WeeklyAwards() {
  const { meta } = useSession();
  const page = usePageParams();
  const weeks = useWeekOptions(true);
  // the latest completed matchup unless another one was chosen
  const week = clamp(
    page.get("week", String(meta.completed_matchups)),
    1,
    meta.completed_matchups,
  );
  return (
    <Page
      title="Weekly awards"
      controls={
        weeks.length > 0 && (
          <Select
            label="Matchup"
            value={week}
            options={weeks}
            onChange={(next) => page.set({ week: next })}
          />
        )
      }
    >
      <RemoteView path="/weekly/awards" params={{ week: weeks.length ? week : null }} />
    </Page>
  );
}

export function PowerRankings() {
  const { meta } = useSession();
  const page = usePageParams();
  const completed = meta.completed_matchups;
  const span = clamp(page.get("window", String(Math.min(4, completed))), 2, completed);
  return (
    <Page
      title="Power rankings over time"
      controls={
        completed >= 2 && (
          <Field label={`Hot-streak window in matchups (2-${completed})`}>
            <input
              type="number"
              min={2}
              max={completed}
              value={span}
              onChange={(event) => page.set({ window: event.target.value }, true)}
            />
          </Field>
        )
      }
    >
      <RemoteView
        path="/standings/power-rankings"
        params={{ window: completed >= 2 ? span : null }}
      />
    </Page>
  );
}

export function MatchupPreview() {
  const { meta, stats } = useSession();
  const page = usePageParams();
  const weeks = useWeekOptions();
  const week = clamp(page.get("week", String(meta.current_week)), 1, weeks.length);
  return (
    <Page
      title="Matchup preview"
      controls={
        <Select
          label="Matchup"
          value={week}
          options={weeks}
          onChange={(next) => page.set({ week: next })}
        />
      }
    >
      <RemoteView path="/preview" params={{ week, stats }} />
    </Page>
  );
}
