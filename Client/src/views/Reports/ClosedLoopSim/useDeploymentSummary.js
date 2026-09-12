/**
 * Shared /api/queryDeploymentSummary fetch.
 *
 * The top-of-page verdict strip (DeploymentVerdictStrip) and the bottom Deploy-to-Percept sign-off
 * card both need the SAME authoritative summary. Factoring the request-body construction here means
 * the two can never disagree: identical participant/channel/center/cutpoint inputs → identical
 * deterministic backend payload. Each caller still issues its own request (matching the existing
 * per-panel fetch architecture), but they cannot drift in what they ask for.
 */
import { SessionController } from "database/session-control";
import { useCachedResult } from "database/useCachedResult";

import { CL } from "views/Reports/moduleCacheKeys";

// Build the EXACT body DeploySignoffCard sends, so the strip's verdict/threshold match the card's.
export function deploymentSummaryBody({ participantUid, channel, centerHz, bandWidthHz, matchDir,
  cutThr, requestParams }) {
  const body = {
    ParticipantId: participantUid, Channel: channel, CenterHz: Number(centerHz),
    BandWidthHz: Number(bandWidthHz || 5.0), MatchDirection: matchDir || "prior", ...requestParams,
  };
  if (cutThr != null) body.Cutpoint = Number(cutThr);
  return body;
}

export default function useDeploymentSummary({ participantUid, channel, centerHz, bandWidthHz,
  matchDir, cutThr, requestParams, enabled = true }) {
  const body = deploymentSummaryBody({ participantUid, channel, centerHz, bandWidthHz, matchDir,
    cutThr, requestParams });
  // The request minus the participant, for the reason given at length in useDeploymentReport: the
  // body is by definition the complete list of inputs, and the participant is already the other
  // half of the cache slot.
  const settings = { ...body };
  delete settings.ParticipantId;

  const cached = useCachedResult({
    moduleKey: CL.summary,
    uid: participantUid,
    settings,
    // `enabled` lets a consumer that receives the summary as a prop skip its own fetch entirely,
    // so the shared single-fetch path doesn't get shadowed by a duplicate request.
    enabled: enabled !== false && !!participantUid && channel != null && centerHz != null,
    fetcher: () => SessionController.query("/api/queryDeploymentSummary", body)
      .then((response) => (response && response.data) || null),
  });

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
