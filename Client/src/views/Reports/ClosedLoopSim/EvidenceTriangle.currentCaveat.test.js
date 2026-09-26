/**
 * The interim caveat on the band-power-to-pain edge, and the provisional sentence in the open.
 *
 * WHY. The triangle's second edge (band power to pain) is estimated with no term for the
 * stimulation current that was running at the time. Measured on 2026-09-22: on this participant's
 * left lead, taking the current in force out of the same band family shrinks every positive reading
 * (on L 0-3+, 22.5-27.5 Hz, +0.08 to +0.20 becomes +0.01 to +0.12 against NRS). Until that edge is
 * re-estimated with the current taken out, a clinician reading this card should see the fact stated,
 * not have to know it. The caveat is scoped: the left lead, and the band family that was measured.
 *
 * The second half: the module already writes "PROVISIONAL: ... intervals span zero ... the pattern
 * rests on the point signs alone" into the coherence note, and the card kept it inside a fold. The
 * sentence that says the verdict rests on point signs alone is not a detail; it reads in the open.
 */
import "@testing-library/jest-dom";
import { render as rtlRender } from "@testing-library/react";
import { ThemeProvider } from "@mui/material/styles";

import theme from "assets/theme";
import { PlatformContextProvider } from "context";

import EvidenceTrianglePanel from "./EvidenceTrianglePanel";
import payload from "./__fixtures__/rcs08_deployment_payload_2026-09-15.json";

const wrap = (ui) => (
  <ThemeProvider theme={theme}>
    <PlatformContextProvider initialStates={{ darkMode: false }}>{ui}</PlatformContextProvider>
  </ThemeProvider>
);

const withCandidate = (channel, centerHz) => {
  const d = JSON.parse(JSON.stringify(payload));
  d.candidates = [{ ...(d.candidates || [{}])[0], channel, center_hz: centerHz }];
  return d;
};

const CAVEAT = /stimulation current in force/i;

describe("the band-power-to-pain edge names the current in force as an unadjusted confound", () => {
  it("says it for a left-lead band inside the family that was measured", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    const text = container.textContent;
    expect(text).toMatch(CAVEAT);
    // the measurement itself, so the sentence is a finding and not an opinion
    expect(text).toMatch(/\+0\.08/);
    expect(text).toMatch(/\+0\.01/);
    // and it says plainly that this edge carries no such adjustment yet
    expect(text).toMatch(/this edge is not adjusted for it/i);
  });

  it("does not say it on the right lead, where the measurement was not made", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_RIGHT", 24.5) }} />));
    expect(container.textContent).not.toMatch(CAVEAT);
  });

  it("does not say it for a left band outside the family that was measured", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 12.5) }} />));
    expect(container.textContent).not.toMatch(CAVEAT);
  });
});

// A closed fold keeps its children mounted (`Collapse unmountOnExit={false}`), so "the text is in
// the document" says nothing about whether a reader can see it. These helpers ask the question that
// matters: is the sentence inside a fold that is currently closed?
const leafWith = (root, re) => Array.from(root.querySelectorAll("*"))
  .filter((el) => el.children.length === 0 && re.test(el.textContent || ""))[0];
const insideClosedFold = (el) => {
  let n = el;
  while (n) {
    if (n.classList && n.classList.contains("MuiCollapse-hidden")) return true;
    n = n.parentElement;
  }
  return false;
};

describe("the coherence note is one fold again (decision 302, superseding decision 235's split)", () => {
  // Decision 235 printed the note's "PROVISIONAL: ... intervals span zero" half in the open. By
  // 2026-09-26 the same fact was on the page three more times -- each edge row's "INTERVAL SPANS
  // ZERO" with its numbers, the triangle's "uncertain" labels, and the decision card's status
  // line -- and the PI ruled that repeated statements go. Updated on purpose: the whole note,
  // both halves, sits in "How the sign agreement was tested".
  it("keeps the provisional half, now inside the closed fold", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    expect(container.textContent).toMatch(/How the sign agreement was tested/);
    const node = leafWith(container, /rests on the point signs alone/i);
    expect(node).toBeTruthy();
    expect(insideClosedFold(node)).toBe(true);
  });

  it("the edge rows still say, in the open, which intervals span zero", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    const node = leafWith(container, /INTERVAL SPANS ZERO/);
    expect(node).toBeTruthy();
    expect(insideClosedFold(node)).toBe(false);
  });

  it("leaves the rest of the note where it was, inside the fold", () => {
    const { container } = rtlRender(wrap(
      <EvidenceTrianglePanel report={{ data: withCandidate("ZERO_THREE_LEFT", 24.5) }} />));
    const rest = leafWith(container, /Dual Threshold ramps amplitude UP/i);
    expect(rest).toBeTruthy();
    expect(insideClosedFold(rest)).toBe(true);
  });
});
