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
 * this request shape. So this is a second, independently-cached request under the same module slot
 * (the settings differ -- an empty Candidates list vs. a real one -- so `useCachedResult` gives it
 * its own cache entry, never colliding with the real single-candidate report).
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";

export default function useBandSweepGrid({ participantUid, enabled = true }) {
  const body = { ParticipantId: participantUid, Candidates: [] };

  const cached = useCachedResult({
    moduleKey: CL.report,
    uid: participantUid,
    settings: { Candidates: [] },
    enabled: enabled !== false && !!participantUid,
    fetcher: () => SessionController.query("/api/queryClosedLoopDeployment", body)
      .then((response) => (response && response.data) || null),
  });

  const raw = cached.data;
  return {
    grid: raw ? raw.band_sweep_grid : null,
    loading: cached.loading,
    err: cached.err,
    stale: cached.stale,
    recompute: cached.recompute,
  };
}
