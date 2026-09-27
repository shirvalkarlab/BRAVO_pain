/**
 * The "Choose a band" grid's family-wise mark named the corrected value it prints "p"
 * ("p 0.002 after allowing for all 22 bands tested"), but the number the server sends
 * (`family_wise_q_8_to_30hz`) is a Benjamini-Hochberg q, not a p. The PI, 2026-09-26: print it as
 * q, with the correction named in words -- "q 0.002 (fdr 22 bands)".
 */
import { allowanceWords } from "./BandSweepGridPanel";

describe("allowanceWords", () => {
  it("names the number q, and says the p it corrects rather than being called p itself", () => {
    expect(allowanceWords(0.002)).toBe("q 0.002 (fdr 22 bands)");
  });

  it("takes the band count it was given", () => {
    // 18, not the default 22: with 22 this test also passed when the count was ignored.
    expect(allowanceWords(0.002, 18)).toBe("q 0.002 (fdr 18 bands)");
  });

  it("is null when no q is given, same as before", () => {
    expect(allowanceWords(null)).toBeNull();
  });
});

test("the grid tooltip carries the corrected value once, with no brackets inside brackets", () => {
  const fs = require("fs");
  const src = fs.readFileSync(require.resolve("./BandSweepGridPanel.js"), "utf8");
  expect(src).not.toMatch(/tested\$\{words \? ` \(\$\{words\}\)`/);
});
