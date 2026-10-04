/**
 * THE BANDS EITHER SIDE, WORKED OUT AHEAD (the PI, 2026-10-04: "when a band is selected ... have 2
 * bands on either side automatically computed in parallel because a user is most likely to click
 * one of those bands when exploring"; decision 425).
 *
 * Once the chosen band's report and summary are in, the page sends the report and summary requests
 * for the two grid rows either side on the same contact. Each lands on another server worker, so
 * they run side by side on separate cores, and the server saves each answer (decision 423). The
 * requests are built by the same functions a tick uses (`bandRecordFromGrid`,
 * `reportCandidateFromBand`, `deploymentReportBody`, `summaryRequestParams`,
 * `deploymentSummaryBody`), so ticking a neighbour sends exactly what was sent ahead and is served
 * the saved answer. The answers are not kept here: the server keeps them. Each request is sent once
 * per page load.
 */
import { SessionController } from "database/session-control";

import { bandRecordFromGrid, gridCentres } from "./BandSweepGridPanel";
import { bandPainScore, eraSettings, lsbSettings, reportCandidateFromBand, rocSettings,
  summaryRequestParams } from "./candidateRequestParams";
import { deploymentReportBody } from "./useDeploymentReport";
import { deploymentSummaryBody } from "./useDeploymentSummary";

/** How many grid rows either side are worked out ahead. */
export const NEIGHBOURS_EACH_SIDE = 2;

const SENT = new Set();

/** The grid centres within `k` rows of `centreHz` on `channel`, the chosen one left out. */
export function neighbourCentres(grid, channel, centreHz, k = NEIGHBOURS_EACH_SIDE) {
  const all = gridCentres(grid, channel);
  const i = all.findIndex((c) => Math.abs(c - Number(centreHz)) < 1e-6);
  if (i < 0) return [];
  return all.slice(Math.max(0, i - k), i + k + 1).filter((c, j) => j !== Math.min(i, k));
}

/** The report and summary request bodies ticking the band at `centreHz` would send. */
export function neighbourRequests({ participantUid, grid, channel, centreHz, includeSheets,
  inherited, reportMatching }) {
  const nbc = bandRecordFromGrid(grid, channel, centreHz);
  const pain = bandPainScore(nbc).key;
  return {
    report: deploymentReportBody({ participantUid, bandCandidate: reportCandidateFromBand(nbc),
      painScore: pain, matching: reportMatching }),
    summary: deploymentSummaryBody({ participantUid, channel: nbc.contact,
      centerHz: nbc.center_freq_hz, bandWidthHz: nbc.bandwidth_hz || 5.0, matchDir: "prior",
      cutThr: null, requestParams: summaryRequestParams(nbc, includeSheets, pain, inherited) }),
  };
}

function send(url, body) {
  const key = `${url}|${JSON.stringify(body)}`;
  if (SENT.has(key)) return null;
  SENT.add(key);
  return Promise.resolve()
    .then(() => SessionController.query(url, body))
    .catch(() => { SENT.delete(key); return null; });   // a failed ask may be tried again later
}

/**
 * The Background panels for one band (decision 428): the ROC and the month-by-month check at once,
 * then the band-power panel with the ROC's own default operating point (Youden, "next report"),
 * the point the ROC panel starts on and hands that panel. `bc` and `requestParams` are the band's
 * own, as the page will hold them when the band is chosen.
 */
function prefetchPanels(participantUid, bc, requestParams) {
  const roc = send("/api/queryDeploymentROC",
    { ParticipantId: participantUid, ...rocSettings(bc, "prior", requestParams) });
  send("/api/queryDeploymentRocByEra", { ParticipantId: participantUid, ...eraSettings(bc, requestParams) });
  if (!roc) return;
  roc.then((res) => {
    const env = res && res.data;
    const yd = env && env.available && env.roc && env.roc.available && env.roc.operating_points
      && env.roc.operating_points.youden;
    if (!yd || !Number.isFinite(yd.threshold)) return;
    send("/api/queryLsbPower", { ParticipantId: participantUid,
      ...lsbSettings(bc, { threshold: yd.threshold, matchDir: "prior" }, requestParams) });
  });
}

/** Send the requests not yet sent: the neighbours' report and summary, and the Background panels
 *  of the chosen band (`bc`, `requestParams`, the page's own) and of each neighbour. */
export function prefetchNeighbours(opts) {
  const { grid, channel, centreHz, participantUid, bc, requestParams } = opts;
  if (!grid || !channel || centreHz == null) return 0;
  const before = SENT.size;
  if (bc && requestParams) prefetchPanels(participantUid, bc, requestParams);
  neighbourCentres(grid, channel, centreHz).forEach((c) => {
    const { report, summary } = neighbourRequests({ ...opts, centreHz: c });
    send("/api/queryClosedLoopDeployment", report);
    send("/api/queryDeploymentSummary", summary);
    const nbc = bandRecordFromGrid(grid, channel, c);
    prefetchPanels(participantUid, nbc,
      summaryRequestParams(nbc, opts.includeSheets, bandPainScore(nbc).key, opts.inherited));
  });
  return SENT.size - before;
}

/** For tests: forget what was sent. */
export function resetNeighbourPrefetch() { SENT.clear(); }
