# Wave 2 design (Plan agent, 2026-10-18; read-only design)

PI rulings that override the questions at the end: see `snr_2026-10-18.md` (correction family: allowed pairs L 1-3 and R 0-3, current pain score only; PSD-only shown, cannot choose; rolling 70/30 cut, date printed; the chronic log may choose).

# Plan: four approved Biomarkers changes, in nine commits (one change per commit)

I made no edits. Each commit is checked against the one before it. Most commits add a setting that puts the old behaviour back (the "neutral setting"). That makes every proof attributable: with the neutral setting on, every field matches the "before" capture; with the default, only the fields named for that commit differ.

## How each commit is proved

- Write a capture script in `BRAVO/_agent_bridge/` and run it through the bridge on RCS08 with the saved-answers store switched off.
- Capture, before and after each commit:
  1. the heat-map grid for all six pain scores at the default settings;
  2. the deployment summary for every band `all_band_requests.py` registers;
  3. the Closed-Loop report for the band ticked on each side;
  4. the Stim Optimizer's response.
- Report the field count and the difference count, and sort every difference into store labels, timings, or that commit's named fields. Never use a tolerance. Then run both test suites in full, the page tests, the build, and an `rg` of the built chunks for each new page string.
- Where a neutral setting must give 0 differences, it has to skip the new code path entirely, not run it with a harmless value. Floating-point arithmetic can move the last digit, and a tolerance is not allowed.

## Commit order

**C1. The verdict reads the rotation p (change 4, first part).**
- In `bravo_service.py::_band_decide_verdict` (line 5294), replace `p = g.get("p")` with `(g.get("rotation") or {}).get("p")`. If the rotation test is unavailable, the band gets "candidate (rotation test unavailable)", never a pass (decision 9). Add `VERDICT_P_SOURCE = "rotation"`; `"glmer"` is the neutral setting.
- Rewrite the docstring and the `validated` gate label at line 7825 ("Band validated (mixed-effects)" becomes "Band validated (rotation test)").
- Tests (`Biomarkers/tests/test_band_rotation_in_model.py`):
  - glmer p 0.01 with rotation p 0.2 gives "candidate";
  - glmer p 0.2 with rotation p 0.01 gives "VALIDATED";
  - a missing rotation test never gives "VALIDATED";
  - the neutral setting gives the old answer.
- Saved answers: no grid kind changes. The deployment summary and band panels miss automatically, because their key includes the code fingerprint (`_serve_saved_band_answer`).
- Proof: the "before" summary already carries `p_rotation`, so the new verdict for every band can be predicted offline. Predicted against actual must give 0 differences. Only `verdict`, the `validated` gate, `ready_to_program` and the pass counts may differ.

**C2. The current is read at the recording (change 1, first part).**
- `availability.py` (the matcher around 1990–2107) records the times of each report's own pieces in a new list, `info["recording_times_s"]`. These are the TD pieces it owns, or the PSD snapshots when there are no TD pieces.
- Add `stim_current.current_at_recordings(times_lists, stream, hemisphere)`. It takes the median of the current in force at each piece, and counts reports whose pieces span two currents.
- `bravo_service._band_time_sweep_channels._prepare` (lines 8431–8434) switches to it. Rewrite `stim_current.py` lines 20–23 ("not the current the band power was measured under"). Add `CURRENT_READ_AT = "recording"`; `"report"` is the neutral setting.
- The deployment summary already reads the current at each sample (`deployment_current.py`), so it does not change.
- Tests:
  - a report whose window straddles a settings change takes the current at its pieces, not the current at the rating;
  - the span counter is right;
  - the PSD-only route uses the snapshot times.
- Saved answers: `GRID_RULE_VERSION` becomes v28; `band_results_tables.RULE_VERSION` becomes v2.
- Proof: with the switch on, the plain fields show 0 differences and the adjusted fields differ. Changed columns must be predicted exactly by the reports whose two currents differ.

