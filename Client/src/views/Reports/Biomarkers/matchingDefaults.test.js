/**
 * The Biomarkers page's matching defaults are the server's (decision 331; the PI, 2026-09-26: make
 * the timing measurement's findings the defaults for every slider and choice on the page).
 *
 * What is pinned:
 *   1. every value in the page's one block (`matchingDefaults.js`) equals the server's one home,
 *      `BRAVO/modules/Biomarkers/routines/sweep_settings.py`, read from its source here;
 *   2. the window is 15 minutes either side and the direction "nearest";
 *   3. the page's controls take their defaults from the block, never from a number typed in the page;
 *   4. a saved setting from before the ruling moves once: a 5 or 60 minute window becomes 15, the old
 *      default direction becomes "nearest", the old split cuts become the server's; anything else a
 *      viewer chose is kept, and once saved under today's version a later 5 stays 5.
 */
import fs from "fs";
import path from "path";

import { MATCHING_DEFAULTS, MATCHING_DEFAULTS_VERSION } from "./matchingDefaults";
import { migrateControls, saveControls, loadControls, loadMatchingRun } from "./biomarkerStateStore";

const SERVER = path.join(__dirname, "..", "..", "..", "..", "..", "BRAVO", "modules", "Biomarkers",
  "routines", "sweep_settings.py");
const src = fs.readFileSync(SERVER, "utf8");
const pyConst = (name) => {
  const m = src.match(new RegExp(`^${name}\\s*=\\s*(.+?)\\s*(#.*)?$`, "m"));
  if (!m) throw new Error(`${name} not found in sweep_settings.py`);
  const v = m[1].trim();
  if (v === "True") return true;
  if (v === "False") return false;
  if (/^"[^"]*"$/.test(v)) return v.slice(1, -1);
  return Number(v);
};

describe("1-2. the page's block equals the server's one home", () => {
  test.each([
    ["metric", "DEFAULT_BIOMARKER_METRIC"],
    ["strategy", "DEFAULT_BINARIZATION"],
    ["percentileLow", "DEFAULT_PERCENTILE_LOW"],
    ["percentileHigh", "DEFAULT_PERCENTILE_HIGH"],
    ["matchTolerance", "DEFAULT_MATCH_TOLERANCE_MIN"],
    ["matchDirection", "DEFAULT_MATCH_DIRECTION"],
    ["allowWindowReuse", "DEFAULT_ALLOW_WINDOW_REUSE"],
    ["maxPerRating", "DEFAULT_MAX_PER_RATING"],
    ["refractoryMin", "DEFAULT_REFRACTORY_MIN"],
    ["matchExtentSec", "DEFAULT_MATCH_EXTENT_SEC"],
    ["includeClinicSheetRatings", "DEFAULT_INCLUDE_CLINIC_SHEET_RATINGS"],
  ])("%s equals %s", (field, pyName) => {
    expect(MATCHING_DEFAULTS[field]).toEqual(pyConst(pyName));
  });

  test("the window is 15 minutes either side, each recording paired with its nearest report", () => {
    expect(MATCHING_DEFAULTS.matchTolerance).toBe(15);
    expect(MATCHING_DEFAULTS.matchDirection).toBe("nearest");
  });
});

describe("3. the page's controls start from the block", () => {
  const page = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
  test("no control's default is a number or choice typed in the page", () => {
    // every `useState(P.x != null ? P.x : <default>)` and `useState(P.x || <default>)` reads D.
    // (the timeline's colour mode is a view choice and the last run a record, not controls)
    const inits = (page.match(/useState\(P\.\w+ (?:!= null \? P\.\w+ : |\|\| )[^)]+\)/g) || [])
      .filter((line) => !/timelineColorMode|matchingRun/.test(line));
    expect(inits.length).toBeGreaterThanOrEqual(9);
    inits.forEach((line) => expect(line).toMatch(/: D\.\w+\)$|\|\| D\.\w+\)$/));
    expect(page).not.toMatch(/P\.matchTolerance : 60/);
    expect(page).not.toMatch(/P\.matchDirection \|\| "pro_first"/);
  });
});

