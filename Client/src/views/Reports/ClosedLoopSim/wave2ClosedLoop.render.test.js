/**
 * Wave 2 on the Closed-Loop page, rendered from RCS08's live responses of 2026-10-22, captured in
 * the server container through the functions the API calls:
 *   - the "Band selection" grid (`run_for_participant` with the page's grid request, its
 *     `band_sweep_grid`; NRS at the page's remembered settings: 5-min window, report picks nearest,
 *     split 36/37 %);
 *   - the sign-off summaries (`deployment_summary`) for the two ticked bands, R 0-3 9.5 Hz and
 *     L 0-3 15.5 Hz (Left Leg VAS, the bands' own score);
 *   - the Closed-Loop reports for R 0-3 9.5 Hz (the ticked right band) and L 0-3 26.5 Hz (the band
 *     D53 warns on).
 *
 * Pinned, with the live values: the four new columns (Source, Current out, Later 30%, q) and their
 * key; the sign-off's "Decides" line and its new rows; the deciding p in the band identity; the
 * home-swing warning beside the thresholds and in their reasons; D53 filed as recommended, never a
 * refusal; the band's peak above the smooth background. Queried directly in the DOM.
 */
import "@testing-library/jest-dom";
import { render as rtlRender, fireEvent } from "@testing-library/react";
import { wrap, clone } from "testUtils/render";

import BandSweepGridPanel from "./BandSweepGridPanel";
import SignoffRecord from "./DeploySignoffCard";
import BandCandidateIdentity from "./BandCandidateIdentity";
import ParameterTable, { ParameterDetails } from "./PrescriptionPanel";
import DeviceRuleLedger from "./DeviceRuleLedger";
import CLGRID from "./__fixtures__/rcs08_wave2_clgrid_nrs_2026-10-22.json";
import SUM_R from "./__fixtures__/rcs08_wave2_summary_R03_9p5_2026-10-22.json";
import SUM_L from "./__fixtures__/rcs08_wave2_summary_L03_15p5_2026-10-22.json";
import REP_R from "./__fixtures__/rcs08_wave2_cl_R03_9p5_2026-10-22.json";
import REP_L26 from "./__fixtures__/rcs08_wave2_cl_L03_26p5_2026-10-22.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const q = (sel) => document.querySelector(sel);
const text = (sel) => { const el = q(sel); return el ? el.textContent : null; };
const ok = (data) => ({ data, loading: false, err: null });
const kvValue = (label) => {
  // a KV row: the label and the value are the row's two captions
  const rows = Array.from(document.querySelectorAll(".cl-signoff-record span, .cl-signoff-record div"));
  const lab = rows.find((el) => el.children.length === 0 && el.textContent === label);
  if (!lab) return null;
  const sib = lab.nextElementSibling;
  return sib ? sib.textContent : null;
};
const tab = (side, label) => Array.from(document.querySelectorAll(`[data-testid="band-side-${side}"] button`))
  .find((b) => b.textContent.replace("✕", "") === label);

