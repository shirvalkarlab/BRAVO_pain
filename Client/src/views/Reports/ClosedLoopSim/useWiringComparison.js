/**
 * The three sense-to-control wirings compared by simulation (decision 472;
 * `ClosedLoopDeployment/wiring_simulation.py`), for the wiring card. Asked for only when a band is
 * chosen on each side; the request carries the page's pain score, matching settings and edited
 * program exactly as its reports do, so the four reports it needs are the page's own and are
 * served from the same saved answers. Its own cache slot (`CL.wiring`).
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";

export function wiringComparisonBody({ participantUid, left, right, painScore, matching, stimProgram }) {
  const band = (bc) => ({ channel: bc.contact, center_hz: Number(bc.center_freq_hz),
    band_width_hz: Number(bc.bandwidth_hz || 5.0) });
  return {
    ParticipantId: participantUid,
    ...(matching || {}),
    PainScore: painScore || "nrs",
    PowerScale: "power_linear",
    Bands: { Left: band(left), Right: band(right) },
    ...(stimProgram ? { StimProgram: stimProgram } : {}),
  };
}

export default function useWiringComparison({ participantUid, left, right, painScore, matching,
  stimProgram, enabled = true }) {
  const ready = !!(participantUid && left && right);
  const body = ready ? wiringComparisonBody({ participantUid, left, right, painScore, matching, stimProgram }) : {};
  const settings = { ...body };
  delete settings.ParticipantId;
  const cached = useCachedResult({
    moduleKey: CL.wiring,
    uid: participantUid,
    settings,
    enabled: enabled !== false && ready,
    fetcher: () => SessionController.query("/api/queryWiringComparison", body)
      .then((response) => (response && response.data) || null),
  });
  const raw = cached.data;
  const available = !!(raw && raw.available);
  return {
    data: available ? raw : null,
    loading: cached.loading,
    err: cached.err || (raw && !available ? (raw.reason || "unavailable") : null),
    stale: cached.stale,
  };
}
