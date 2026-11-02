/** Independent edge cases: missing evidence stays absent; response warnings never become gates. */
import {
  gridSourceName, chooseWords, sourceGridTitle, cannotChooseWhy, deciderOf, decidedByWords,
  decidingValues, rIntervalN, chronicCountsWords, currentOutWords, dailySwingWords,
  recentWords, familyQWords, familyFootnote, familyQAucWords, familyAucFootnote,
  chronicMarkCentres, cutDateWords, chronicMatchWarning,
} from "./gridReadouts";

test("older or missing source metadata supplies no inferred choice", () => {
  expect(gridSourceName("unrecognized")).toBeNull();
  expect(chooseWords(null)).toBeNull();
  expect(chooseWords({})).toBeNull();
  expect(sourceGridTitle(null)).toBeNull();
  expect(sourceGridTitle({ grid_source: "td" })).toBe("TD only");
  expect(cannotChooseWhy(null)).toBeNull();
  expect(cannotChooseWhy({ best_correlation_rows: [{ can_choose_band: false }] })).toBeNull();
});

test("uncovered chronic rows use TD; an explicit decider supplies its own values", () => {
  expect(deciderOf(null)).toBeNull();
  expect(deciderOf({})).toBeNull();
  expect(deciderOf({ choice_source: "chronic", chronic: { covered: false } })).toBe("TD");
  expect(decidedByWords({ choice_source: "none" })).toBe("Shown, cannot choose");
  expect(decidedByWords({})).toBeNull();
  expect(decidingValues(null)).toBeNull();
  const row = { decided_by: "chronic", pearson_r: -0.2, n_pain_reports: 8,
    chronic: { pearson_r: 0.8, n_reports: 16 }, chronic_match_warning: "window warning" };
  expect(decidingValues(row)).toMatchObject({ r: -0.2, n: 8, matchWarning: "window warning" });
});

test("unavailable intervals and home counts remain unavailable", () => {
  expect(rIntervalN(null, -1, 1, 8)).toBe("no r");
  expect(rIntervalN("invalid", -1, 1, 8)).toBe("no r");
  expect(rIntervalN(0.2)).toBe("r +0.20");
  expect(chronicCountsWords(null)).toBeNull();
  expect(chronicCountsWords({ covered: false, n_reports: 0 })).toBeNull();
  expect(chronicCountsWords({ covered: true })).toBeNull();
  expect(chronicCountsWords({ covered: true, n_reports: 0 })).toBe("0 matched");
});

test("current and daily warnings distinguish absent, untested and measured evidence", () => {
  expect(currentOutWords(null)).toBeNull();
  expect(currentOutWords({})).toBe("not assessed");
  expect(currentOutWords({ status: "constant current", p: NaN })).toBe("constant current");
  expect(currentOutWords({ status: "holds", p: 0.02 })).toBe("holds · p 0.02");
  expect(dailySwingWords(null)).toBeNull();
  expect(dailySwingWords({})).toBeNull();
  expect(dailySwingWords({ status: "unavailable" })).toBe("unavailable");
  expect(dailySwingWords({ status: "measured", ratio: 1.2, hour_low: 3, hour_high: 12 }))
    .toBe("1.2-fold (low 03:00, high 12:00)");
});

test("recent-report checks preserve untested states and server warnings", () => {
  expect(recentWords(null)).toBeNull();
  expect(recentWords({})).toBeNull();
  expect(recentWords({ status: "too few recent reports" })).toBe("too few (n=?)");
  expect(recentWords({ status: "none" })).toBe("none");
  expect(recentWords({ status: "checked", warning: "unstable", pearson_r: -0.3, n_after: 12 }))
    .toBe("▲ r −0.30, n=12");
});

test("correlation and AUC families never borrow each other's q or status", () => {
  expect(familyQWords(null)).toBeNull();
  expect(familyQWords({ family_q: 0.01 })).toBeNull();
  expect(familyQAucWords({ family_q_auc: 0.01 })).toBeNull();
  expect(familyQAucWords({ family_q_auc_status: "not assessed" })).toBe("not assessed");
  expect(familyFootnote(null)).toBeNull();
  expect(familyFootnote({ available: false, words: "not used" })).toBeNull();
  expect(familyFootnote({ words: "server family" })).toBe("q: server family");
  expect(familyFootnote({})).toBeNull();
  expect(familyFootnote({ per_pair: { pair: { n_in_family: 3 } } })).toBe("q: corrected within each pair: pair across 3 bands");
  expect(familyAucFootnote(null)).toBeNull();
  expect(familyAucFootnote({ per_pair_auc: {} })).toBeNull();
  expect(familyAucFootnote({ per_pair_auc: { pair: { n_in_family: 4 } } }))
    .toBe("AUC q: its own family, corrected within each pair: pair across 4 bands");
});

test("home marks exclude invalid centers and cut-date labels require a date", () => {
  expect(chronicMarkCentres(null)).toEqual([]);
  expect(chronicMarkCentres({ best_correlation_rows: [
    { decided_by: "chronic", band_center_hz: "bad" },
    { decided_by: "chronic", band_center_hz: 15.5 },
    { choice_source: "TD", band_center_hz: 9.5 },
  ] })).toEqual([15.5]);
  expect(cutDateWords(null)).toBeNull();
  expect(cutDateWords({})).toBeNull();
  expect(cutDateWords({ choice_cut_date: "2040-01-01" })).toBe("Later 30% of ratings: after 2040-01-01");
});

test("a nondefault home match keeps its warning even on sparse stored responses", () => {
  expect(chronicMatchWarning(null)).toBeNull();
  expect(chronicMatchWarning({ settings_applied: { chronic_match: "covering" } })).toBeNull();
  const settings_applied = { chronic_match: "window", chronic_match_is_default: false };
  expect(chronicMatchWarning({ settings_applied }))
    .toBe("Not the recommended default way of matching reports to the home record.");
  expect(chronicMatchWarning({ settings_applied, band_time_sweep: { pair: {
    best_correlation_rows: [{ chronic_match_warning: "server warning" }],
  } } })).toBe("server warning");
  expect(chronicMatchWarning({ settings_applied, band_time_sweep: { pair: {
    chronic_band_choice: { warning: "grid warning" },
  } } })).toBe("grid warning");
});
