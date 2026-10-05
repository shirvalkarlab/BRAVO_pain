/**
 * The current-map card (CurrentMapCard), rendered against the live RCS08 fixture.
 * Merged here 2026-10-05: CurrentMapCard.answerBlockOfTime.test.js, CurrentMapCard.clinicNextSession.test.js,
 * CurrentMapCard.clinicReason.test.js, CurrentMapCard.currentCaveat.test.js, CurrentMapCard.nextVisit.test.js,
 * CurrentMapCard.orientation.test.js, CurrentMapCard.pooling.test.js. Each describe block keeps its file's reason.
 *
 * Descriptions (S5 of the 2026-09-15 review, in the PI's shape of 2026-09-17): the card's prose is
 * folded behind one "Expand descriptions" push-button (as on the Biomarkers binarization card),
 * and among the folded lines is ONE succinct sentence naming which pulse-width pairings the
 * REDCap stream and the clinic-sheet stream were each fitted at -- so "no current, both streams"
 * is not read as two measurements of one configuration.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, screen, fireEvent } from "@testing-library/react";
import Plotly from "plotly.js-dist";
import { wrap, clone } from "testUtils/render";
import CurrentMapCard, { pulseWidthPairingSentence } from "./CurrentMapCard";
import response from "./__fixtures__/rcs08_stim_optimizer_two_stage.json";

// A recording stand-in (the orientation tests read what was drawn); it answers like the plain one.
jest.mock("plotly.js-dist", () => ({ ...require("testUtils/plotlyStubs").plotlyNoop(), react: jest.fn() }));
// The test setup resets every jest.fn's behaviour before each test, so the answer is set here.
beforeEach(() => Plotly.react.mockImplementation(() => Promise.resolve()));

const plan = response.two_stage;

describe("the pulse-width pairing sentence (S5)", () => {
  it("names the pairings fitted in both streams and in one only, from the fitted strata", () => {
    const s = pulseWidthPairingSentence(plan.stage1.rate_strata, plan.stage1.rate_strata_clinic);
    expect(s).toBe("Pulse-width pairings fitted: both streams 60/160 µs; home surveys only 140/180 µs; clinic sheets only 100/100 µs.");   // PIN CHANGED 2026-09-26: "REDCap" is "home surveys" in page text (SPEC.md section 6)
  });
  it("says so when the two streams share no pairing", () => {
    const s = pulseWidthPairingSentence(
      [{ pw_us_left: 60, pw_us_right: 160, fitted: true }], [{ pw_us_left: 100, pw_us_right: 100, fitted: true }]);
    expect(s).toBe("Pulse-width pairings fitted: none in both streams; home surveys only 60/160 µs; clinic sheets only 100/100 µs.");   // PIN CHANGED 2026-09-26, as above
  });
});

describe("the card's prose folds behind one push-button, except the legend", () => {
  // THE LEGEND IS OPEN ON LOAD (the PI, 2026-09-23, amending his S5 ruling of 2026-09-17 for this
  // one paragraph; panel C item 5, report C §5.3): what the colours, the cross, the dots and the
  // star mean is needed to read the squares at all. Every other description stays folded.
  it("shows the legend on load and no other description, and every description after one click", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    expect(screen.getByText(/Each square below is one stimulation rate/)).toBeInTheDocument(); // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "rate", never "speed"
    expect(screen.queryByText(/Pulse-width pairings fitted:/)).toBeNull();
    expect(screen.queryByText(/These scores come from the lab's testing workbooks/)).toBeNull();
    const btn = screen.getByRole("button", { name: /Show explanations/ });   // PIN CHANGED 2026-09-26: the control is the text link "Show explanations" (SPEC.md section 5.3)
    fireEvent.click(btn);
    expect(screen.getByText(/Each square below is one stimulation rate/)).toBeInTheDocument(); // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "rate", never "speed"
    expect(screen.getByText(/Pulse-width pairings fitted: both streams 60\/160 µs/)).toBeInTheDocument();
    expect(screen.getByText(/These scores come from the lab's testing workbooks/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hide explanations/ })).toBeInTheDocument();   // PIN CHANGED 2026-09-26, as above
  });
  it("keeps the values visible while folded: the per-rate lines and the three checks", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "stretches", never "epochs"
    expect(screen.getAllByText(/stretches · \d+ reports/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Sampled currents, predicted pain/)).toBeInTheDocument();   // PIN CHANGED 2026-09-26: the title is the section question (SPEC.md section 5.3)
  });
});

describe("absolute numbers on the squares, colour centred on today (the PI, 2026-09-17)", () => {
  const { absoluteSurface } = require("./CurrentMapCard");
  it("adds the rating at the setting in force back to every cell and centres the scale on it", () => {
    const s = { mu: [[0, -1.5], [2, 0.5]], safe: [[true, true], [true, false]], pain_reference: 5.25, pain_item: "left_leg_vas" };
    const a = absoluteSurface(s);
    expect(a.z).toEqual([[5.25, 3.75], [7.25, null]]);
    expect(a.zmid).toBe(5.25);
    expect(a.zmin).toBeLessThanOrEqual(3.75);
    expect(a.zmax).toBeGreaterThanOrEqual(7.25);
    expect(a.zmax - a.zmid).toBeCloseTo(a.zmid - a.zmin, 9);   // symmetric, so the grey midpoint IS today's value
    expect(a.title).toMatch(/predicted .*rating/);
    expect(a.title).not.toMatch(/score/);
  });
  it("an older response with no reference still draws, as the relative score it always was", () => {
    const a = absoluteSurface({ mu: [[0, -1]], safe: [[true, true]] });
    expect(a.z).toEqual([[0, -1]]);
    expect(a.zmid).toBe(0);
    expect(a.title).toBe("score (lower is better)");
  });
  // PIN CHANGED 2026-09-26: the scale is blue - light grey - orange (colour-blind safe), so the
  // midpoint that means "today" is light grey, not yellow.
  it("the intro says light grey is today's predicted rating, not that zero is the score", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    fireEvent.click(screen.getByRole("button", { name: /Show explanations/ }));   // PIN CHANGED 2026-09-26, as above
    expect(screen.getAllByText(/light grey = predicted rating at today.s setting/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/zero, on the colour scale/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------------
// The open answer carries the block-of-time qualifier (from CurrentMapCard.answerBlockOfTime). The
// current map starts closed, so its answer is what a reader sees. When a map that can recommend a
// current "moves between blocks of time" (decision 253's check, marked with a dagger since decision
// 294), the answer says so in the open rather than giving the count alone.
function planWithVerdict(verdict) {
  const p = clone(response.two_stage);
  let first = true;
  p.stage1.rate_strata = p.stage1.rate_strata.map((r) => {
    if (!r.fitted || !first) return r;
    first = false;
    return { ...r, resolved: true, amp_mA_left: 2.0, amp_mA_right: 1.5,
      calibration: { diagnosis: { verdict } } };
  });
  return p;
}
const openAnswer = (container) => Array.from(container.querySelectorAll("section#current-map p"))
  .filter((p) => p.closest("[hidden]") === null).map((p) => p.textContent).join(" ");

describe("the current map's open answer carries the block-of-time qualifier", () => {
  it("says when a map that can recommend a current moves between blocks of time", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={planWithVerdict("moves between blocks of time")} />));
    const a = openAnswer(container);
    expect(a).toMatch(/^1 of the \d pain maps drawn can recommend a current/);
    expect(a).toContain("moves between blocks of time");
    expect(a).toContain("†");
  });

  it("adds nothing when the map was checked and holds", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={planWithVerdict("calibrated")} />));
    const a = openAnswer(container);
    expect(a).toMatch(/^1 of the \d pain maps drawn can recommend a current, marked best ★\.$/);
  });
});

// ---------------------------------------------------------------------------------------------
// The clinic stream's next session and its pooled fit (from CurrentMapCard.clinicNextSession, 2026-09-23).
// (1) Ruling 5 (decision 233): the next session runs at the pairing in force and its ratings are
// merged with the earlier clinic record at that rate. What that merged stratum still needs (decision
// 239's measurement) rides the clinic block as `next_session_coverage`, printed in the open at the
// head of the clinic section. (2) The clinic stream's own fit pooled over pulse widths: the "Pool
// pulse widths" toggle swaps the clinic section too, where it is available.
function planWithClinic({ nextSession, clinicPooling }) {
  const base = response.two_stage;
  const s1 = base.stage1;
  const fitted = s1.rate_strata_clinic.find((r) => r.fitted) || s1.rate_strata_clinic[0];
  const pooledClinicRow = { ...fitted, pooled_pulse_widths: true, n_pairings_pooled: 2, n_epochs: 34,
    n_reports: 140, pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 24, n_reports: 100 },
      { pw_us_left: 100, pw_us_right: 150, n_epochs: 10, n_reports: 40 }] };
  return { ...base, stage1: { ...s1,
    clinic_stream: { ...s1.clinic_stream, next_session_coverage: nextSession },
    pulse_width_pooling: { available: true, default: "separate", note: "n",
      in_force_pairing: { pw_us_left: 60, pw_us_right: 160 },
      rate_strata_pooled: [{ ...s1.rate_strata.find((r) => r.fitted), pooled_pulse_widths: true,
        n_pairings_pooled: 3, pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 17, n_reports: 120 }] }] },
    pulse_width_pooling_clinic: clinicPooling ? { available: true, default: "separate", note: "n",
      in_force_pairing: { pw_us_left: 100, pw_us_right: 150 }, rate_strata_pooled: [pooledClinicRow] }
      : { available: false, reason: "not requested", rate_strata_pooled: [] } } };
}

const NEXT = { available: true, rate_hz: 55, n_epochs: 34,
  pairings_merged: [{ pw_us_left: 100, pw_us_right: 150, n_epochs: 10, in_force: true },
    { pw_us_left: 60, pw_us_right: 160, n_epochs: 24, in_force: false }],
  coverage: { n_pairs: 5, n_pairs_required: 6, passes: false },
  gap: { n_pairs_missing: 1, cheapest_way: "repeat L3/R3 (1 more rating) -- settings the record already has, which need topping up rather than a new pair" },
  sentence: "The PI's ruling 5: the next session runs at 55 Hz at the pairing in force (100/150 us) and its ratings are merged with the clinic record at 60/160 us. Merged, 5 of 6 current pairs qualify." };

describe("CurrentMapCard: the clinic stream's next session and its pooled fit", () => {
  it("prints ruling 5's merged answer in the open at the head of the clinic section", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithClinic({ nextSession: NEXT, clinicPooling: false })} />));
    const t = document.body.textContent;
    expect(t).toContain("Merged, 5 of 6 current pairs qualify.");
    expect(t).toContain("What the next session must deliver: repeat L3/R3 (1 more rating)");
  });

  it("the pooling toggle swaps the clinic section to its own pooled fit", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithClinic({ nextSession: NEXT, clinicPooling: true })} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    const t = document.body.textContent;
    // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "stretches", never "epochs"
    expect(t).toContain("60/160 µs (24 stretches), 100/150 µs (10 stretches)");
  });

  it("where the clinic pooled fit is not available the clinic section stays separate and says so", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithClinic({ nextSession: null, clinicPooling: false })} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    expect(document.body.textContent).toMatch(/clinic sheets: pooling across pulse widths is not available/i);
  });
});

// ---------------------------------------------------------------------------------------------
// The clinic section says why it has nothing to draw (from CurrentMapCard.clinicReason). When the
// clinic fit is unavailable the server says why under `reason` (`clinic_pain.fit_clinic_rate_strata`,
// `bravo_service._clinic_stream_stage1_block`); `note` is the success path's own remark (the
// pooled-variance note). The section prints the reason, never the success note, for an empty section.
describe("the clinic section says why it has nothing to draw", () => {
  it("prints the server's reason when the clinic fit is unavailable", () => {
    const p = clone(response.two_stage);
    p.stage1.clinic_stream = { available: false,
      reason: "fewer than two clinic settings carry Left Leg pain readings" };
    p.stage1.rate_strata_clinic = [];
    const { container } = rtlRender(wrap(<CurrentMapCard plan={p} />));
    expect(container.textContent).toContain("fewer than two clinic settings carry Left Leg pain readings");
    expect(container.textContent).not.toContain("no clinic or home-testing workbooks could be read");
  });

  it("does not offer the success note as the reason when no rate came back", () => {
    const p = clone(response.two_stage);
    p.stage1.rate_strata_clinic = [];
    const { container } = rtlRender(wrap(<CurrentMapCard plan={p} />));
    expect(container.textContent).not.toContain("pooled within-setting variance (2.6762) was estimable and used");
    expect(container.textContent).toContain("the fit returned no rate to draw");
  });
});

// ---------------------------------------------------------------------------------------------
// The card must not be readable as "higher current lowers this patient's pain" (from
// CurrentMapCard.currentCaveat). Across the whole record the two do move together: Left Leg VAS
// averages 58 at 0 mA and 46 to 53 between 3.0 and 4.8 mA. Measured on 2026-09-22, out of sample it
// does not hold -- a model given only the current in force forecasts whether a rating will be high or
// low no better than chance (area under the curve 0.41 on the left current alone, 0.49 on both,
// against a shuffled level whose 95th percentile is 0.57, over 611 ratings, with the folds separated
// in time). This card draws pain against the two currents, so the sentence belongs in the open.
describe("the current-map card says the current-and-pain association does not hold out of sample", () => {
  it("prints the caveat in the open, without pressing the descriptions button", () => {
    const { container } = rtlRender(wrap(<CurrentMapCard plan={plan} />));
    const node = Array.from(container.querySelectorAll('[data-testid="current-pain-caveat"]'))[0];
    expect(node).toBeTruthy();
    const text = node.textContent;
    expect(text).toMatch(/does not hold up out of sample/i);
    expect(text).toMatch(/0\.41/);          // the measured area under the curve
    expect(text).toMatch(/0\.57/);          // the level chance reaches
    expect(text).toMatch(/611 ratings/);
    expect(text).toMatch(/not evidence that raising the current lowers this patient/i);
  });

  it("does not hide it behind the descriptions button", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));
    // the button is there and still closed; the caveat is readable anyway
    expect(screen.getByText(/Show explanations/i)).toBeTruthy();   // PIN CHANGED 2026-09-26: the control reads "Show explanations" (SPEC.md section 5.3)
    expect(screen.getByTestId("current-pain-caveat")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------------------------
// What the next visit must deliver (from CurrentMapCard.nextVisit; decision 239, wired 2026-09-23).
// The server carries, on every row whose coverage fails, which current pairs to repeat or add and why
// (`coverage_gap`), and the card prints it under that check, cheapest way first. A row whose coverage
// passes prints nothing extra.
function planWithGap(gap, passes = false) {
  const base = response.two_stage;
  const rows = base.stage1.rate_strata.map((r) => (r.fitted && r.rate_hz === 55
    ? { ...r, coverage_passes: passes, coverage_gap: gap } : { ...r, coverage_gap: null }));
  return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
}

const GAP = {
  n_pairs_missing: 1, stepped_side: "Left", held_side_mA: 2.5,
  pairs_to_top_up: [{ amp_mA_Left: 3, amp_mA_Right: 2.5, needs_more_ratings: 1, needs_more_days: 0 }],
  pairs_to_add: [{ amp_mA_Left: 4, amp_mA_Right: 2.5 }, { amp_mA_Left: 4.5, amp_mA_Right: 2.5 }],
  cheapest_way: "repeat L3/R2.5 (1 more rating) -- settings the record already has, which need topping up rather than a new pair",
  why: "this stratum needs 1 more current pair carrying enough ratings on enough days",
  what_each_pair_needs: "at least 5 ratings at that setting, on at least 2 different days",
};

describe("CurrentMapCard: what the next visit must deliver", () => {
  it("prints the cheapest way, the reason and the new pairs under a failing coverage check", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(GAP)} />));
    const t = document.body.textContent;
    expect(t).toContain("What the next visit must deliver: repeat L3/R2.5 (1 more rating)");
    expect(t).toContain("this stratum needs 1 more current pair carrying enough ratings on enough days");
    expect(t).toContain("Each pair needs at least 5 ratings at that setting, on at least 2 different days.");
    expect(t).toContain("New settings that would also count: L4/R2.5, L4.5/R2.5.");
  });

  it("prints nothing extra where coverage passes or no gap came back", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithGap(null, true)} />));
    expect(document.body.textContent).not.toMatch(/What the next visit must deliver/);
  });
});

// ---------------------------------------------------------------------------------------------
// The predicted rating is drawn at its own (left current, right current) (from
// CurrentMapCard.orientation). The server sends `surface.mu[i][j]` for LEFT current `amps_mA[i]` and
// RIGHT current `amps_mA[j]` (`stage1_openloop._fit_rate_stratum`: a meshgrid with indexing "ij").
// Plotly draws `z[row][col]` at x = x[col], y = y[row], and the x axis is the left current, so the
// drawn z must be the server's grid transposed. From 2026-09-14 (3779bfb8) to 2026-09-26 it was passed
// unchanged, which drew every map mirrored across its diagonal. An asymmetric surface pins it.
// Left index i counts in tens and right index j in ones, so mu[i][j] names its own cell.
function asymmetricPlan() {
  const base = response.two_stage;
  const rows = base.stage1.rate_strata.map((r) => {
    if (!r.fitted || !r.surface) return r;
    const n = r.surface.amps_mA.length;
    const mu = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (__, j) => 10 * i + j));
    const safe = Array.from({ length: n }, () => Array.from({ length: n }, () => true));
    return { ...r, surface: { ...r.surface, mu, safe, pain_reference: 0 } };
  });
  return { ...base, stage1: { ...base.stage1, rate_strata: rows } };
}

// The map's section starts closed and its squares are drawn only once it has been opened (speed-up
// item C5, 2026-10-01), so each test opens it the way a reader does before reading the drawing.
const openMap = () => fireEvent.click(screen.getByRole("button", { name: /Sampled currents/ }));
// the home-survey squares only (div ids "cms-surface-..."); the clinic squares keep their data
const drawnHeatmaps = () => Plotly.react.mock.calls
  .filter((c) => /^cms-surface-/.test(c[0]))
  .map((c) => c[1] && c[1][0])
  .filter((t) => t && t.type === "heatmap");

describe("CurrentMapCard: the predicted rating is drawn at its own left and right current", () => {
  it("draws the server's mu[left][right] at x = left current, y = right current", () => {
    rtlRender(wrap(<CurrentMapCard plan={asymmetricPlan()} />));
    openMap();
    const heatmaps = drawnHeatmaps();
    expect(heatmaps.length).toBeGreaterThan(0);
    heatmaps.forEach((t) => {
      const n = t.x.length;
      // row index = y (right current), column index = x (left current)
      for (let row = 0; row < n; row += 1) {
        for (let col = 0; col < n; col += 1) {
          expect(t.z[row][col]).toBe(10 * col + row);
        }
      }
    });
  });

  it("puts one off-diagonal cell where its currents say (left 0 mA, right the top current)", () => {
    rtlRender(wrap(<CurrentMapCard plan={asymmetricPlan()} />));
    openMap();
    const t = drawnHeatmaps()[0];
    const n = t.x.length;
    // server: left index 0, right index n-1 -> 10*0 + (n-1)
    expect(t.x[0]).toBe(t.y[0]);
    expect(t.z[n - 1][0]).toBe(n - 1);          // y = right top, x = left 0
    expect(t.z[0][n - 1]).toBe(10 * (n - 1));   // y = right 0, x = left top
  });
});

// ---------------------------------------------------------------------------------------------
// Pooling across pulse widths behind a toggle (from CurrentMapCard.pooling; decision 189's option A,
// the PI, 2026-09-21): the card draws the per-pairing fit by default and, on one push-button, the fit
// pooled over every pulse-width pairing (one surface per stimulation rate, read at the pairing in
// force), with a pooling block built from the fixture's own fitted 55 Hz row.
const NOTE = "Pooling fits one surface per stimulation speed over every pulse-width pairing, with the two pulse widths as inputs, and reads it at the pairing in force: more ratings per fit, and the coverage check counts current pairs across pairings, which is why it resolves more often. It assumes the current-to-pain shape is shared across pairings. The separate fit is the default; the toggle shows the pooled one.";

function planWithPooling() {
  const base = response.two_stage;
  const fitted = base.stage1.rate_strata.find((r) => r.fitted && r.rate_hz === 55);
  const pooledRow = {
    ...fitted, pw_us_left: 60, pw_us_right: 160, pooled_pulse_widths: true, n_pairings_pooled: 3,
    n_epochs: 41, n_reports: 250,
    pairings: [{ pw_us_left: 60, pw_us_right: 160, n_epochs: 17, n_reports: 120 },
      { pw_us_left: 100, pw_us_right: 100, n_epochs: 12, n_reports: 70 },
      { pw_us_left: 140, pw_us_right: 180, n_epochs: 12, n_reports: 60 }],
    surface: { ...fitted.surface, points: fitted.surface.points.map((p) => ({ ...p, pw_us_left: 60, pw_us_right: 160 })) },
  };
  const unfitted = { pw_us_left: 60, pw_us_right: 160, rate_hz: 165, fitted: false, n_epochs: 4,
    pooled_pulse_widths: true, n_pairings_pooled: 2, pairings: [],
    reason: "4 epochs over every pulse-width pairing, below the 8-epoch floor" };
  return { ...base, stage1: { ...base.stage1, pulse_width_pooling: {
    available: true, default: "separate", note: NOTE, in_force_pairing: { pw_us_left: 60, pw_us_right: 160 },
    n_rates: 2, n_rates_fitted: 1, rate_strata_pooled: [pooledRow, unfitted] } } };
}

describe("CurrentMapCard: pooling across pulse widths behind a toggle", () => {
  it("draws the separate fit on load, with the toggle offering the pooled one", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    const t = document.body.textContent;
    expect(t).toContain("left pulse width 60 µs · right pulse width 160 µs");
    expect(t).toContain("left pulse width 140 µs · right pulse width 180 µs");
    expect(t).not.toMatch(/pooled over/i);
    expect(screen.getByRole("button", { name: /Pool pulse widths/ })).toBeInTheDocument();
  });

  it("one click shows the pooled fit: one group at the pairing in force, its pairings named, the assumption stated", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    const t = document.body.textContent;
    expect(t).toContain("pooled over 3 combinations of left and right pulse widths, read at left 60 µs / right 160 µs");
    // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): "stretches", never "epochs"
    expect(t).toContain("60/160 µs (17 stretches), 100/100 µs (12 stretches), 140/180 µs (12 stretches)");
    expect(t).toContain("41 stretches · 250 reports");   // PIN CHANGED 2026-09-26: "stretches", never "epochs"
    // PIN CHANGED 2026-09-26 (the design review, the PI's "yes to all six"): one line for the unfitted rates
    expect(t).toContain("Not drawn, too few stretches of unchanged settings (minimum 8): 165 Hz (4).");        // the unfitted pooled rate still says so
    expect(t).toMatch(/assumes the current-to-pain shape is shared across pairings/i);
    expect(t).not.toContain("left pulse width 140 µs · right pulse width 180 µs");
    expect(screen.getByRole("button", { name: /Keep pulse widths separate/ })).toBeInTheDocument();
  });

  it("a second click restores the separate fit", () => {
    rtlRender(wrap(<CurrentMapCard plan={planWithPooling()} />));
    fireEvent.click(screen.getByRole("button", { name: /Pool pulse widths/ }));
    fireEvent.click(screen.getByRole("button", { name: /Keep pulse widths separate/ }));
    expect(document.body.textContent).toContain("left pulse width 140 µs · right pulse width 180 µs");
    expect(document.body.textContent).not.toMatch(/pooled over/i);
  });

  it("offers no toggle when the response carries no pooled fit, and says why under the descriptions", () => {
    rtlRender(wrap(<CurrentMapCard plan={plan} />));   // the fixture predates the block
    expect(screen.queryByRole("button", { name: /Pool pulse widths/ })).toBeNull();
    const plan2 = { ...plan, stage1: { ...plan.stage1, pulse_width_pooling: { available: false, default: "separate",
      reason: "the pulse-width pairing in force is not known", rate_strata_pooled: [] } } };
    rtlRender(wrap(<CurrentMapCard plan={plan2} />));
    expect(screen.queryByRole("button", { name: /Pool pulse widths/ })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /Show explanations/ })[1]);   // PIN CHANGED 2026-09-26: "Show explanations" (SPEC.md section 5.3)
    expect(document.body.textContent).toContain("the pulse-width pairing in force is not known");
  });
});
