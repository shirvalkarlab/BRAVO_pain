/**
 * "PSD", NEVER "SPECTRUM", ON THE THREE ANALYSIS PAGES (the PI, 2026-09-25 night).
 * The Biomarkers, Closed-Loop and Stim Optimizer pages name the two sources of band power one way:
 *   "TD"  -- band power from the time-domain recording;
 *   "PSD" -- the device's own 30 s snapshot (a patient event). A montage recording's samples are
 *            worked out from its time-domain signal and are TD (the PI, 2026-09-26).
 * "spectrum", "spectra" and "spectral" are not used in anything a reader sees. This reads every
 * string literal and every piece of JSX text the three pages' components (and the shared components
 * they render) can print, with comments stripped and the code inside `${...}` removed, and fails if
 * one of the three words appears as a word of its own. Code names such as `n_spectral_samples` or
 * `spectrumRevealed` are not text and are not matched.
 *
 * PENDING lists text still on a page that the PI has to rule on, because it is neither plainly TD
 * nor plainly PSD. Each entry must still be found in its file, so it cannot outlive the text.
 */
import fs from "fs";
import path from "path";

const PAGE_DIRS = ["Biomarkers", "ClosedLoopSim", "StimOptimizer"];
// Shared components the three pages render, outside their own folders.
const SHARED = [
  "RecomputeBar.js", "CacheStatusLine.js", "legibleText.js",
  "ControlAnalyses/ControlAnalysesCard.js", "ControlAnalyses/figures.js",
];

// Empty since 2026-09-26: the PI ruled that the older Biomarkers scan's button says "the all-band
// scan", so "Click Recompute above to run the full-spectrum scan." is no longer excused.
const PENDING = [];

const WORD = /(^|[^A-Za-z0-9_$])spectr(?:um|a|al)(?![A-Za-z0-9_$])/i;

function pageFiles() {
  const own = PAGE_DIRS.flatMap((d) => fs.readdirSync(path.join(__dirname, d))
    .filter((f) => f.endsWith(".js") && !f.endsWith(".test.js"))
    .map((f) => `${d}/${f}`));
  return own.concat(SHARED);
}
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
}
function withoutInterpolations(lit) {
  // Remove `${...}` (one level of nested braces is enough for this code base).
  return lit.replace(/\$\{(?:[^{}]|\{[^{}]*\})*\}/g, " ");
}
function printable(src) {
  const code = stripComments(src);
  const lits = (code.match(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g) || [])
    .map(withoutInterpolations);
  const jsx = (code.match(/>([^<>{}]*[A-Za-z][^<>{}]*)</g) || []).map((s) => s.slice(1, -1));
  return lits.concat(jsx);
}
function offending(src, pending = []) {
  return printable(src)
    .map((t) => pending.reduce((s, p) => s.split(p).join(""), t))
    .filter((t) => WORD.test(t));
}
function read(f) {
  return fs.readFileSync(path.join(__dirname, f), "utf8");
}

describe("the three analysis pages say PSD or TD, never spectrum", () => {
  const files = pageFiles();

  test("the scan covers every page component and the shared ones", () => {
    expect(files.length).toBeGreaterThan(60);
    ["Biomarkers/BiomarkerDataTimeline.js", "ClosedLoopSim/ThreeSourceResponsePanel.js",
      "StimOptimizer/TitrationSessionCard.js", "ControlAnalyses/ControlAnalysesCard.js"]
      .forEach((f) => expect(files).toContain(f));
  });

  files.forEach((f) => {
    test(`${f}: no "spectrum", "spectra" or "spectral" in any printable text`, () => {
      const pending = PENDING.filter((p) => p.file === f).map((p) => p.text);
      expect(offending(read(f), pending)).toEqual([]);
    });
  });

  test("the acquisition timeline's montage legend names it TD, and says no hover shows a PSD", () => {
    // Until 2026-09-26 the legend read "PSD (...): montage (...; hover \u2192 PSD)"; the tick's hover
    // shows the recording's name only, and the page reads each montage through its TD.
    const tl = stripComments(read("Biomarkers/BiomarkerDataTimeline.js"));
    expect(tl).toContain("TD (montage): one tick per montage or survey recording");
    expect(tl).not.toContain("hover \u2192 PSD");
  });

  test("the Biomarkers page's Recompute prompt names the all-band scan", () => {
    // Printed as "... Click <strong>Recompute</strong> above to run the all-band scan."
    const idx = read("Biomarkers/index.js");
    expect(idx).toContain("<strong>Recompute</strong>{\" above to run the all-band scan.\"}");
    expect(idx).not.toContain("above to run the full-spectrum scan.");
  });

  test("every pending entry is still on its page (remove it once the PI rules)", () => {
    PENDING.forEach((p) => expect(read(p.file)).toContain(p.text));
  });

  test("the guard itself catches the words (negative control)", () => {
    const src = 'const a = "hover \u2192 spectrum"; // the spectrum in a comment is fine\n'
      + "const b = <span>Device spectra on record</span>;\n"
      + "const c = `Spectral samples: ${n_spectral_samples}`;\n"
      + "/* spectral block comment */ const d = \"the full-spectrum scan\";\n"
      + "const e = `On the ${a.n_spectral_samples} samples`; const f = showSpectrum ? \"Hide\" : \"Show\";\n"
      + 'const g = "device_spectrum_total_grid";';
    expect(offending(src)).toHaveLength(4);
    expect(offending(src, ["the full-spectrum scan"])).toHaveLength(3);
    expect(offending("// only a comment about the spectrum and its spectra")).toEqual([]);
  });
});
