/**
 * Shared /api/queryDeploymentSummary fetch.
 *
 * The top-of-page verdict strip (DeploymentVerdictStrip) and the bottom Deploy-to-Percept sign-off
 * card both need the SAME authoritative summary. Factoring the request-body construction here means
 * the two can never disagree: identical participant/channel/center/cutpoint inputs → identical
 * deterministic backend payload. Each caller still issues its own request (matching the existing
 * per-panel fetch architecture), but they cannot drift in what they ask for.
 */
import { useEffect, useState } from "react";
import { SessionController } from "database/session-control";

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
  matchDir, cutThr, requestParams }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!participantUid || channel == null || centerHz == null) return undefined;
    let cancelled = false;
    setLoading(true); setErr(null);
    const body = deploymentSummaryBody({ participantUid, channel, centerHz, bandWidthHz, matchDir,
      cutThr, requestParams });
    SessionController.query("/api/queryDeploymentSummary", body).then((response) => {
      if (cancelled) return;
      const d = response && response.data;
      if (d && d.available) setData(d);
      else { setData(null); setErr((d && d.reason) || "unavailable"); }
      setLoading(false);
    }).catch(() => {
      if (cancelled) return;
      setData(null); setErr("request failed"); setLoading(false);
    });
    return () => { cancelled = true; };
  }, [participantUid, channel, centerHz, bandWidthHz, matchDir, cutThr, requestParams]);

  return { data, loading, err };
}