**C3. The current-removed result can refuse a band (change 1, second part; reverses decisions 233 answer 2, 234, 242, 243 and 293).**
- The switch at `sweep_settings.py:279-286` stops deciding whether the adjusted grid is built: it is always built. The switch leaves the store key. Every grid sidecar now says `adjust_for_stim_current: True`, so `adapter.stored_current_adjusted_grid` (which the Stim Optimizer reads) keeps working unchanged.
- In `analytics._best_rows_correlation`, for the chosen cell, add a `current_removed_check` with: the partial r; its block-resampled interval (same method as the headline interval); and a rotation p. For the rotation p, take the straight-line fit on the current out of both band power and pain (`stats_utils._residualize`), then rotate the pain remainder.
- The row's `answer` can be "established" only if the check passes. The check fails when the interval is not wholly the same sign as the plain r, or p > 0.05. A constant current passes, with that stated. No settings stream means "not assessed", which blocks (decision 9).
- Sign-off:
  - pass the current at each sample (from `deployment_current`) as a second column of `X0` to `MS.null_fit_lme4` (`band_mixedmodel_inference`, line 4813);
  - add a gate `current_removed` (necessary), short label "Holds with current removed", in `DEPLOYMENT_GATE_SHORT_LABELS`;
  - `_summary_auc_current_removed` stays descriptive;
  - `CURRENT_REMOVED_REFUSES = False` is the neutral setting.
- Tests:
  - a made-up band that follows the current alone loses its pass;
  - a band genuinely linked to pain keeps it;
  - a constant current passes;
  - a missing stream blocks;
  - the rotation with the current as a covariate matches a written-out version.
- Saved answers: grid v29; band tables v3. The summary misses through the code fingerprint.
- Proof: the numbers from C2 are unchanged; only the new fields, `answer`, the gates and `ready_to_program` differ.

**C4. TD and PSD values kept apart (change 5, first part).**
- `_band_time_sweep_power_by_seconds` builds two more matrices: TD only (PSD fill switched off) and PSD only (every report with a PSD in its window, ignoring TD). `band_time_sweep_from_power` runs on each, each with its own shuffles and best rows, under `by_source_grid: {td, psd}`.
- The existing mixed grid keeps its fields so the proof is clean, but nothing chooses a band from it any more. It becomes "TD, PSD where no TD".
- `_correlation_by_recording_source` (line 6137) is superseded; keep it until C9, then delete it on the PI's word (rule §6).
- Tests: the TD grid has no PSD-flagged report and the PSD grid has none from TD; for each cell, the two counts add up to the mixed cell's count.
- Saved answers: grid v30; band tables v4.
- Proof: old fields show 0 differences; only new fields appear. Time a grid build before and after in alternating rounds; expect about 3 times the shuffle work.

**C5. The chronic log as the main source (change 5, second part).**
- Add `routines/chronic_band_choice.py` (no Django). It reads `representation.native_lsb_by_channel`, chronic source only, on the chronic record's own contact pair (decision 461).
- For each (pair, chronic sensing frequency) it matches each report to the median chronic reading within the 15-minute window. It then gives the r, its interval, the rotation p and the C3 current check, using the current at the chronic samples' times.
- Each chronic frequency is mapped to the nearest grid centre (for example 24.41 Hz to 24.5 Hz), requiring less than 0.5 Hz apart.
- On each grid row, add `chronic: {covered, n_reports, ...}`, plus a band-choice field `choice_source`:
  - "chronic" where the chronic log covers the band;
  - else "TD";
  - PSD-only rows are labelled and cannot choose until the PI rules (see the questions below).
- Bands with no chronic coverage are labelled "no home record at this band".
- Add the chronic recordings' identity to `_band_sweep_signature`.
- Tests:
  - frequency to grid-centre mapping;
  - samples on another pair never count (rule 13);
  - a band the chronic log does not cover cannot be labelled chronic;
  - when the chronic and TD answers disagree, chronic wins.
- Saved answers: grid v31; band tables v5.

