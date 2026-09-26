/**
 * Nothing on the Closed-Loop page is computed on NRS alone (the PI, 2026-09-25 night). A dropdown
 * beside the band selection offers the Biomarkers heat maps' own pain scores, defaults to the score
 * of the grid the chosen band came from (NRS, said as such, when the band carries none), and the
 * chosen score goes to the deployment report (`PainScore`) and to the deployment summary
 * (`LabelMetric`), so every band-to-pain reading on the page follows it. The sign-off sheet prints
 * which score was used.
 */
import fs from "fs";
import path from "path";

jest.mock("plotly.js-dist", () => ({ toImage: jest.fn(), newPlot: jest.fn(), purge: jest.fn() }));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

/* eslint-disable import/first */
import { PAIN_SCORE_OPTIONS, painScoreLabel } from "views/Reports/painScores";
import { bandPainScore, summaryRequestParams } from "./candidateRequestParams";
import { deploymentReportBody } from "./useDeploymentReport";
import { painScoreUsedText } from "./DeploySignoffCard";
/* eslint-enable import/first */

const REPO = path.resolve(__dirname, "../../../../..");
const GRID = { sweep_metric: "left_leg_vas", label_strategy: "tertile", match_tolerance_min: 60 };

test("the page's list of pain scores is the server's list, key for key and label for label", () => {
  const src = fs.readFileSync(path.join(REPO, "BRAVO/modules/Biomarkers/routines/sweep_settings.py"), "utf8");
  const block = src.slice(src.indexOf("BIOMARKER_METRICS = ["), src.indexOf("]", src.indexOf("BIOMARKER_METRICS = [")));
  const server = [...block.matchAll(/\{"key": "([^"]+)", "label": "([^"]+)"\}/g)]
    .map((m) => ({ key: m[1], label: m[2] }));
  expect(server.length).toBe(6);
  expect(PAIN_SCORE_OPTIONS).toEqual(server);
  expect(painScoreLabel("left_leg_vas")).toBe("Left Leg VAS");
});

test("the default is the pain score of the grid the band came from, or NRS said as such", () => {
  expect(bandPainScore({ label: {}, grid_settings: GRID })).toEqual({ key: "left_leg_vas", fromBand: true });
  expect(bandPainScore({ label: { pro_metric: "back_vas" }, grid_settings: GRID }))
    .toEqual({ key: "back_vas", fromBand: true });
  expect(bandPainScore({ label: {} })).toEqual({ key: "nrs", fromBand: false });
  expect(bandPainScore(null)).toEqual({ key: "nrs", fromBand: false });
  expect(bandPainScore({ label: { pro_metric: "worst_pain" } })).toEqual({ key: "nrs", fromBand: false });
});

test("the chosen score overrides the band's own in the deployment summary's request", () => {
  const bc = { label: {}, grid_settings: GRID };
  expect(summaryRequestParams(bc, false, "back_vas").LabelMetric).toBe("back_vas");
  expect(summaryRequestParams(bc, true, "nrs")).toEqual({ LabelMetric: "nrs", LabelStrategy: "tertile",
    MatchToleranceMin: 60, IncludeClinicSheetRatings: "1" });
  expect(summaryRequestParams(bc, false).LabelMetric).toBe("left_leg_vas");
});

test("the deployment report's request carries the chosen score, so the cached answer is keyed on it", () => {
  const cand = { channel: "ONE_THREE_LEFT", centerHz: 24.5, sensingHemisphere: "Left" };
  expect(deploymentReportBody({ participantUid: "u", bandCandidate: cand, painScore: "left_leg_vas" }).PainScore)
    .toBe("left_leg_vas");
  expect(deploymentReportBody({ participantUid: "u", bandCandidate: cand }).PainScore).toBe("nrs");
});

test("the page offers the shared list and sends the chosen score to both requests", () => {
  const src = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
  expect(src).toMatch(/from "views\/Reports\/painScores"/);
  expect(src).toMatch(/summaryRequestParams\(bc, includeSheets, painScore\)/);
  expect(src).toMatch(/useDeploymentReport\(\{[^}]*painScore/);
  expect(src).toMatch(/<PainScoreSelect/);
});

test("the sign-off sheet says which pain score every band-to-pain reading used", () => {
  expect(painScoreUsedText({ key: "left_leg_vas", label: "Left Leg VAS", fell_back_to_nrs: false }, "left_leg_vas"))
    .toBe("Left Leg VAS, for every band-to-pain reading on this page");
  expect(painScoreUsedText({ key: "nrs", label: "NRS (0–10)", fell_back_to_nrs: true,
    reason: "no pain score was sent with the request, so NRS was used" }, "nrs"))
    .toBe("NRS (0–10), for every band-to-pain reading on this page (no pain score was sent with the request, so NRS was used)");
  expect(painScoreUsedText({ key: "left_leg_vas", label: "Left Leg VAS" }, "nrs"))
    .toBe("NOT THE SAME: the evidence and stability readings used Left Leg VAS, the deployment summary NRS (0–10)");
  expect(painScoreUsedText(null, "nrs")).toBe("not recorded on the deployment report");
});

test("the triangle and the stability card say which pain score they read", () => {
  const tri = fs.readFileSync(path.join(__dirname, "EvidenceTrianglePanel.js"), "utf8");
  const stab = fs.readFileSync(path.join(__dirname, "BandStabilityPanel.js"), "utf8");
  const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
  expect(tri).toMatch(/data\.pain_score\.label/);
  // Reworded on purpose by decision 302 ("Pain score: NRS (0-10)."), and the page now hands the
  // stability card the report checked against the chosen band (`report`), not the raw hook's.
  expect(stab).toMatch(/Pain score: \$\{painScore\.label/);
  expect(page).toMatch(/painScore=\{report\?\.data\?\.pain_score\}/);
});
