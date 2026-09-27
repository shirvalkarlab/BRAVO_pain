/**
 * classBalanceFlag — decision 337 (the PI, 2026-09-27): warn when the high/low pain-day split that
 * feeds the discrimination reading (an area-under-the-curve figure, computed as though from a
 * one-band logistic fit) is too lopsided to trust. Two thresholds from the literature, the
 * stricter of the two wins:
 *   - Peduzzi, Concato, Kemper, Holford & Feinstein 1996 (J Clin Epidemiol) — the widely used
 *     "events per variable" rule for a logistic fit: below 10 members in the smaller of the two
 *     outcome groups per fitted term, the fitted numbers and their spread become unreliable. With
 *     one term (the band's own power) that is 10 in the smaller group.
 *   - A widely used general severity scale for an uneven split (see e.g. MachineLearningMastery's
 *     imbalanced-classification guide, summarising Kotsiantis et al. 2006 and others): once the
 *     larger group is at least 3 times the smaller, the split counts as "moderate" imbalance and
 *     is worth a caution.
 */
import { classBalanceFlag } from "./binarizationModel";

test("no flag when both groups are sized well and close to even", () => {
  expect(classBalanceFlag(40, 45)).toBeNull();
  expect(classBalanceFlag(0, 0)).toBeNull();
});

test("flags too few in the smaller group, even when the two are close", () => {
  const msg = classBalanceFlag(8, 9);
  expect(msg).toMatch(/8/);
  expect(msg).toMatch(/10/);
});

test("flags a lopsided split even once both groups clear the size floor", () => {
  const msg = classBalanceFlag(12, 60);
  expect(msg).toMatch(/12/);
  expect(msg).toMatch(/60/);
});

test("the boundary cases: ratio just under 3 passes, at 3 flags; 10 passes, 9 flags", () => {
  expect(classBalanceFlag(10, 29)).toBeNull();
  expect(classBalanceFlag(10, 30)).not.toBeNull();
  expect(classBalanceFlag(10, 10)).toBeNull();
  expect(classBalanceFlag(9, 9)).not.toBeNull();
});

test("never uses jargon the house rules ban from page text", () => {
  const msg = classBalanceFlag(5, 50);
  const lower = msg.toLowerCase();
  for (const banned of ["class imbalance", "predictor", "coefficient", "logistic", "classifier",
                        "epv", "events per variable"]) {
    expect(lower).not.toContain(banned);
  }
});
