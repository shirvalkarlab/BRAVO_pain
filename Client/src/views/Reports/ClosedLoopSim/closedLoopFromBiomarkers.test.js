/**
 * The Biomarkers page asks the server to work out the Closed-Loop report and summary of the bands a
 * reader is likeliest to choose (the PI, 2026-10-04: "prefetching in biomarker to feed to CL
 * deployment", decision 430, plan item 3a): the three strongest by AUC on each contact the device
 * allows, built by the Closed-Loop page's own request builders so the server's saved answers match
 * when the band is chosen there. At most three requests are in flight at once, so the reader's
 * own requests are never queued behind them; each band is asked for once.
 */
import { SessionController } from "database/session-control";
import { invalidateAll } from "database/resultCache";
import FULL from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";
import { gridTopBands, prefetchClosedLoopFromBiomarkers, neighbourRequests, resetNeighbourPrefetch }
  from "./neighbourPrefetch";
import { inheritedMatching, matchingRequestKeys, MATCHING_KEYS } from "./inheritedMatching";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const GRID = FULL.band_sweep_grid;
const UID = "TOPBANDS";

beforeEach(() => {
  invalidateAll("test");
  window.localStorage.clear();
  resetNeighbourPrefetch();
  SessionController.query.mockReset();
});

test("the three strongest bands by AUC on each allowed contact", () => {
  const top = gridTopBands(GRID, 3);
  const byContact = {};
  top.forEach(({ channel, centreHz }) => { (byContact[channel] = byContact[channel] || []).push(centreHz); });
  Object.values(byContact).forEach((list) => expect(list.length).toBeLessThanOrEqual(3));
  expect(top.length).toBeGreaterThan(0);
  // each chosen band is at least as strong as any band left out on its contact
  Object.entries(byContact).forEach(([ch, chosen]) => {
    const rows = (GRID.band_time_sweep[ch].best_auc_rows || []).filter((r) => r.auc != null);
    const strength = (hz) => Math.abs(rows.find((r) => r.band_center_hz === hz).auc - 0.5);
    const weakestChosen = Math.min(...chosen.map(strength));
    rows.filter((r) => !chosen.includes(r.band_center_hz))
      .forEach((r) => expect(Math.abs(r.auc - 0.5)).toBeLessThanOrEqual(weakestChosen + 1e-12));
  });
});

test("asks for the grid, then each top band's report and summary as choosing it would, three at a time", async () => {
  let inFlight = 0; let maxInFlight = 0;
  const asked = [];
  SessionController.query.mockImplementation((url, body) => {
    asked.push({ url, body });
    if (url === "/api/queryClosedLoopDeployment" && !(body.Candidates || []).length) {
      return Promise.resolve({ data: { band_sweep_grid: GRID } });
    }
    inFlight += 1; maxInFlight = Math.max(maxInFlight, inFlight);
    return new Promise((r) => setTimeout(() => { inFlight -= 1; r({ data: { available: true } }); }, 20));
  });
  await prefetchClosedLoopFromBiomarkers(UID, { perContact: 3, concurrency: 3 });
  expect(maxInFlight).toBeLessThanOrEqual(3);
  const inh = inheritedMatching(UID);
  const reportMatching = matchingRequestKeys(inh, MATCHING_KEYS);
  const includeSheets = !!reportMatching.IncludeClinicSheetRatings;
  const top = gridTopBands(GRID, 3);
  top.forEach(({ channel, centreHz }) => {
    const want = neighbourRequests({ participantUid: UID, grid: GRID, channel, centreHz, includeSheets,
      inherited: inh, reportMatching });
    expect(asked.some((a) => a.url === "/api/queryClosedLoopDeployment"
      && JSON.stringify(a.body) === JSON.stringify(want.report))).toBe(true);
    expect(asked.some((a) => a.url === "/api/queryDeploymentSummary"
      && JSON.stringify(a.body) === JSON.stringify(want.summary))).toBe(true);
  });
  const n = asked.length;
  await prefetchClosedLoopFromBiomarkers(UID, { perContact: 3, concurrency: 3 });
  expect(asked.length).toBe(n + 1);                        // the grid again; no band asked twice
});

test("the Biomarkers heat-map grid starts it once its grid is in and current", () => {
  const fs = require("fs");
  const path = require("path");
  const src = fs.readFileSync(path.join(__dirname, "../Biomarkers/BiomarkerHeatmapGrids.js"), "utf8");
  const eff = src.slice(src.indexOf("THE CLOSED-LOOP ANSWERS FOR THE LIKELIEST BANDS"));
  expect(eff).toMatch(/if \(!participantUid \|\| loading \|\| cachedGrid\.stale \|\| !cachedGrid\.data\) return undefined;/);
  expect(eff).toMatch(/prefetchClosedLoopFromBiomarkers\(participantUid\)/);
});