describe("Band selection: Source, Current out, Later 30% and q on each band", () => {
  const mount = () => rtlRender(wrap(<BandSweepGridPanel grid={CLGRID} participantUid="uid"
    committed={{ contact: "ZERO_THREE_RIGHT", centerHz: 9.5 }}
    committedBySide={{ Left: { contact: "ZERO_THREE_LEFT", centerHz: 15.5 },
      Right: { contact: "ZERO_THREE_RIGHT", centerHz: 9.5 } }}
    onCandidateChosen={() => {}} />));

  it("R 0-3 9.5 Hz: the home record decides, current out warns, the later 30% agrees, q 0.96", () => {
    mount();
    const id = "cl-band-ZERO_THREE_RIGHT-9.5";
    expect(text(`[data-testid="${id}-source"]`)).toBe("Home");
    expect(q(`[data-testid="${id}-source"]`).getAttribute("title")).toBe(
      "Decided by: home record (chronic log). r +0.08 [−0.30, +0.30], n=30; TD alone: r −0.38 "
      + "[−0.63, −0.13], n=49. Daily swing: ▲ 2.6-fold (low 17:00, high 00:00)");
    expect(text(`[data-testid="${id}-current"]`)).toBe("▲");
    expect(q(`[data-testid="${id}-current"]`).getAttribute("title"))
      .toBe("warning: with the current taken out, its interval reaches the other side of zero and its rotation p is 1");
    expect(text(`[data-testid="${id}-recent"]`)).toBe("✓");
    expect(q(`[data-testid="${id}-recent"]`).getAttribute("title"))
      .toBe("On the 10 reports after 2026-04-03, r is +0.44 [+0.00, +0.80]: the same clear sign as on all reports");
    expect(text(`[data-testid="${id}-q"]`)).toBe("0.96");
    // the r cell is the deciding (home record) answer
    expect(document.getElementById(id)).toBeTruthy();
  });

  it("the key names both q's apart, the footnote gives each pair's family, the cut date is printed", () => {
    mount();
    expect(text('[data-testid="band-grid-key"]')).toMatch(/^fdr: this grid's own allowance for its 22 bands \(grid q\)/);
    expect(text('[data-testid="band-grid-key"]')).not.toMatch(/corrected/);
    expect(text('[data-testid="band-grid-family"]')).toBe(
      "q: corrected within each pair: L 0⁻3⁺ across 22 bands; R 0⁻3⁺ across 22 bands, by the deciding source's p");
    expect(text('[data-testid="band-grid-cut"]')).toBe("Later 30% of ratings: after 2026-04-03 (rolling cut)");
    expect(text('[data-testid="band-grid-key-wave2"]')).toMatch(/warnings only, never a refusal/);
  });

  it("L 0-3 15.5 Hz: TD decides; a pair outside the family says so", () => {
    mount();
    fireEvent.click(tab("Left", "L 0⁻3⁺"));
    expect(text('[data-testid="cl-band-ZERO_THREE_LEFT-15.5-source"]')).toBe("TD");
    expect(text('[data-testid="cl-band-ZERO_THREE_LEFT-15.5-recent"]')).toBe("few");
    fireEvent.click(tab("Left", "L 1⁻3⁺"));
    expect(text('[data-testid="band-side-Left-family"]'))
      .toBe("q: L 1⁻3⁺ is outside the family (not an allowed sensing pair).");
    expect(text('[data-testid="cl-band-ONE_THREE_LEFT-23.5-q"]')).toBe("out");
  });
});

describe("Sign-off record: the deciding p and the wave-2 rows", () => {
  it("R 0-3 9.5 Hz: decides by the rotation p; current out, later 30%, thresholds from home record, q", () => {
    rtlRender(wrap(<SignoffRecord bandCandidate={{}} summary={ok(SUM_R)} deploymentReport={ok(REP_R)} />));
    expect(SUM_R.gates.find((g) => g.key === "validated").label).toBe("Band validated (rotation test)");
    expect(document.body.textContent).toMatch(/Band validated \(rotation test\)/);
    expect(text('[data-testid="signoff-decides"]')).toBe("Decides: p from shifting ratings");
    expect(kvValue("p from shifting ratings in time (decides)")).toBe("0.747 (146 shifts)");
    expect(kvValue("p from the mixed-effects model (ratings grouped in time), shown only")).toBeTruthy();
    expect(kvValue("Holds with current removed")).toBe("▲warning · p 0.767");
    expect(kvValue("Later 30% of ratings")).toBe("▲after 2026-04-28: r +0.42 [−0.02, +0.67], n=21");
    expect(text('[data-testid="signoff-recent-note"]')).toMatch(/also used in choosing, so this checks consistency over time, not an independent test$/);
    expect(kvValue("Thresholds from home record")).toBe("▲no; clinic recordings only · home swing 2.6-fold");
    expect(text('[data-testid="signoff-home-swing"]')).toBe("Home power at this band swings 2.6-fold across the day "
      + "(lowest 17:00, highest 00:00); these thresholds were set from clinic recordings only, so the device may "
      + "cross them from the time of day alone.");
    expect(kvValue("q corrected within the pair")).toBe("q 0.98 (22 bands, by the home record's p)");
    expect(kvValue("Peak above the smooth background (tie-break only)")).toBe("1.02× (86 PSDs)");
    // C8 is a warning only: no held-out claim is made for the later 30%; the weekly forward test keeps its own line
    expect(document.body.textContent).not.toMatch(/Later weeks, after the cut/);
    expect(document.body.textContent).toMatch(/The same, tested on each later week after training on the weeks before \(18 weeks\)/);
  });

  it("L 0-3 15.5 Hz: too few recent reports, with the server's note; no current-removed answer", () => {
    rtlRender(wrap(<SignoffRecord bandCandidate={{}} summary={ok(SUM_L)} deploymentReport={null} />));
    expect(kvValue("Later 30% of ratings")).toBe("after 2026-04-28: too few (n=8)");
    expect(text('[data-testid="signoff-recent-note"]'))
      .toBe("Recent-reports check: only 8 reports after 2026-04-28 (fewer than 10), not checked");
    expect(kvValue("Holds with current removed")).toBe("not assessed");
    expect(kvValue("q corrected within the pair")).toBe("q 0.71 (22 bands, by the TD p)");
  });
});

describe("The band as chosen: which p decides", () => {
  const bc = { contact: "ZERO_THREE_RIGHT", center_freq_hz: 9.5, adaptive_valid: false,
    evidence: { p_glmer: 0.04, p_rotation: 0.567, rotation_n_orders: 145 } };
  it("with the rotation gate, the rotation p decides and the model's p is shown only", () => {
    rtlRender(wrap(<BandCandidateIdentity bc={bc} envelope={null} decides="rotation" />));
    expect(document.body.textContent).toMatch(/p from shifting ratings in time0\.567 \(145 shifts\) · decides/);
    expect(document.body.textContent).toMatch(/p from the mixed-effects model0\.040 · shown only/);
  });
  it("with no summary, nothing is marked", () => {
    rtlRender(wrap(<BandCandidateIdentity bc={bc} envelope={null} />));
    expect(document.body.textContent).not.toMatch(/decides|shown only/);
  });
});

describe("Thresholds: the home record's daily swing beside them (C7)", () => {
  it("R 0-3 9.5 Hz: the planning table carries the warning line; each threshold's reason ends with it", () => {
    const { container } = rtlRender(wrap(<ParameterTable report={ok(REP_R)} mode="dual" />));
    expect(q('[data-testid="home-swing-line"]')).toBeNull();     // withheld: the device refuses
    const show = Array.from(container.querySelectorAll("button"))
      .find((b) => b.textContent === "Show the values for planning (not for programming)");
    fireEvent.click(show);
    expect(text('[data-testid="home-swing-line"]')).toBe("▲Home power at this band swings 2.6-fold across "
      + "the day (lowest 17:00, highest 00:00); these thresholds were set from clinic recordings only, so the "
      + "device may cross them from the time of day alone.");
  });
  it("withheld while the device refuses: the details print no per-value reason, so no swing text", () => {
    rtlRender(wrap(<ParameterDetails report={ok(REP_R)} mode="dual" />));
    expect(document.body.textContent).not.toMatch(/these thresholds were set from clinic recordings only/);
  });
  it("on a band the device allows, the details fold draws each threshold row's reason with the appended warning", () => {
    // the same live report with the device's answer set to allowed, the only path that prints reasons
    const allowed = clone(REP_R);
    allowed.verdict_detail.device_eligible = true;
    rtlRender(wrap(<ParameterDetails report={ok(allowed)} mode="dual" />));
    const n = (document.body.textContent.match(/these thresholds were set from clinic recordings only/g) || []).length;
    expect(n).toBeGreaterThanOrEqual(2);
    expect(document.body.textContent).toMatch(/Placed from the record \(decision 180\): the median minus the same \+-160\./);
  });
});

describe("D53 (decision 485): a warning, never a refusal", () => {
  it("L 0-3 26.5 Hz: D53 not met, filed under recommended, not required; no refusal names it", () => {
    const rep = clone(REP_L26);
    const d53 = rep.eligibility.advisories.find((a) => a.rule_id === "D53");
    expect(d53.severity).toBe("advisory");
    expect(d53.kind).toBe("advisory_failed");
    expect(rep.eligibility.failures.map((f) => f.rule_id)).not.toContain("D53");
    rtlRender(wrap(<DeviceRuleLedger report={ok(rep)} bare />));
    expect(document.body.textContent).toMatch(/Recommended, not required: not met/);
    expect(document.body.textContent).toMatch(/No folded multiple of the stimulation rate in or near the band/);
  });
  it("the band's peak above the smooth background prints on the sign-off record", () => {
    rtlRender(wrap(<SignoffRecord bandCandidate={{}} summary={ok(SUM_L)} deploymentReport={ok(REP_L26)} />));
    expect(kvValue("Peak above the smooth background (tie-break only)")).toBe("1.30× (112 PSDs)");
  });
});
