/**
 * The sign-off card's "q corrected within the pair" row carries the band's area-under-the-curve q
 * (decision 500's open item) beside its correlation q, rendered from RCS08's live sign-off summaries
 * of 2026-10-23 for the two ticked bands, R 0-3 9.5 Hz and L 0-3 15.5 Hz (Left Leg VAS, the bands'
 * own score), captured in the server container through `deployment_summary` with the frozen pain
 * table (`_agent_bridge/_aucsign_capture.py`; hash labels replaced, no serials or export names).
 *
 * Pinned, with the live values: R 0-3 9.5 Hz "r 0.98 (22 bands, by the home record's p) · AUC 0.99
 * (22 bands)"; L 0-3 15.5 Hz "r 0.71 (22 bands, by the TD p) · AUC 0.33 (22 bands)"; no warning mark
 * on either (the server gives none); a ▲ and the server's sentence when it gives an AUC warning; a
 * summary served before the AUC q prints the row as it did.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { wrap } from "testUtils/render";

import SignoffRecord from "./DeploySignoffCard";
import SUM_R from "./__fixtures__/rcs08_aucsign_summary_R03_9p5_2026-10-23.json";
import SUM_L from "./__fixtures__/rcs08_aucsign_summary_L03_15p5_2026-10-23.json";

jest.mock("plotly.js-dist", () => ({
  react: jest.fn(), purge: jest.fn(), restyle: jest.fn(), relayout: jest.fn(), newPlot: jest.fn(),
  toImage: jest.fn(),
}));
jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const ok = (data) => ({ data, loading: false, err: null });
const LABEL = "q corrected within the pair";
const kvValue = (label) => {
  const rows = Array.from(document.querySelectorAll(".cl-signoff-record span, .cl-signoff-record div"));
  const lab = rows.find((el) => el.children.length === 0 && el.textContent === label);
  if (!lab) return null;
  const sib = lab.nextElementSibling;
  return sib ? sib.textContent : null;
};
const withFc = (summary, patch) => {
  const s = JSON.parse(JSON.stringify(summary));
  s.evidence.family_correction = { ...s.evidence.family_correction, ...patch };
  return s;
};
const mount = (s) => rtlRender(wrap(<SignoffRecord bandCandidate={{}} summary={ok(s)} deploymentReport={null} />));

describe("Sign-off record: the AUC q beside the correlation q", () => {
  it("the fixtures hold the live values the rows print", () => {
    const r = SUM_R.evidence.family_correction;
    const l = SUM_L.evidence.family_correction;
    expect([r.family_q.toFixed(2), r.family_q_auc.toFixed(2), r.family_n_auc]).toEqual(["0.98", "0.99", 22]);
    expect([l.family_q.toFixed(2), l.family_q_auc.toFixed(2), l.family_n_auc]).toEqual(["0.71", "0.33", 22]);
    expect([r.family_q_auc_warning, l.family_q_auc_warning]).toEqual([null, null]);
  });

  it("R 0-3 9.5 Hz: r 0.98 · AUC 0.99, no warning mark", () => {
    mount(SUM_R);
    expect(kvValue(LABEL)).toBe("r 0.98 (22 bands, by the home record's p) · AUC 0.99 (22 bands)");
    expect(document.querySelector('[data-testid="signoff-auc-q-warning"]')).toBeNull();
  });

  it("L 0-3 15.5 Hz: r 0.71 · AUC 0.33, no warning mark", () => {
    mount(SUM_L);
    expect(kvValue(LABEL)).toBe("r 0.71 (22 bands, by the TD p) · AUC 0.33 (22 bands)");
    expect(kvValue(LABEL)).not.toMatch(/▲/);
  });

  it("an AUC warning from the server: a ▲ on the AUC part only, and its sentence below", () => {
    const w = "After correcting for the 22 area-under-the-curve bands tested on L 0⁻3⁺, this band's q is 0.33: "
      + "it may be a chance finding";
    mount(withFc(SUM_L, { family_q_auc_warning: w }));
    expect(kvValue(LABEL)).toBe("r 0.71 (22 bands, by the TD p) · ▲AUC 0.33 (22 bands)");
    expect(document.querySelector('[data-testid="signoff-auc-q-warning"]').textContent).toBe(w);
  });

  it("an AUC row out of the family prints its reason", () => {
    mount(withFc(SUM_R, { family_q_auc: null, family_q_auc_status: "not an allowed sensing pair" }));
    expect(kvValue(LABEL)).toBe("r 0.98 (22 bands, by the home record's p) · AUC: not an allowed sensing pair");
  });

  it("a summary served before the AUC q prints the row as it did", () => {
    const old = JSON.parse(JSON.stringify(SUM_R));
    ["family_q_auc", "family_p_auc", "family_p_auc_source", "family_q_auc_status", "family_q_auc_warning",
      "family_n_auc", "auc_words", "auc_n_in_family", "auc_n_built"].forEach((k) => delete old.evidence.family_correction[k]);
    mount(old);
    expect(kvValue(LABEL)).toBe("q 0.98 (22 bands, by the home record's p)");
  });
});
