# Fix plan from the three page reviews (2026-10-02, written while the PI slept)

Nothing here is done. Source: three read-only agents clicked through the local BRAVO (RCS08), one per page.
Their raw lists: scratchpad `review_biomarkers.md`, `review_stimoptimizer.md`, `review_closedloop.md`
(copied beside this file). Not yet checked by me: every item below is the agent's
observation, so step 0 of each fix is to reproduce it.
Each fix = its own commit + decision row + regression test; wrong numbers first, layout last.
The PI gives the go-ahead before any of it runs (rule 8).

## A. Wrong or contradictory numbers (do first)

- [ ] **A1. Closed-Loop: pain score flips Left Leg -> Overall VAS after load; first result already says "settings have changed".**
  Three causes to test, cheapest first: (1) the dropdown starts from the page default and is overwritten by the saved band's score after mount, changing the cache key; (2) the stale check compares an un-normalised key to a normalised one; (3) the saved result really was built on Overall VAS (data, not a bug). Look at `ClosedLoopSim/PainScoreSelect.js`, `useCachedResult` key, the "settings changed" test.
- [ ] **A2. Closed-Loop: amber "settings have changed" banner persists after a successful Recompute** (shown three times: top bar, card, LSB panel). Same code as A1; one test for both: after recompute the key equals the stored key.
- [ ] **A3. Closed-Loop: three statements about the grid score and window disagree** (Left Leg ±15 min vs Overall VAS ±5 min vs "chosen on Overall VAS"). Decide which is the grid and which the signed band, label each; one source for the string.
- [ ] **A4. Closed-Loop: counts that disagree on one card:** 93 samples vs 92 matched readings (62 reports both). Find which filter drops one; show one count or say why two.
- [ ] **A5. Closed-Loop: same AUC (stimulation current removed) 0.51 vs 0.539 (62 vs 24 reports), and interval ends differ between cards (0.59 vs 0.60, 0.64 vs 0.65, 0.63 vs 0.68).** Print every interval from one formatter; label the report count beside each AUC.
- [ ] **A6. Closed-Loop: power vs current rises (+0.083/mA) in the evidence card and falls (-16.51/mA) in Background, on a different contact (L 1-3, not the chosen L 0-3).** Label the contact on both; consider drawing Background on the chosen contact.
- [ ] **A7. Closed-Loop: top "Cannot tell" vs bottom "Holds" for stability across states.** Different tests; name the test in each, keep verdict words once (rule 15).
- [ ] **A8. Stim Optimizer next-visit card: text "30 blocks tie... 3.09 NRS points" but every ranked row is worse (0.89-1.78 worse).** Highest priority: find where 3.09 comes from (likely an improvement taken from a different quantity, or the sign flipped), fix text to come from the table rows.
- [ ] **A9. Stim Optimizer readiness card: "12 combinations screened, 12 could not be built" beside assessed counts.** Say what was not built.
- [ ] **A10. Stim Optimizer exploratory ladder: record dates to 2026-06-24 but evidence runs to 2026-09-02; "23 stretches" vs 31/24/11 for the same contact; bare "3738 h".** Check against live data; label which record each count uses.
- [ ] **A11. Stim Optimizer: same "+0.00 ± 1.24" on Left and Right candidate gauges.** Confirm not a copied value (print both sides' underlying numbers).
- [ ] **A12. Biomarkers headline: "0 rise, 28 fall of 22 bands, on R 0-3, L 1-3"** mixes two pairs. Say per pair.
- [ ] **A13. Biomarkers: "49 of 146 matched pain reports" vs 522 on the heat maps; split "54" vs median "57".** Label the settings each count uses.
- [ ] **A14. Biomarkers checks panel offers only Overall VAS / NRS, starts on Overall VAS while page score is Left Leg VAS.** Either follow the page score or say it covers two scores only.

## B. Failures and waits

- [ ] **B1. 502 on first load of `queryPsdScanIndex` (Biomarkers) and one `queryStimOptimizer` 502 on "Recompute anyway" that blanked the whole Stim page for ~3 s.** Cause to test first: three agents plus warm-up loading the same 16 workers at once (gunicorn worker timeout or restarts); then a worker killed by memory; then a real bug. Check gunicorn/nginx logs for the 502 times. Fix regardless: retry once on 502, keep the old result on screen and show errors inline (never replace the page).
- [ ] **B2. First loads: Biomarkers ~2 min, Stim Optimizer ~3 min, Closed-Loop ~2.5 min; recompute 1.5-2 min (Closed-Loop).** The three pages were opened together, so part is contention. Re-measure each alone (alternating rounds, as in decision 372-373) before touching code. Meanwhile fix the stale "about 10 s" text on the Stim page to show elapsed time and stage.
- [ ] **B3. 12-20 `updateSessions` POSTs on every page load.** Find the caller; batch or skip when nothing changed.
- [ ] **B4. During Recomputing the stale banner and a live Recompute button stay clickable (double start).** Disable while running.
- [ ] **B5. WebSocket `/socket/notification` fails on every page** (console only). Check whether it works on the Mac stack at all; if not, stop opening it.
- [ ] **B6. Empty "Stored results, memory" fold during first load.** Show "Reading..." until loaded.

## C. Clipped or overlapping text in figures

- [ ] **C1. Closed-Loop plots:** rating-count plot note cut both sides and over the data line, "now: 62" over "lower end of range: 5%"; device-readings plot subtitle over the x title; axis titles clipped ("chance of detecting a real link with pa..."); "fitted data"/"coin toss" labels overlap; "shaded: 95% range" under the toolbar; empty right half of Panel C says nothing (write "no curve fitted").
- [ ] **C2. Biomarkers timeline:** legend over the title in Multimodal colouring (use the line count to set the top margin, per skill `bravo-timeline-layout`); pain-split histogram "64.0 (67th pct)" half clipped; timeline and calibration scatter do not fill their cards.
- [ ] **C3. Stim Optimizer:** "Analyse at" dot strip cut at the right edge (missing the 30 tick); rotated "safe ceiling 4.5 mA" label clipped on all pain maps; pooled 55/165 Hz maps one flat colour (check the colour scale range).
- [ ] **C4. Closed-Loop values wrap badly ("0.53 (0.39-" / "0.66)"):** non-breaking range.

## D. House style (rule 15) leftovers

- [ ] **D1. Dropdowns without the blue outline:** Biomarkers checks "Sensing pair" and "Pain score" (plus thinner "Median split"); Stim Optimizer visit-date field (only if rule covers dates; ask the PI); Closed-Loop dropdown text is 12 px, not 14.
- [ ] **D2. Titles not short noun phrases** (full lists in the review files): Closed-Loop 8 titles ("What would change this answer, and who can do it", "The sign-off record: ...", etc.); Biomarkers "High vs Low Pain Logistic classification", "Background"; Stim Optimizer "From the clinic testing sheets (...)", "Exploratory ladder for the pair the readiness check prefers", "Home programming schedule to map the two currents", sub-labels "Hold per step, why", "Analyse at, the harmonics", "Record from, why".
- [ ] **D3. Fold labels flip when opened** ("Hide ..."), 45 bare "Hide" buttons on Stim Optimizer, a repeated heading under the Checks fold. Keep the title, flip only the arrow.
- [ ] **D4. Code names and jargon on screen:** `stim1_openloop.clinician_override`, `within_visit.PRE_CHANGE_WINDOW_S`, `ZERO_THREE_LEFT`, `left_leg_vas`, decision/open-item numbers, "A610 p. 35", a repo path, "era", "gate", "youden", "BCa", "floor" (banned), raw ISO times, raw floats (0.45738925624915433, p 5.77e-1). Move to a hover or round; "era"/"floor" per HOUSE_RULES table.
- [ ] **D5. Biomarkers stat block above the detail plot is 5 lines; rule 15 says one line.** Ask the PI: the TD/PSD lines were requested on separate lines (2026-10-02), so confirm which wins.
- [ ] **D6. Date formats differ on the Stim page (3 styles).** Pick one.
- [ ] **D7. Stim Optimizer pain maps use ~170 of 600 px; page scrolls 12-19k px open.** Lower priority layout.

## E. To confirm with the PI

- E1. The Titration session card was not found on the Stim Optimizer page. Is it on the Closed-Loop page or on no page (the review found no text with "titration" on either Stim or the 7 folds opened on Closed-Loop)? If it is on no page, say so in the decision log; I have just condensed its text (decision 385) without being able to see it.
- E2. Agents were not able to test plot zoom on Stim Optimizer, nor "Use this band" (writes to the server, deliberately not clicked) or Make Google sheet.
- E3. Re-run the reviews one page at a time after B2 so contention does not hide or create failures.

## Suggested order
A8, A1+A2, A3-A7, B1, A9-A14, B2-B6, C, D. Tests first for A and B (regression test named for the real defect).
