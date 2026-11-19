/**
 * With the clinic-sheet switch on, the page's pain scores and matching index carry the sheets'
 * ratings (the PI, 2026-10-04, decision 436): both requests send the switch and are asked again when
 * it moves; the composite score leaves the sheet ratings out, as the server's heat maps do (the
 * sheets carry no MPQ); the coverage sentence is handed the number of sheet ratings.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "index.js"), "utf8");
const effectOf = (url) => {
  const i = src.indexOf(`SessionController.query("${url}"`);
  return src.slice(i, src.indexOf("]);", i) + 3);
};

test("the pain scores request sends the switch and follows it", () => {
  const e = effectOf("/api/queryPainScores");
  expect(e).toMatch(/IncludeClinicSheetRatings: includeClinicSheetRatings/);
  expect(e).toMatch(/\[participant_uid, includeClinicSheetRatings\]\);$/);
});

test("the matching index request sends the switch and follows it", () => {
  const e = effectOf("/api/queryPsdScanIndex");
  expect(e).toMatch(/IncludeClinicSheetRatings: includeClinicSheetRatings/);
  expect(e).toMatch(/\[participant_uid, metric, includeClinicSheetRatings\]\);$/);
});

test("the composite leaves sheet ratings out; the coverage sentence gets their count", () => {
  expect(src).toMatch(/return m \? m\.points\.filter\(\(p\) => !p\.sheet\) : \[\];/);
  expect(src).toMatch(/n_clinic: previewPoints\.filter\(\(p\) => p && p\.sheet\)\.length/);
});
