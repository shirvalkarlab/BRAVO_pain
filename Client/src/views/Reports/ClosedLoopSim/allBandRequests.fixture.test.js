/**
 * EVERY BAND'S REQUESTS, AS THE PAGE BUILDS THEM (the PI, 2026-10-06: register all 132 bands with the
 * 10-minute refresh job; decision 463).
 *
 * The server works out every band's saved answers ahead (`ClosedLoopDeployment/all_band_requests.py`),
 * and a saved answer is found only when the request matches what the page sends. This test builds
 * every band's report, summary, ROC, month-by-month and band-power requests with the page's OWN
 * functions on a fixed grid and fixed inherited settings, and compares them with the shared fixture
 * the Python copy is tested against (`BRAVO/modules/ClosedLoopDeployment/tests/test_all_band_requests.py`).
 * A change to either side fails one of the two tests. To rewrite the fixture after a deliberate change
 * to the page's request builders: UPDATE_ALL_BAND_FIXTURE=1, then rerun both tests.
 */
import fs from "fs";
import path from "path";
import { biomarkerGridSettings } from "./useBandSweepGrid";
import { gridCentres, refusedByRule, bandRecordFromGrid } from "./BandSweepGridPanel";
import { neighbourRequests } from "./neighbourPrefetch";
import { inheritedMatching, matchingRequestKeys, MATCHING_KEYS } from "./inheritedMatching";
import { bandPainScore, eraSettings, lsbSettings, rocSettings, summaryRequestParams } from "./candidateRequestParams";

const FIXTURE = path.join(__dirname, "../../../../../BRAVO/modules/ClosedLoopDeployment/tests/fixtures/all_band_requests.json");
const SETTINGS = { LabelMetric: "left_leg_vas", MatchToleranceMin: 10, MatchDirection: "pro_first",
  AllowWindowReuse: false, LabelStrategy: "percentile", PercentileLow: 35, PercentileHigh: 36,
  IncludeClinicSheetRatings: false, MaxPerRating: 4 };

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));
jest.mock("views/Reports/Biomarkers/biomarkerStateStore", () => {
  const real = jest.requireActual("views/Reports/Biomarkers/biomarkerStateStore");
  return { ...real, loadMatchingRun: () => ({ settings: { ...real.defaultMatchingSettings(),
    LabelMetric: "left_leg_vas", MatchToleranceMin: 10, MatchDirection: "pro_first", AllowWindowReuse: false,
    LabelStrategy: "percentile", PercentileLow: 35, PercentileHigh: 36, IncludeClinicSheetRatings: false,
    MaxPerRating: 4 }, ranAt: null, source: "run" }) };
});

const UID = "u-fixture";
const row = (c, extra = {}) => ({ band_center_hz: c, ...extra });
const GRID = {
  available: true,
  grid_settings: { sweep_metric: "left_leg_vas", label_strategy: "percentile", percentile_low: 35,
    percentile_high: 36, match_tolerance_min: 10, match_direction: "pro_first", allow_window_reuse: false,
    include_clinic_sheet_ratings: false, metric_label: "Left Leg VAS", stored_utc: "2026-10-06T00:00:00Z" },
  sensing_rule: { by_side: { Right: { rule_applied: true, allowed_channel: "ZERO_THREE_RIGHT", why: "x" },
    Left: { rule_applied: false } } },
  band_time_sweep: {
    ONE_THREE_LEFT: { display_hemisphere: "Left", display_short: "L 1-3", band_width_hz: 5,
      best_correlation_rows: [row(10.5), row(24.5)], best_auc_rows: [row(24.5, { auc: 0.6 }), row(9.5, { auc: 0.4 })] },
    ZERO_THREE_RIGHT: { display_hemisphere: "Right", band_width_hz: 5.0, best_correlation_rows: [row(26.5)], best_auc_rows: [] },
    ONE_THREE_RIGHT: { display_hemisphere: "Right", best_correlation_rows: [row(12.5)], best_auc_rows: [] },
  },
};

export function pageRequests(grid) {
  const sweeps = grid.band_time_sweep || {};
  const channels = Object.keys(sweeps);
  const sideOf = (ch) => (sweeps[ch] || {}).display_hemisphere || (/LEFT/i.test(ch) ? "Left" : (/RIGHT/i.test(ch) ? "Right" : null));
  const refused = refusedByRule(channels, sweeps, grid.sensing_rule, sideOf) || {};
  const inherited = inheritedMatching(UID);
  const reportMatching = matchingRequestKeys(inherited, MATCHING_KEYS);
  const includeSheets = !!reportMatching.IncludeClinicSheetRatings;
  const bands = [];
  channels.filter((ch) => !refused[ch]).forEach((ch) => {
    gridCentres(grid, ch).forEach((c) => {
      const { report, summary } = neighbourRequests({ participantUid: UID, grid, channel: ch, centreHz: c,
        includeSheets, inherited, reportMatching });
      const bc = bandRecordFromGrid(grid, ch, c);
      const rp = summaryRequestParams(bc, includeSheets, bandPainScore(bc).key, inherited);
      bands.push({ channel: ch, centre: c, report, summary,
        roc: { ParticipantId: UID, ...rocSettings(bc, "prior", rp) },
        era: { ParticipantId: UID, ...eraSettings(bc, rp) },
        lsb_at_cut_1234_5: { ParticipantId: UID, ...lsbSettings(bc, { threshold: 1234.5, matchDir: "prior" }, rp) } });
    });
  });
  return { grid_body: { ParticipantId: UID, Candidates: [], ...biomarkerGridSettings(UID) }, bands };
}

test("the page's own requests for every band equal the shared fixture the server's copy is tested on", () => {
  const got = JSON.parse(JSON.stringify({ uid: UID, settings: SETTINGS, grid: GRID, ...pageRequests(GRID) }));
  if (process.env.UPDATE_ALL_BAND_FIXTURE === "1") fs.writeFileSync(FIXTURE, `${JSON.stringify(got, null, 1)}\n`);
  expect(got).toEqual(JSON.parse(fs.readFileSync(FIXTURE, "utf8")));
  expect(got.bands.map((b) => `${b.channel} ${b.centre}`)).toEqual(
    ["ONE_THREE_LEFT 9.5", "ONE_THREE_LEFT 10.5", "ONE_THREE_LEFT 24.5", "ZERO_THREE_RIGHT 26.5"]);
});
