/**
 * Track D: fetch the calibrated grid independent of any committed candidate.
 *
 * WHY THIS IS ITS OWN HOOK AND NOT PART OF `useDeploymentReport`. `useDeploymentReport` only fires
 * its fetch once a candidate is committed (`enabled: ... && channel != null && centerHz != null`),
 * because the report it asks for is genuinely undefined without one -- device eligibility, the
 * amplitude/power/pain triangle and the threshold placement are all properties of ONE configuration.
 * The calibrated grid is not: it is the same participant-level, pre-computed table whether or not a
 * candidate has been chosen yet, and it exists specifically so a user can browse it BEFORE choosing
 * one. Gating its fetch on a candidate already existing would make it unreachable from the one
 * screen that needs it.
 *
 * This still asks the SAME endpoint (`/api/queryClosedLoopDeployment`) that `useDeploymentReport`
 * uses, with an empty `Candidates` list -- `ClosedLoopDeployment.adapter.report_for_participant`
 * computes the grid unconditionally, before either of its own early returns, and returns it
 * alongside `{available: false, reason: "no candidate configuration was supplied..."}` for exactly
 * this request shape. It is cached under ITS OWN slot (`CL.grid`), not the report's. An earlier
 * version of this comment claimed the two could share `CL.report` because their settings differ;
 * that was wrong -- the cache keeps one answer per slot per participant and answers a different
 * settings key with the held entry marked stale, so the grid's empty-candidate reply was being
 * shown as the report for a chosen band (watched live on RCS08, 2026-09-10).
 *
 * WHICH GRID, 2026-09-11 (decision 131). The store keeps up to twelve grids per participant, one
 * per pain score and per combination of matching and split settings, and this request used to
 * carry none of them, so the server answered with the NEWEST grid whatever it was built under --
 * usually the last score the daily precompute wrote, not the one the Biomarkers page shows. The
 * request now carries the pain score and the settings the Biomarkers page has persisted for this
 * participant (`biomarkerStateStore.loadControls`: the last COMPUTED request, plus the score in
 * its dropdown), read from the same place that page reads them, so the two pages ask for the same
 * entry. When those settings differ from the ones the held answer was fetched under, the shared
 * cache marks it stale and (by its documented design) does not refetch; this hook does, once per
 * settings key, because a stale grid here is exactly the disagreement the PI reported.
 */
import { useEffect, useMemo, useRef } from "react";

import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";
import { loadControls } from "views/Reports/Biomarkers/biomarkerStateStore";

/** The request keys that decide which stored grid the Biomarkers page shows; nothing else. */
export const GRID_SETTING_KEYS = ["LabelMetric", "MatchToleranceMin", "MatchDirection",
  "AllowWindowReuse", "LabelStrategy", "PercentileLow", "PercentileHigh"];

/** The Biomarkers page's persisted score and settings for this participant, as request keys. */
export function biomarkerGridSettings(participantUid) {
  const P = (participantUid && loadControls(participantUid)) || {};
  const rp = P.requestParams || {};
  const out = {};
  GRID_SETTING_KEYS.forEach((k) => { if (rp[k] !== undefined && rp[k] !== null) out[k] = rp[k]; });
  if (P.metric) out.SweepMetric = P.metric;
  return out;
}

export default function useBandSweepGrid({ participantUid, enabled = true }) {
  const gridSettings = useMemo(() => biomarkerGridSettings(participantUid), [participantUid]);
  const settingsKey = JSON.stringify(gridSettings);
  const body = { ParticipantId: participantUid, Candidates: [], ...gridSettings };

  const cached = useCachedResult({
    moduleKey: CL.grid,
    uid: participantUid,
    settings: { Candidates: [], ...gridSettings },
    enabled: enabled !== false && !!participantUid,
    fetcher: () => SessionController.query("/api/queryClosedLoopDeployment", body)
      .then((response) => (response && response.data) || null),
  });

  // Refetch ONCE per settings key when the held grid was fetched under other settings.
  const refetchedFor = useRef(null);
  const { stale, loading, data, recompute } = cached;
  useEffect(() => {
    if (!enabled || !participantUid || !data || loading || !stale) return;
    if (refetchedFor.current === settingsKey) return;
    refetchedFor.current = settingsKey;
    recompute();
  }, [enabled, participantUid, data, loading, stale, settingsKey, recompute]);

  const raw = cached.data;
  return {
    grid: raw ? raw.band_sweep_grid : null,
    gridSettings,
    loading: cached.loading,
    err: cached.err,
    stale: cached.stale,
    recompute: cached.recompute,
  };
}
