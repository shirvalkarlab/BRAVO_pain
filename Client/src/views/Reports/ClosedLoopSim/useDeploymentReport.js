/**
 * Shared /api/queryClosedLoopDeployment fetch.
 *
 * This is a DIFFERENT question from useDeploymentSummary, and the two are deliberately kept apart.
 * The summary answers "given this band, where does the threshold go and do the statistical gates
 * pass". This report answers "may this configuration be programmed onto the device at all" — it
 * evaluates the 51 encoded Percept rules, estimates the three edges of the amplitude/power/pain
 * triangle at their correct clustering units, and tests whether the three signs are mutually
 * coherent. A band can pass every gate in the summary and still be undeployable, most obviously
 * when its power RISES with amplitude, which closes a positive-feedback loop on the device.
 *
 * The backend never throws for an unevaluable participant; it returns {available: false, reason}.
 * Treat a missing report as "not yet answerable" rather than as an error, because the commonest
 * cause is simply that no candidate configuration has been chosen yet.
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";

export function deploymentReportBody({ participantUid, bandCandidate, hemisphere, powerScale }) {
  const bc = bandCandidate || {};
  return {
    ParticipantId: participantUid,
    Hemisphere: hemisphere || "Left",
    // The device thresholds a LINEAR sum of squared magnitude (rule D11), so the linear scale is
    // the one that describes what the device will actually do. The log scale remains a valid
    // statistical description and is not what should drive a threshold.
    PowerScale: powerScale || "power_linear",
    Candidates: bc.channel == null ? [] : [{
      channel: bc.channel,
      center_hz: Number(bc.centerHz),
      band_width_hz: Number(bc.bandWidthHz || 5.0),
      sensing_hemisphere: bc.sensingHemisphere || null,
      actuated_hemisphere: hemisphere || "Left",
      rate_hz: bc.rateHz == null ? null : Number(bc.rateHz),
      pulse_width_us: bc.pulseWidthUs == null ? null : Number(bc.pulseWidthUs),
      threshold_mode: bc.thresholdMode || "dual",
    }],
  };
}

/**
 * The request, minus the participant, is the cache key.
 *
 * This is the rule every fetch in the deployment family follows, and it is worth stating once. The
 * body of the request IS the complete list of things that change the answer — that is what a
 * request body is — so deriving the settings key from it means the key cannot fall behind the
 * request. The participant is removed because the cache already stores one entry per participant
 * per module, so including it would put the same value in the key twice.
 *
 * It also fixes a real gap in what used to be watched. The effect this replaces listed only the
 * primitives it could safely depend on without re-firing every render, which meant the rate, the
 * pulse width and the candidate's own threshold mode were sent to the server but were NOT part of
 * what identified the request. A candidate committed at a different rate would have been answered
 * from a response fitted at the old one. The serialised key has no such problem: it is a string, so
 * a body rebuilt on every render still compares equal as long as its contents are equal, and every
 * field participates.
 */
function reportSettings(body) {
  const rest = { ...body };
  delete rest.ParticipantId;
  return rest;
}

export default function useDeploymentReport({ participantUid, bandCandidate, hemisphere,
  powerScale, enabled = true }) {
  const channel = bandCandidate && bandCandidate.channel;
  const centerHz = bandCandidate && bandCandidate.centerHz;
  const body = deploymentReportBody({ participantUid, bandCandidate, hemisphere, powerScale });

  const cached = useCachedResult({
    moduleKey: CL.report,
    uid: participantUid,
    settings: reportSettings(body),
    enabled: enabled !== false && !!participantUid && channel != null && centerHz != null,
    // The whole response is cached, INCLUDING an {available:false, reason} answer. That answer is
    // as durable as a successful one — it will not change until an input changes — and it is the
    // expensive one to rediscover, because the endpoint has to read the participant's recordings
    // before it can conclude that the configuration cannot be evaluated. Storing only successes
    // would leave the slowest case uncached.
    fetcher: () => SessionController.query("/api/queryClosedLoopDeployment", body)
      .then((response) => (response && response.data) || null),
  });

  // The external shape of this hook is unchanged, so every consumer keeps working: `data` is the
  // report only when the server said it was available, and `err` carries the server's own reason
  // otherwise. The cache fields are ADDED alongside, for the page's Recompute control.
  const raw = cached.data;
  const available = !!(raw && raw.available);
  return {
    data: available ? raw : null,
    loading: cached.loading,
    err: cached.err || (raw && !available ? (raw.reason || "unavailable") : null),
    stale: cached.stale,
    staleReasons: cached.staleReasons,
    computedAt: cached.computedAt,
    notKept: cached.notKept,
    recompute: cached.recompute,
    hasCached: cached.hasCached,
  };
}