**C6. Hour-of-day block in band choice (change 2, first part; departs from §7.13).**
- Add `sweep_settings.HOUR_BLOCK_HOURS`. Step 0 measures it before any code: on the chronic log, compute the hourly median profile per (pair, frequency), and for widths 3, 4, 6 and 8 hours report the largest within-block high-to-low ratio and the ratings per block. Choose the widest width whose within-block ratio is at most 1.25. I expect 6 hours.
- In `band_time_sweep_from_power`, add `time_block=`:
  - subtract the block mean of band power within each block, on raw power (never log power, decision 202), for both grids;
  - subtract the block mean of pain only for the correlation grid, so "high pain" keeps its meaning in the AUC split;
  - add `stats_utils.stratified_rotations(blocks, rng)`: one shift k = 1..N_max−1, each block's pain rotated by k mod its size, so ratings move only within their block. `_best_of_windows_null_*` uses it.
- The same blocks apply in C5's chronic rows and in the sign-off's rotation (rotate within block, using `order=`).
- A 24-hour width (one block) skips the code path entirely; this is the neutral setting.
- Tests:
  - a made-up band whose power follows the clock, against pain given at habitual hours, reads p ≤ 0.05 in about 5% of records with blocks, against far more without;
  - one block reproduces the old grid exactly;
  - a block with one report contributes nothing, and is counted.
- Saved answers: grid v32; band tables v6.

**C7. Thresholds from the home chronic-log spread (change 2, second part).**
- `threshold_placement.median_level` is centred on the chronic-log median for the band's pair and frequency, instead of the median of the 3 s clinic pieces.
- `design_rule.false_crossing_rate` (line 784) and `min_separation_for_rate` (line 844) take `level_profile`: the chronic hourly-block medians laid along 24 hours. The level then follows the measured daily swing instead of being fixed. The fast wobble is still fitted on the 3 s pieces. Each row also reports, per block, the share of time spent above, between and below the thresholds.
- With no chronic coverage, the old method runs, labelled "clinic recording only".
- `THRESHOLD_SPREAD_SOURCE = "tiles"` is the neutral setting.
- Tests:
  - a flat profile reproduces today's table exactly;
  - a daily swing larger than the separation gives "never" for that row;
  - the label is right when chronic coverage is absent.
- Saved answers: `design_rule.RULE_VERSION` becomes v3 (band onset keys follow, because they include it); `threshold_placement.RULE_VERSION` becomes v2. Check with `rg` that the simulation's key includes the threshold values; if not, bump its version.

**C8. Choose on the first 70%, test on the last 30% (change 4, second part).**
- Add `routines/time_split.py`: `choice_cut(report_times_s, share=0.70)` returns the time of the report at the 70% mark, ordered by time, on the same pain series the grid and the sign-off both build (after the clinic-sheet merge). One cut is shared by all pairs and both pages.
- Grid: compute every choice statistic with the last 30% of pain values set to missing; the machinery already skips missing values. Each best row gains `held_out`: r at the chosen length on the last 30%, its interval and its rotation p.
- "Established" also needs the held-out check to pass: same sign, p ≤ 0.05.
- Sign-off: `band_mixedmodel_inference` and the rotation test run on the last 30% only. `deployment_forward_chaining` scores only folds whose test week starts after the cut. The ROC and the threshold percentile stay on all the data.
- Today the grid chooses on all the data, and the forward check (line 1885) refits only direction and cut-point inside each fold. So weeks used to choose the band are later used to test it.
- `share=1.0` skips the code path; this is the neutral setting.
- Tests:
  - no last-30% rating reaches any value used to choose (shuffle them and the choice is unchanged);
  - the cut is the same on both pages;
  - a band planted only in the first 70% fails the held-out check.
- Saved answers: grid v33; band tables v7. The stability grid keeps all the data, so its version stays the same.

**C9. Correction across contact pairs, sides and pain measures (change 4, third part).**
- Add `routines/family_correction.py`: Benjamini–Hochberg over every (pair, side, measure, source) choice p from the stored grids under the same settings and rule. It is attached when a grid is read, not stored, the way stability answers are (decision 185). The Biomarkers grid response and `adapter.band_sweep_grid_for_closed_loop` both call it.
- It prints "corrected across N of M built". `family_wise_q_8_to_30hz` stays, renamed on screen to "fdr 22 bands".
- Tests:
  - the family size counts only what was built;
  - a missing measure lowers N and does not fabricate p values;
  - the q values match a written-out BH.
