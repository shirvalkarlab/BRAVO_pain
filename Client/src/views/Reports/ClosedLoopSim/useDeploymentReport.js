/** Canonical research-only report; the upstream deployment request schema is not used. */
import { useEffect } from "react";
import { useAnalysisQuery } from "../Biomarkers/queryAnalysis";
import { useCachedResult } from "database/useCachedResult";
import { settingsKey } from "database/resultCache";
import { CL } from "views/Reports/moduleCacheKeys";

export function deploymentReportBody({ participantUid, bandCandidate, requestParams }) {
  const bc = bandCandidate || {};
  return { ...requestParams, ParticipantId: participantUid, Channel: bc.contact,
    CenterHz: Number(bc.center_freq_hz), BandWidthHz: Number(bc.bandwidth_hz || 5) };
}

export default function useDeploymentReport({ participantUid, bandCandidate, requestParams,
  inputIdentity, enabled = true }) {
  const queryAnalysis = useAnalysisQuery();
  const body = deploymentReportBody({ participantUid, bandCandidate, requestParams });
  const requestKey = settingsKey(body);
  useEffect(() => () => queryAnalysis.cancel("/api/queryClosedLoopResearch"), [requestKey, queryAnalysis]);
  const cached = useCachedResult({
    moduleKey: CL.report, uid: participantUid, settings: body,
    // A different band/control set must not display the previous band's research result.
    identity: { input: inputIdentity, request: body },
    enabled: enabled && !!participantUid && !!body.Channel && !!bandCandidate && bandCandidate.center_freq_hz != null,
    autoFetch: false,
    fetcher: () => queryAnalysis("/api/queryClosedLoopResearch", body).then(({ data }) => data),
  });
  const raw = cached.data;
  return { ...cached, raw, data: raw && raw.available ? raw : null };
}
