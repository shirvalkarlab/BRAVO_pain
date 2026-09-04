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
import { useEffect, useState } from "react";
import { SessionController } from "database/session-control";

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

export default function useDeploymentReport({ participantUid, bandCandidate, hemisphere,
  powerScale, enabled = true }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const channel = bandCandidate && bandCandidate.channel;
  const centerHz = bandCandidate && bandCandidate.centerHz;

  useEffect(() => {
    if (enabled === false) return undefined;
    if (!participantUid || channel == null || centerHz == null) return undefined;
    let cancelled = false;
    setLoading(true); setErr(null);
    SessionController.query("/api/queryClosedLoopDeployment",
      deploymentReportBody({ participantUid, bandCandidate, hemisphere, powerScale }))
      .then((response) => {
        if (cancelled) return;
        const d = response && response.data;
        if (d && d.available) { setData(d); setErr(null); }
        else { setData(null); setErr((d && d.reason) || "unavailable"); }
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setData(null); setErr("request failed"); setLoading(false);
      });
    return () => { cancelled = true; };
    // The dependency list holds the PRIMITIVES that identify a request, not the `bandCandidate`
    // object itself. The object is rebuilt on every render of the parent, so depending on it would
    // re-run this effect every render and issue an unbounded stream of requests to an endpoint that
    // fits regression models. Everything the request body varies on is listed here.
  }, [participantUid, channel, centerHz, hemisphere, powerScale, enabled]);  // eslint-disable-line react-hooks/exhaustive-deps

  return { data, loading, err };
}