- Saved answers: no grid bump; band tables v8 (they gain the field).

## Page changes (`Client/src`; rebuild after each commit)

- `ClosedLoopSim/DeploySignoffCard.js`, Evidence block (lines 509–533):
  - add "Decides: p from shifting ratings";
  - new rows "Holds with current removed", "Later 30% of ratings" and "Thresholds from home record";
  - the forward line becomes "Later weeks, after the cut".
- `ClosedLoopSim/BandCandidateIdentity.js` (lines 132–136): mark which p decides.
- `ClosedLoopSim/BandSweepGridPanel.js`: new columns Source, Current out and Later 30%; `FamilyWiseMark` and the footnote at line 581 change from "corrected for 22 bands" to "corrected across N tests".
- `Biomarkers/gridReadouts.js`: `qWords` and the header comment; `correctionCounts`; a source caption replaces the mixed-source wording at line 321.
- `Biomarkers/BiomarkerHeatmapGrids.js`: TD and PSD heat maps side by side; chronic marks on covered columns; the caption states the 70% cut date and the hour block.
- Update the page tests' fixtures; each new string is pinned by a render test.

## Questions for the PI before coding

1. **Correction may make passing impossible.** With 12 pairs × 22 centres × 6 measures × 3 sources (about 4,750 tests), and the smallest possible p about 1/270 on the 70% choice set, BH would need about 260 cells at that smallest p before any band clears. Recommendation: the family is the pairs the sensing-pair rule allows (L 1-3, R 0-3); measure this live first. Also needed: is the new q a label (decision 63) or a check that can refuse?
2. **Rolling or frozen 70% cut.** A rolling cut lets each new rating move it, and the chosen band can change from one day to the next. Recommendation: rolling, with the cut date printed.
3. **No settings stream blocks every band** (decision 9) for any participant without one.
4. **Which shape removes the current.** A straight line, as decisions 241 and 242 use for every published adjusted number, or the spline?
5. **May PSD-only rows choose?** Patient-event PSDs are recorded at pain moments.
6. **The daily swing may refuse every threshold.** A 2–6.7-fold swing could make C7 answer "never" at every timing. Decision 180's placement would then fall back to D24.
7. **Where §7.13 is departed from.** Hour-of-day enters band choice as fixed blocks (centring and stratified rotation), and the daily profile enters the threshold simulation. Calendar drift (decisions 193–196) and any fitted time trend stay out. CLAUDE.md §7.13 and Part 1 line 17 need rewording.
8. **The Stim Optimizer's readiness rule moves.** It reads the grid's "supported" answer (decision 199), so C3, C6 and C8 move its result too.
9. **Clinic chooses, home confirms (§10).** Choosing from the chronic log uses ratings filed at home to choose a band.
10. **Execution authority (§7.8).** Confirm that "do all" covers this plan as written.

## Why I made each design choice

- **Commit order.** C1 changes only a verdict. Changes that add fields come before changes that move every number. The split and the correction come last, so their family covers every test.
- **Neutral setting per commit.** It gives the 0-difference control that makes each proof attributable.
- **Current = median over the report's own pieces.** That is the current the averaged power was measured under.
- **Pain is not centred for the AUC.** Its high/low split keeps a fixed meaning.
- **A shared shift for the stratified rotation.** It is exact, enumerable and fast.
- **The 70% cut is a count of reports.** That keeps the test set's size predictable.
- **The correction is attached when read.** The family spans stored grids, and attaching it changes no key.

### Critical files for implementation
- /media/volume/pnlstore/BRAVO_pain/BRAVO/modules/Biomarkers/routines/analytics.py
- /media/volume/pnlstore/BRAVO_pain/BRAVO/modules/Biomarkers/bravo_service.py
- /media/volume/pnlstore/BRAVO_pain/BRAVO/modules/Biomarkers/routines/availability.py
- /media/volume/pnlstore/BRAVO_pain/BRAVO/modules/Biomarkers/routines/sweep_settings.py
- /media/volume/pnlstore/BRAVO_pain/BRAVO/modules/ClosedLoopDeployment/design_rule.py