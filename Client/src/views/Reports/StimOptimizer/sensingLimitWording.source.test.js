/**
 * The readiness card must never let the module's 5.0 mA hard limit read as the safe limit for
 * programming (found in the live safety check of 2026-09-26): the safe ceiling is the PI's, per side.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "SensingEvidenceTable.js"), "utf8");

describe("the readiness card's current-limit wording", () => {
  it("says the module's hard limit is not the safe ceiling", () => {
    expect(src).toMatch(/hard limit, which is not the safe ceiling for programming/);
  });
  it("no longer calls the module limit PI-declared or tested at 165 Hz", () => {
    expect(src).not.toMatch(/PI-declared and was established by testing at 165 Hz/);
    expect(src).not.toMatch(/must sit at or below the flat/);
  });
});
