import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  apiUrl,
  request,
  type CalibrationInfo,
  type OutlookView,
  type View,
} from "../api";
import { Field, Page, Select, useTeamOptions } from "../components/controls";
import { currentMeta, useView, ViewBlocks, ViewPanel } from "../components/View";
import { usePageParams } from "../params";
import { useSession } from "../session";

export function ScheduleOutlook() {
  const { meta } = useSession();
  const page = usePageParams();
  const teams = useTeamOptions();
  const scope = page.get("scope", "full");
  const weight = page.get("weight", "0.4");
  const fitTeam = page.get("fit");
  const sort = page.get("sort");

  const fitted = scope !== "full";
  const outlook = useView<OutlookView>("/schedule/outlook", {
    scope,
    playoff_weight: scope === "playoffs" ? null : weight,
    fit_team: fitted ? fitTeam : null,
    sort,
  });
  const shown = currentMeta(outlook);
  const sorts = shown?.sorts ?? [];
  // nothing to weight in a scope without both season and playoff matchups
  const blends = shown?.blends_playoffs ?? scope !== "playoffs";

  return (
    <Page
      title="NHL schedule outlook"
      controls={
        <>
          <Select
            label="Scope"
            value={scope}
            options={[
              { value: "full", label: "Full season" },
              {
                value: "remaining",
                label: `Remaining matchups (from matchup ${meta.current_week})`,
              },
              { value: "playoffs", label: "Playoffs only" },
            ]}
            onChange={(next) => page.set({ scope: next, sort: null })}
          />
          {blends && (
            <Field label="Playoff weight in Combined score (0-1)">
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={weight}
                onChange={(event) => page.set({ weight: event.target.value }, true)}
              />
            </Field>
          )}
          {fitted && (
            <Select
              label="Weight by a roster's open seats (Fit)"
              value={fitTeam}
              options={[{ value: "", label: "Skip" }, ...teams]}
              onChange={(next) => page.set({ fit: next, sort: null })}
            />
          )}
          {sorts.length > 1 && (
            <Select
              label="Sort by"
              value={sort || sorts[0]}
              options={sorts.map((name) => ({ value: name, label: name }))}
              onChange={(next) => page.set({ sort: next })}
            />
          )}
        </>
      }
    >
      <ViewPanel query={outlook} />
      <Calibration />
    </Page>
  );
}

/** Fit the night-value curve on a league season and keep it. */
function Calibration() {
  const { leagues, meta } = useSession();
  const queryClient = useQueryClient();
  const [source, setSource] = useState(leagues[0].id);
  const url = apiUrl(`/leagues/${meta.id}/schedule/calibration`);
  const curve = useMutation({
    mutationFn: () => request<View>(url, "POST", { source }),
  });
  const store = useMutation({
    mutationFn: () => request<CalibrationInfo>(url, "PUT", { source }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const error = curve.error ?? store.error;

  return (
    <details className="panel">
      <summary>
        Calibrate scoring
        {meta.calibration
          ? ` (calibrated on ${meta.calibration.source}, ${meta.calibration.calibrated})`
          : " (uncalibrated)"}
      </summary>
      <div className="controls">
        <Select
          label="Calibrate from which league season?"
          value={source}
          options={leagues.map((league) => ({
            value: league.id,
            label: `${league.name} (${league.year})`,
          }))}
          onChange={(next) => {
            setSource(next);
            curve.reset();
          }}
        />
        <button onClick={() => curve.mutate()} disabled={curve.isPending}>
          Show curve
        </button>
        <button onClick={() => store.mutate()} disabled={store.isPending}>
          Save as calibration for {meta.name}
        </button>
      </div>
      {error && <p className="note note-warning">{error.message}</p>}
      {curve.data && <ViewBlocks view={curve.data} />}
    </details>
  );
}
