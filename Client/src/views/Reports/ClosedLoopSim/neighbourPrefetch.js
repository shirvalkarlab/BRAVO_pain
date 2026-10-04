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

import { bandRecordFromGrid, gridCentres, refusedByRule } from "./BandSweepGridPanel";
import { inheritedMatching, matchingRequestKeys, MATCHING_KEYS } from "./inheritedMatching";
import { biomarkerGridSettings } from "./useBandSweepGrid";
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

/**
 * The bands a reader is likeliest to choose (decision 430): on each contact the device allows, the
 * `perContact` strongest by AUC (furthest from 0.5), strongest first. `[{channel, centreHz}]`.
 */
export function gridTopBands(grid, perContact = 3) {
  const sweeps = (grid && grid.band_time_sweep) || {};
  const channels = Object.keys(sweeps);
  const sideOf = (ch) => {
    const s = sweeps[ch] || {};
    return s.display_hemisphere || (/LEFT/i.test(ch) ? "Left" : (/RIGHT/i.test(ch) ? "Right" : null));
  };
  const refused = refusedByRule(channels, sweeps, grid && grid.sensing_rule, sideOf) || {};
  const out = [];
  channels.filter((ch) => !refused[ch]).forEach((ch) => {
    const rows = ((sweeps[ch] || {}).best_auc_rows || [])
      .filter((r) => r && r.auc != null && Number.isFinite(Number(r.auc)) && r.band_center_hz != null);
    rows.sort((a, b) => Math.abs(b.auc - 0.5) - Math.abs(a.auc - 0.5))
      .slice(0, perContact)
      .forEach((r) => out.push({ channel: ch, centreHz: Number(r.band_center_hz) }));
  });
  return out;
}

/**
 * FROM THE BIOMARKERS PAGE (the PI, 2026-10-04: "prefetching in biomarker to feed to CL
 * deployment"; decision 430). Fetch the Closed-Loop grid as that page will before a band is chosen,
 * then ask for the Closed-Loop report and summary of `gridTopBands`, built by the same functions a
 * tick there uses, so the server's saved answers (decision 423) match when one is chosen. At most
 * `concurrency` requests at once, so the reader's own requests are never queued behind them; each
 * request is sent once per page load. Resolves when every request has answered.
 */
export async function prefetchClosedLoopFromBiomarkers(participantUid,
  { perContact = 3, concurrency = 3 } = {}) {
  if (!participantUid) return 0;
  const gridBody = { ParticipantId: participantUid, Candidates: [], ...biomarkerGridSettings(participantUid) };
  let grid = null;
  try {
    const res = await SessionController.query("/api/queryClosedLoopDeployment", gridBody);
    grid = res && res.data && res.data.band_sweep_grid;
  } catch (e) {
    return 0;
  }
  if (!grid || grid.available === false) return 0;
  const inherited = inheritedMatching(participantUid);
  const reportMatching = matchingRequestKeys(inherited, MATCHING_KEYS);
  const includeSheets = !!reportMatching.IncludeClinicSheetRatings;
  const tasks = [];
  gridTopBands(grid, perContact).forEach(({ channel, centreHz }) => {
    const { report, summary } = neighbourRequests({ participantUid, grid, channel, centreHz,
      includeSheets, inherited, reportMatching });
    tasks.push(["/api/queryClosedLoopDeployment", report], ["/api/queryDeploymentSummary", summary]);
  });
  let next = 0; let sent = 0;
  const worker = async () => {
    while (next < tasks.length) {
      const [url, body] = tasks[next];
      next += 1;
      const p = send(url, body);
      if (p) {
        sent += 1;
        // eslint-disable-next-line no-await-in-loop
        await p;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, concurrency) }, worker));
  return sent;
}

/** For tests: forget what was sent. */
export function resetNeighbourPrefetch() { SENT.clear(); }
