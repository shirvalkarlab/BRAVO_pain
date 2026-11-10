/**
 * Decision 507: the recent-reports check (Later 30%) tells a NOTE from a WARNING on both pages.
 * A band whose recent r has the same sign as on all reports but whose interval reaches across zero
 * carries a note ("too few to confirm the sign on their own"), never the warning mark: "~" in the
 * Closed-Loop band column and before the value in the Biomarkers band table; "▲" stays for the other
 * sign or an interval leaving out the r on all reports; "✓" for the same clear sign.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { wrap } from "testUtils/render";

import BandSweepGridPanel, { recentCell } from "./BandSweepGridPanel";
import { recentWords } from "../Biomarkers/gridReadouts";
import CLGRID from "./__fixtures__/rcs08_wave2_clgrid_nrs_2026-10-22.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const NOTE = "On the 17 reports after 2026-04-03, r is -0.16 [-0.55, +0.22]: the same sign as on all "
  + "reports (r -0.38), but the recent reports are too few to confirm the sign on their own";
const WARN = "On the 17 reports after 2026-04-03, r is +0.16 [-0.22, +0.55]: the other sign from all "
  + "reports (r -0.38). These recent reports were also used in choosing, so this checks consistency "
  + "over time, not an independent test";
const base = { status: "checked", choice_cut_date: "2026-04-03", n_after: 17 };

describe("Later 30%: a note is not a warning (decision 507)", () => {
  it("Closed-Loop band column: ~ for the note, ▲ for a warning, ✓ for the same clear sign", () => {
    const note = { ...base, pearson_r: -0.16, pearson_r_low: -0.55, pearson_r_high: 0.22, warning: null, note: NOTE, words: NOTE };
    const warn = { ...base, pearson_r: 0.16, pearson_r_low: -0.22, pearson_r_high: 0.55, warning: WARN, note: null, words: WARN };
    const clear = { ...base, pearson_r: -0.5, pearson_r_low: -0.8, pearson_r_high: -0.2, warning: null, note: null,
      words: "On the 17 reports after 2026-04-03, r is -0.50 [-0.80, -0.20]: the same clear sign as on all reports" };
    expect(recentCell({ recent_check: note })).toEqual({ text: "~", title: NOTE });
    expect(recentCell({ recent_check: warn })).toEqual({ text: "▲", title: WARN });
    expect(recentCell({ recent_check: clear }).text).toBe("✓");
  });

  it("Biomarkers band table: the note's value starts with ~, a warning's with ▲", () => {
    const note = { ...base, pearson_r: -0.16, pearson_r_low: -0.55, pearson_r_high: 0.22, warning: null, note: NOTE };
    const warn = { ...base, pearson_r: 0.16, pearson_r_low: -0.22, pearson_r_high: 0.55, warning: WARN, note: null };
    expect(recentWords(note)).toBe("~ r −0.16 [−0.55, +0.22], n=17");
    expect(recentWords(warn)).toBe("▲ r +0.16 [−0.22, +0.55], n=17");
    expect(recentWords({ ...warn, warning: null })).toBe("r +0.16 [−0.22, +0.55], n=17");
  });

  it("the Closed-Loop key names the ~ mark", () => {
    rtlRender(wrap(<BandSweepGridPanel grid={CLGRID} participantUid="uid"
      committed={{ contact: "ZERO_THREE_RIGHT", centerHz: 9.5 }}
      committedBySide={{ Left: { contact: "ZERO_THREE_LEFT", centerHz: 15.5 },
        Right: { contact: "ZERO_THREE_RIGHT", centerHz: 9.5 } }}
      onCandidateChosen={() => {}} />));
    expect(document.querySelector('[data-testid="band-grid-key-wave2"]').textContent)
      .toMatch(/Later 30%: ✓ same clear sign, ~ same sign, too few to confirm, ▲ warning, few = too few recent reports/);
  });
});
