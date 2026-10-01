/**
 * Step A of the contact-aware Stim Optimizer (2026-10-01): the server groups stretches by
 * (left pulse width, right pulse width, Left contact), so two groups can share pulse widths and
 * differ only in Left contact. The page must keep them apart and name the contact.
 *
 * Values, not shapes: the row read for a setting is the one on the setting's own Left contact;
 * the groups on the current map are keyed with the contact and their headings name it; the
 * pairing sentence names it; a response without contacts reads exactly as before.
 */
jest.mock("plotly.js-dist", () => {
  const noop = () => {};
  return { react: () => Promise.resolve(), purge: noop, restyle: noop, relayout: noop, newPlot: noop };
});
jest.mock("graphing-utility/Plotly", () => ({
  PlotlyRenderManager: class {
    constructor() { this.traces = []; this.layout = {}; }
    subplots() {} clearData() {} render() {} setLayoutProps() {} setXlabel() {} setYlabel() {}
    addHeatmap() {} addScatter() {} addShape() {} addAnnotation() {} setTitle() {} purge() {}
  },
}));

import { rateRowForSetting } from "./blockOfTime";
import { groupByPulseWidthPair, groupHeading, pulseWidthPairingSentence } from "./CurrentMapCard";

const ring1 = { fitted: true, rate_hz: 55, pw_us_left: 60, pw_us_right: 160, left_contact: "L C+1-", n_epochs: 13 };
const ring2 = { fitted: true, rate_hz: 55, pw_us_left: 60, pw_us_right: 160, left_contact: "L C+2-", n_epochs: 8 };

test("the row read for a setting is the one on the setting's own Left contact", () => {
  const plan = { stage1: { rate_strata: [ring1, ring2] } };
  const setting = { rate_hz: 55, detail: { best_pw_us_left: 60, best_pw_us_right: 160, left_contact: "L C+2-" } };
  expect(rateRowForSetting(plan, setting)).toBe(ring2);
});

test("a response without contacts reads the pulse-width row as before", () => {
  const plain = { fitted: true, rate_hz: 55, pw_us_left: 60, pw_us_right: 160 };
  const plan = { stage1: { rate_strata: [plain] } };
  const setting = { rate_hz: 55, detail: { best_pw_us_left: 60, best_pw_us_right: 160 } };
  expect(rateRowForSetting(plan, setting)).toBe(plain);
});

test("the current map keeps two Left contacts at the same pulse widths apart and names each", () => {
  const groups = groupByPulseWidthPair([ring1, ring2]);
  expect(groups.map((g) => g.key)).toEqual(["60_160_L C+1-", "60_160_L C+2-"]);
  // the page's own unit spacing: a narrow no-break space before "µs" (stimFormat.fmtUs)
  expect(groupHeading(groups[1])).toBe("left pulse width 60\u202fµs · right pulse width 160\u202fµs · Left contact L C+2-");
});

test("the pairing sentence names the Left contact", () => {
  expect(pulseWidthPairingSentence([ring1], [])).toContain("60/160 µs, Left contact L C+1-");
});

test("the per-contact counts are said in one sentence, the 0 mA stretches named as shared", () => {
  const { leftContactSentence } = require("./CurrentMapCard");
  const table = [
    { left_contact: "L C+2-", n_epochs: 27, n_reports: 241, shared_into_every_contact: false },
    { left_contact: "L C+1-", n_epochs: 19, n_reports: 231, shared_into_every_contact: false },
    { left_contact: "off (Left 0 mA)", n_epochs: 13, n_reports: 102, shared_into_every_contact: true },
  ];
  expect(leftContactSentence(table)).toBe(
    "Home surveys by Left contact: L C+2- 27 stretches (241 reports); L C+1- 19 stretches (231 reports); "
    + "Left at 0 mA 13 stretches (102 reports), counted with every Left contact.");
  expect(leftContactSentence([])).toBe("");
});
