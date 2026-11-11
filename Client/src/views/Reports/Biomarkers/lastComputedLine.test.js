/**
 * The "Last computed" line under the matching controls adds up every contact pair, so it says so
 * (the PI, 2026-10-04: "last line can report summed counts", decision 438): one rating counts once
 * per pair it matched. The text above each scatter and violin stays that pair's own.
 */
import lastComputedLine from "./lastComputedLine";

const stats = { n_pro_td: 135, n_pro_psd: 379, n_pro_unmatched: 3218, n_td_used: 2400, n_psd_used: 410,
  per_channel: { A: {}, B: {}, C: {}, D: {}, E: {}, F: {} } };

test("names the number of pairs summed over and how a rating is counted", () => {
  expect(lastComputedLine(stats)).toBe(
    "Last computed, summed over 6 contact pairs (a rating counts once per pair): 135 ratings matched "
    + "to TD, 379 to a PSD, 3218 with nothing in the window (2400 3 s TD pieces and 410 PSDs used).");
});

test("one pair reads as one pair; no breakdown without per-pair stats", () => {
  expect(lastComputedLine({ n_pro_td: 2, n_pro_psd: 0, per_channel: { A: {} } }))
    .toBe("Last computed, for 1 contact pair: 2 ratings matched to TD, 0 to a PSD.");
  expect(lastComputedLine(null)).toBeNull();
});
