/**
 * The stored closed-loop simulation (Phase 8 of the 2026-09-11 redesign): M0 (the replay), M1 or
 * M2 (the loop closed through the fitted response curve) and M3 (run-resampled intervals).
 *
 * FETCHED AFTER THE REPORT, like the pooled three-source view: the report is what WRITES the
 * simulation (it needs the thresholds the report places), so this asks for it only once the
 * report's data has arrived, with `ClosedLoopSimulation: 1`, which the service answers from the
 * stored entry without building anything. Cached under its own slot `CL.simulation`.
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";
import { deploymentReportBody } from "./useDeploymentReport";

export default function useClosedLoopSimulation({ participantUid, bandCandidate, afterReport,
  reportStamp, hemisphere, powerScale, enabled = true }) {
  // The same candidate the report was asked for: the service reads the stored simulation back BY
  // candidate, because the store keeps one per band and the newest is not necessarily this one.
  const body = { ...deploymentReportBody({ participantUid, bandCandidate, hemisphere, powerScale }),
    ClosedLoopSimulation: 1 };
  const bc = bandCandidate || {};
  const cached = useCachedResult({
    moduleKey: CL.simulation,
    uid: participantUid,
    // `reportStamp` is when the report's answer was computed: a fresh report writes a fresh
    // simulation, and without it in the key this fetch would keep the answer read before the
    // report finished (watched live: "no simulation is stored yet" beside a report that had
    // just stored one).
    settings: { ClosedLoopSimulation: 1, channel: bc.channel || null, centerHz: bc.centerHz == null ? null : Number(bc.centerHz),
      hemisphere: hemisphere || "Left", reportStamp: reportStamp || null },
    enabled: enabled !== false && !!participantUid && !!afterReport,
    fetcher: () => SessionController.query("/api/queryClosedLoopDeployment", body)
      .then((response) => (response && response.data) || null),
  });
  const raw = cached.data;
  return {
    data: raw && raw.available ? raw : null,
    loading: cached.loading,
    err: cached.err || (raw && !raw.available ? (raw.reason || "unavailable") : null),
    stale: cached.stale,
    recompute: cached.recompute,
  };
}
