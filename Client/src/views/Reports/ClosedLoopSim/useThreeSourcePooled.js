/**
 * The pooled three-source view: every run of rising current on one side, grouped by the sensing
 * contact on that side, with the stored pooled slope per band centre (redesign decisions 5, 9, 10).
 *
 * FETCHED AFTER THE REPORT, NOT WITH IT. The PI's instruction, 2026-09-11: "prefetch the data after
 * the first figures load." The report request fits mixed-effects models and is what the page's
 * first figures wait on; this request reads two stored tables and groups them, and it is only
 * useful once a band is committed and the report has answered. So it is enabled by the report's
 * `data` arriving, asks the same endpoint with `ThreeSourcePooled: 1` (which the service answers
 * from the stored tables without building anything), and is cached under its own slot `CL.pooled`.
 *
 * WHY THE STORED TABLES ARE THE RIGHT SOURCE. The page's own report is truncated to the newest
 * four runs once the write-back entries exist; the stored tables were written from EVERY run
 * (decision 103's rule), so this view reads the same on a cold request and a warm one.
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";

export default function useThreeSourcePooled({ participantUid, afterReport, enabled = true }) {
  const body = { ParticipantId: participantUid, ThreeSourcePooled: 1 };
  const cached = useCachedResult({
    moduleKey: CL.pooled,
    uid: participantUid,
    settings: { ThreeSourcePooled: 1 },
    // `afterReport` is the report hook's `data`; null until the first figures have their answer.
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
