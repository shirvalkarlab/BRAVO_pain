/**
 * Two lines that are for a developer or a researcher, not for the clinic, sit closed by default on
 * every page (2026-09-26). The Stim Optimizer page already folded both; the Biomarkers page left the
 * control-analyses card open at its foot, and the Closed-Loop page printed the stored-results line
 * ("No stored results under the current key yet: ...") in the open under the recompute bar.
 * A source-text check (the pattern of `timelinePainLabel.source.test.js`): rendering either page
 * pulls in Plotly and every panel and would prove nothing more. `CacheStatusLine.js` and
 * `RecomputeBar.js` are not touched; only where each page places them.
 */
import fs from "fs";
import path from "path";

const read = (f) => fs.readFileSync(path.join(__dirname, f), "utf8")
  .split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");

/** The text between a component's first use and the Fold that must enclose it. */
function enclosingFold(code, needle) {
  const at = code.indexOf(needle);
  expect(at).toBeGreaterThan(-1);
  const before = code.slice(0, at);
  const open = Math.max(before.lastIndexOf("<Fold "), before.lastIndexOf("<SizedFold "));
  const close = Math.max(before.lastIndexOf("</Fold>"), before.lastIndexOf("</SizedFold>"));
  return open > close ? code.slice(open, at) : null;
}

test("the Biomarkers page folds its control-analyses card, closed by default", () => {
  const fold = enclosingFold(read("Biomarkers/index.js"), "<ControlAnalysesSection");
  expect(fold).not.toBeNull();
  expect(fold).toMatch(/show="Research checks, saved offline \(control analyses\)"/);
  expect(fold).not.toMatch(/defaultOpen/);
});

test("the Closed-Loop page folds its stored-results line into a closed 'Stored results' fold", () => {
  const code = read("ClosedLoopSim/index.js");
  const fold = enclosingFold(code, "<CacheStatusLine");
  expect(fold).not.toBeNull();
  expect(fold).toMatch(/show="Stored results"/);
  expect(fold).not.toMatch(/defaultOpen/);
  expect((code.match(/<CacheStatusLine/g) || []).length).toBe(1);
});
