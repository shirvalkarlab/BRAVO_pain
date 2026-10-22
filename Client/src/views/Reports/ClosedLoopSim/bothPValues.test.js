/**
 * Decision 477 (the PI, 2026-10-16: "show both"). Beside the mixed-effects model's own p, the same
 * model's exact rotation test: the pain ratings, with their weeks, slid along band power in time by
 * every possible number of samples. On RCS08's layout the model's own p read <= 0.05 for 8.3% of
 * unrelated bands and the rotation test's for 4.95%, so the page shows both and changes no verdict.
 */
import fs from "fs";
import path from "path";
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { wrap } from "testUtils/render";
import BandCandidateIdentity from "./BandCandidateIdentity";

const render = (ui) => rtlRender(wrap(ui));
const src = (f) => fs.readFileSync(path.join(__dirname, f), "utf8");

describe("both p-values for the chosen band", () => {
  it("the band identity shows the model's p and the rotation p with its number of shifts", () => {
    const { container } = render(<BandCandidateIdentity envelope={null} bc={{
      verdict: "candidate", contact: "ZERO_THREE_RIGHT", center_freq_hz: 11.5,
      evidence: { p_glmer: 0.5886, p_rotation: 0.7092, rotation_n_orders: 141 } }} />);
    const t = container.textContent;
    expect(t).toMatch(/p from the mixed-effects model0\.589/);
    expect(t).toMatch(/p from shifting ratings in time0\.709 \(141 shifts\)/);
  });

  it("says not reported, and no count of shifts, when the rotation p is missing", () => {
    const { container } = render(<BandCandidateIdentity envelope={null} bc={{
      verdict: "candidate", evidence: { p_glmer: 0.5886, rotation_n_orders: 141 } }} />);
    expect(container.textContent).toMatch(/p from shifting ratings in timenot reported/);
    expect(container.textContent).not.toMatch(/shifts\)/);
  });

  it("the sign-off card shows the rotation p on the line after the model's own p", () => {
    const s = src("DeploySignoffCard.js");
    // the labels are template strings since wave 2 (the deciding p is marked, decision 482)
    const own = s.indexOf('k={`p from the mixed-effects model (ratings grouped in time)');
    const rot = s.indexOf('k={`p from shifting ratings in time');
    expect(own).toBeGreaterThan(0);
    expect(rot).toBeGreaterThan(own);
    expect(s.slice(rot, rot + 260)).toMatch(/ev\.p_rotation/);
    expect(s.slice(rot, rot + 260)).toMatch(/ev\.rotation_n_orders/);
  });
});