describe("4. a saved setting from before the ruling moves once", () => {
  beforeEach(() => window.localStorage.clear());

  test("5 and 60 minutes become 15; another window a viewer chose is kept", () => {
    expect(migrateControls({ matchTolerance: 5 }).matchTolerance).toBe(15);
    expect(migrateControls({ matchTolerance: 60 }).matchTolerance).toBe(15);
    expect(migrateControls({ matchTolerance: 30 }).matchTolerance).toBe(30);
  });

  test("the old default direction and split cuts move; a viewer's other choices are kept", () => {
    const out = migrateControls({ matchDirection: "pro_first", percentileLow: 33.3,
      percentileHigh: 66.7, strategy: "median", maxPerRating: 1 });
    expect(out.matchDirection).toBe("nearest");
    expect(out.percentileLow).toBe(33.3333);
    expect(out.percentileHigh).toBe(66.6667);
    expect(out.strategy).toBe("median");
    expect(out.maxPerRating).toBe(1);
    expect(migrateControls({ matchDirection: "prior" }).matchDirection).toBe("prior");
    expect(out.defaults_version).toBe(MATCHING_DEFAULTS_VERSION);
  });

  test("the saved request and the saved last run move with the controls", () => {
    const out = migrateControls({ matchTolerance: 5,
      requestParams: { MatchToleranceMin: 5, MatchDirection: "pro_first", MaxPerRating: 3 },
      matchingRun: { settings: { MatchToleranceMin: 60, MatchDirection: "pro_first" }, ranAt: 1 } });
    expect(out.requestParams).toEqual({ MatchToleranceMin: 15, MatchDirection: "nearest", MaxPerRating: 3 });
    expect(out.matchingRun.settings).toEqual({ MatchToleranceMin: 15, MatchDirection: "nearest" });
  });

  test("read from the browser, a pre-ruling save arrives moved; after a save, 5 stays 5", () => {
    // what a page saved before decision 331 wrote: no version
    window.localStorage.setItem("bravo.biomarkerControls.U1",
      JSON.stringify({ schema: "biomarker_controls_v1", metric: "left_leg_vas", matchTolerance: 5,
        matchDirection: "pro_first", strategy: "median" }));
    const P = loadControls("U1");
    expect(P.matchTolerance).toBe(15);
    expect(P.matchDirection).toBe("nearest");
    expect(P.metric).toBe("left_leg_vas");
    expect(P.strategy).toBe("median");
    // the viewer then chooses 5 minutes; the page saves under today's version
    saveControls("U1", { ...P, matchTolerance: 5 });
    expect(loadControls("U1").matchTolerance).toBe(5);
  });

  test("the last run the Closed-Loop page inherits: recorded, else the last request, else the defaults", () => {
    expect(loadMatchingRun("nobody").source).toBe("defaults");
    expect(loadMatchingRun("nobody").settings.MatchToleranceMin).toBe(15);
    saveControls("U2", { metric: "vas", includeClinicSheetRatings: true,
      requestParams: { MatchToleranceMin: 20, LabelStrategy: "median" } });
    const fromRequest = loadMatchingRun("U2");
    expect(fromRequest.source).toBe("computed");
    expect(fromRequest.settings).toMatchObject({ MatchToleranceMin: 20, LabelStrategy: "median",
      LabelMetric: "vas", IncludeClinicSheetRatings: true, MatchDirection: "nearest" });
    saveControls("U2", { metric: "vas", matchingRun: { settings: { MatchToleranceMin: 30 }, ranAt: 5 } });
    expect(loadMatchingRun("U2")).toMatchObject({ source: "run", ranAt: 5,
      settings: { MatchToleranceMin: 30, MatchDirection: "nearest" } });
  });
});
