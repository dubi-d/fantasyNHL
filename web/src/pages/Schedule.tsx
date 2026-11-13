import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiUrl, request, type CalibrationInfo, type View } from "../api";
import { Field, Page, Select, useTeamOptions } from "../components/controls";
import { useView, ViewBlocks, ViewPanel } from "../components/View";
import { useSession } from "../session";

type OutlookMeta = { sorts?: string[]; blends_playoffs?: boolean };

export function ScheduleOutlook() {
  const { meta } = useSession();
  const teams = useTeamOptions();
  const [scope, setScope] = useState("full");
  const [weight, setWeight] = useState("0.4");
  const [fitTeam, setFitTeam] = useState("");
  const [sort, setSort] = useState("");

  const fitted = scope !== "full";
  const outlook = useView("/schedule/outlook", {
    scope,
    playoff_weight: scope === "playoffs" ? null : weight,
    fit_team: fitted ? fitTeam : null,
    sort,
  });
  const outlookMeta = (outlook.data?.meta ?? {}) as OutlookMeta;
  const sorts = outlookMeta.sorts ?? [];
  // nothing to weight in a scope without both season and playoff matchups
  const blends = outlookMeta.blends_playoffs ?? scope !== "playoffs";

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
            onChange={(next) => {
              setScope(next);
              setSort("");
            }}
          />
          {blends && (
            <Field label="Playoff weight in Combined score (0-1)">
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={weight}
                onChange={(event) => setWeight(event.target.value)}
              />
            </Field>
          )}
          {fitted && (
            <Select
              label="Weight by a roster's open seats (Fit)"
              value={fitTeam}
              options={[{ value: "", label: "Skip" }, ...teams]}
              onChange={(next) => {
                setFitTeam(next);
                setSort("");
              }}
            />
          )}
          {sorts.length > 1 && (
            <Select
              label="Sort by"
              value={sort || sorts[0]}
              options={sorts.map((name) => ({ value: name, label: name }))}
              onChange={setSort}
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
