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
import { bandPainScore, reportCandidateFromBand, summaryRequestParams } from "./candidateRequestParams";
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

/** Send the neighbours' requests not yet sent; the answers are saved by the server. */
export function prefetchNeighbours(opts) {
  const { grid, channel, centreHz } = opts;
  if (!grid || !channel || centreHz == null) return 0;
  let n = 0;
  neighbourCentres(grid, channel, centreHz).forEach((c) => {
    const { report, summary } = neighbourRequests({ ...opts, centreHz: c });
    [["/api/queryClosedLoopDeployment", report], ["/api/queryDeploymentSummary", summary]]
      .forEach(([url, body]) => {
        const key = `${url}|${JSON.stringify(body)}`;
        if (SENT.has(key)) return;
        SENT.add(key);
        n += 1;
        Promise.resolve()
          .then(() => SessionController.query(url, body))
          .catch(() => SENT.delete(key));          // a failed ask may be tried again later
      });
  });
  return n;
}

/** For tests: forget what was sent. */
export function resetNeighbourPrefetch() { SENT.clear(); }
