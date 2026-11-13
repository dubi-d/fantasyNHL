import { useState } from "react";

import { Field, Page, Select, useWeekOptions } from "../components/controls";
import { RemoteView } from "../components/View";
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
  const weeks = useWeekOptions(true);
  const [week, setWeek] = useState(String(meta.completed_matchups));
  return (
    <Page
      title="Weekly awards"
      controls={
        weeks.length > 0 && (
          <Select label="Matchup" value={week} options={weeks} onChange={setWeek} />
        )
      }
    >
      <RemoteView path="/weekly/awards" params={{ week: weeks.length ? week : null }} />
    </Page>
  );
}

export function PowerRankings() {
  const { meta } = useSession();
  const completed = meta.completed_matchups;
  const [span, setSpan] = useState(Math.min(4, completed));
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
              onChange={(event) =>
                setSpan(
                  Math.max(2, Math.min(completed, Number(event.target.value))),
                )
              }
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
  const weeks = useWeekOptions();
  const [week, setWeek] = useState(String(meta.current_week));
  return (
    <Page
      title="Matchup preview"
      controls={
        <Select label="Matchup" value={week} options={weeks} onChange={setWeek} />
      }
    >
      <RemoteView path="/preview" params={{ week, stats }} />
    </Page>
  );
}
