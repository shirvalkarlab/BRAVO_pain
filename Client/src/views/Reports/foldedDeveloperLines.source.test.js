/**
 * Two lines that are for a developer or a researcher, not for the clinic, sit closed by default on
 * every page (2026-09-26). The Stim Optimizer page already folded both; the Biomarkers page left the
 * control-analyses card open at its foot, and the Closed-Loop page printed the stored-results line
 * ("No stored results under the current key yet: ...") in the open under the recompute bar.
 * A source-text check (the pattern of `timelinePainLabel.source.test.js`): rendering either page
 * pulls in Plotly and every panel and would prove nothing more. `RecomputeBar.js` is not touched;
 * only where each page places it.
 *
 * THE REDESIGN OF 2026-09-26 (SPEC section 4 rule 2, WP7). On the Closed-Loop page the developer
 * actions -- load a saved band file, clear the chosen band, the stored-results line -- sit in one ⋯
 * menu (`ClosedLoopSim/DeveloperMenu.js`), closed by default, which hides its content without
 * unmounting it. The stored-results line is no longer wrapped in a fold of its own inside that menu
 * (no fold inside a fold, rule 4). The Biomarkers page's fold carries the spec's plain title for the
 * control analyses (section 6: "Checks against chance and against the current (run offline)").
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
  // PIN CHANGED 2026-09-26 (WP7): was show="Research checks, saved offline (control analyses)";
  // the spec's wording table replaces "Control analyses" with this plain title.
  expect(fold).toMatch(/show="Checks against chance and against the current \(run offline\)"/);
  expect(fold).not.toMatch(/defaultOpen/);
});

/** The text between a component's first use and the ⋯ menu that must enclose it, or null. */
function enclosingMenu(code, needle) {
  const at = code.indexOf(needle);
  expect(at).toBeGreaterThan(-1);
  const before = code.slice(0, at);
  const open = before.lastIndexOf("<DeveloperMenu");
  const close = before.lastIndexOf("</DeveloperMenu>");
  return open > close ? code.slice(open, at) : null;
}

// Split 2026-09-26 (WP7) from the older test "folds its stored-results line into a closed 'Stored
// results' fold": the line now sits in the ⋯ menu, which is closed by default, and a name saying it
// sits in a fold would be untrue.
test("the Closed-Loop page puts its stored-results line in the closed ⋯ menu, once", () => {
  const code = read("ClosedLoopSim/index.js");
  const menu = enclosingMenu(code, "<CacheStatusLine");
  expect(menu).not.toBeNull();
  expect(menu).toMatch(/Stored results/);
  expect((code.match(/<CacheStatusLine/g) || []).length).toBe(1);
});

test("the Closed-Loop page's stored-results line is not a fold inside the menu", () => {
  const code = read("ClosedLoopSim/index.js");
  expect(enclosingFold(code, "<CacheStatusLine")).toBeNull();
});

test("the ⋯ menu is closed by default and hides its content without unmounting it", () => {
  const menu = read("ClosedLoopSim/DeveloperMenu.js");
  expect(menu).toMatch(/useState\(false\)/);
  expect(menu).toMatch(/hidden=\{!open\}/);
  expect(menu).toMatch(/Load a saved band file/);
  expect(menu).not.toMatch(/open \? children|open && children/);
});
