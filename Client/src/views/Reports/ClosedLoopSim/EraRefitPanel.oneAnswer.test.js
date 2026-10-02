/**
 * ONE STABILITY ANSWER (the PI, 2026-10-02, page review 4.2). The Closed-Loop page printed "Cannot
 * tell" in "Stability across stimulation states" and "✓ Holds across stimulation states" in the
 * card below it (live L 0-3+ 25.5 Hz Overall VAS: 2 states estimable, every range overlapping, the
 * interaction test p 0.28). The answer is the one above; this card now states its overlap check as
 * supporting detail, with no verdict words and no ✓, and keeps ▲ only on a fact that is a warning.
 */
jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

// eslint-disable-next-line import/first
import { eraDetail } from "./EraRefitPanel";

const LIVE = { n_eras_estimable: 2, any_reversed: false, any_below_half: false, portable_by_ci: true,
  stim_lrt: { available: true, lrt_p: 0.2808, stim_stable: true }, auc_spread: 0.12, cutpoint_spread: 0.3 };

describe("the switching-point card gives supporting detail, never a second stability answer", () => {
  it("overlapping ranges are stated as a fact, without 'Holds' or a tick", () => {
    const d = eraDetail(LIVE);
    expect(d.caution).toBe(false);
    expect(d.text).toMatch(/^Every state's 95% range overlaps the reading for all states together/);
    expect(d.text).toMatch(/p 0\.281/);
    expect(d.text).not.toMatch(/Holds/);
    expect(d.text).toMatch(/the stability answer is the one in "Stability across stimulation states" above/);
  });
  it("a confident reversal is still flagged as a warning", () => {
    const d = eraDetail({ ...LIVE, any_reversed: true });
    expect(d.caution).toBe(true);
    expect(d.text).toMatch(/whole 95% range sits below 0\.5/);
  });
  it("one estimable state says only that", () => {
    const d = eraDetail({ ...LIVE, n_eras_estimable: 1 });
    expect(d.caution).toBe(false);
    expect(d.text).toMatch(/^Only one stimulation state has enough data/);
    expect(d.text).not.toMatch(/cannot be checked/);
  });
  it("no data, no detail", () => {
    expect(eraDetail(null)).toBeNull();
  });
});
