# What the heat maps would say with the exact chance test

Measured 2026-09-26 on RCS08 (uid `2e3c75c00d7f4f37b53a048d195f11da`) at commit 79ceceef, live through the
bridge. Read-only: nothing was written to the saved answers on disk, and no tracked file changed. It
answers the question left for the PI at the end of decision 314. Nothing here has been switched.

## The question in plain words

To judge whether a band's link with pain is more than chance, several parts of the platform shuffle the
pain ratings and recompute the link many times, all with one shared shuffle
(`stats_utils.circular_block_perm_matrix`). When each pain rating resembles its neighbours, that shuffle
cuts the rating series into short chunks and reorders the chunks. On RCS08 today the chunks are **two**
neighbouring ratings long: each pair of neighbours stays together, but pain's slower rises and falls
over weeks and months are thrown away.

The research band detector switched in decision 314 to **sliding the whole pain series along in time**,
once by every possible number of ratings, wrapping the end round to the start ("every slide once"). It
keeps every slow rise and fall of pain and breaks only its alignment with the band. On made-up records,
decision 314 found that the chunk shuffle makes p too small when both the band and pain drift slowly.
This document measures what switching would do on the pages.

## The short answer

- **Only the correlation grid on the Biomarkers heat maps moves, and it moves a lot.** Its chance test
  uses two-rating chunks today. The area-under-the-curve grid is sorted into high- and low-pain labels,
  which gives a chunk length of 1, so its test already slides the series; switching changes only the
  random draw.
- **Daily defaults (NRS):** bands whose best cell clears the correction for testing 22 bands (q below
  0.05) fall from **32 to 10**, all falling with pain. **R 0⁻3⁺: all 14 lose it. L 1⁻3⁺: 16 become 10.**
- **The Biomarkers page's current settings** (Left Leg VAS, 5-minute window, median split, clinic sheets
  on): **34 to 17**. The one band rising with pain that cleared it, R 0⁻3⁺ 9.5 Hz, loses it; the other 16
  that lose it all fall with pain.
- **The one-band rule does not move: 0 of 50 usable before and after.** Its pain leg (decision 210) uses
  the resampled interval, which does not use the shuffle and is identical to the last digit. No band that
  rises with pain on the daily grid is "established" before or after, so the Stim Optimizer's readiness
  table does not change.
- **The Closed-Loop "Choose a band" card still offers the same 22 bands on every pair.** Only its tick
  changes: under the page's settings, 34 ticks become 17. The tick is a label, not a check that can refuse
  (decision 65).
- **The other users barely move, or reach no page.** The check before any decoder (decision 310) already
  slides the series (chunk length 1 on all 12 readings); its p-values move by at most 0.059 and no sentence
  changes. The power-over-time area-under-the-curve test on the Biomarkers Compute response moves from
  p 0.198 to 0.657; no page reads it.
- **On made-up records built on RCS08's own pain series** (a made-up band unrelated to pain): today's
  shuffle calls it "p ≤ 0.05" in **10.7%** of records (daily NRS) and 8.7% (page settings); every slide
  once, **5.9%** and 5.8%. With the band drifting as slowly as RCS08's band power at 60 s of signal:
  **17.1%** against 7.4%.
- **No extra computing time.** Grid builds, alternating today / slide / today / slide: daily
  7.4 / 7.4 / 8.5 / 7.2 s; page settings 4.7 / 4.6 / 4.4 / 4.5 s.

## 1. How it was measured

- The grid was built fresh through the page's own request (`band_time_sweep_for_participant`): writes to
  the saved answers blocked, the saved grid bypassed, both background jobs stubbed.
- One probe replaced the shared shuffle with a wrapper that **always runs today's shuffle first**, so
  every later step draws exactly the same random numbers (this matters for the resampled intervals), then
  hands back either today's answer or every slide once (`band_detector.rotations`). Nothing else differs.
- Rounds in one process: a warm-up, then today / slide / today / slide.
- Clean-comparison checks: today's test built twice, 43,685 fields in common and 19 differing, all timing
  (same for every slide once); against the grids the page saved at 04:55 UTC, 1,452 of 1,452 compared
  values match on each grid; today against every slide once, 43,685 in common, 0 added, 0 removed, 1,284
  differing (daily) and 1,209 (page), every one a number derived from the shuffle (the p corrected for
  picking the best length, its q, the "clears the correction" flag, the chance level at the 95th and 99th
  percentile, the verdict word, whether the cell beats chance, and sentences quoting them) or timing.
  **No correlation, area under the curve, interval or rating count moved.**

The page's current settings were read from the tag on its own saved grid (written 04:55:01 UTC): Left Leg
VAS, 5-minute match window, median split (33.3 / 66.7), report-first matching, window reuse off,
clinic-sheet ratings on. The pain series the correlation grid shuffles has 777 ratings (daily NRS) and
819 (page); lag-1 correlation 0.54 and 0.59; the shared rule turns both into chunks of 2. The function's
own note of 2026-09-02 measured the NRS series at 72 ratings and a chunk length of 1 (a slide test): on
today's larger record the same rule chooses chunks of 2, so the grid switched from sliding to chunk
shuffling as the record grew, without anyone deciding it.

## 2. The heat maps, pair by pair

**Clears q:** band centres (of 22) whose best cell clears the 22-band correction (the white ring on the
heat map, the tick on the Closed-Loop card). **Established:** the grid's verdict word (the resampled
interval clears zero AND the value clears the chance level for the best of nine lengths). **Chance 95th:**
median over the 22 bands of the correlation the shuffled data reach in 95% of shuffles.

### Daily defaults (NRS, 60-minute window, tertile split, sheets off)

| Sensing pair | Correlation: clears q | established | p ≤ 0.05 | chance 95th (median) | largest change in p | Area under the curve: clears q |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 16 → 10 | 17 → 11 | 17 → 11 | 0.180 → 0.320 | 0.307 | 9 → 9 |
| R 0⁻3⁺ | 14 → 0 | 14 → 2 | 14 → 2 | 0.113 → 0.237 | 0.378 | 0 → 0 |
| L 0⁻2⁺ | 2 → 0 | 6 → 2 | 6 → 2 | 0.259 → 0.334 | 0.228 | 0 → 0 |
| L 0⁻3⁺ | 0 → 0 | 3 → 1 | 3 → 1 | 0.261 → 0.339 | 0.187 | 0 → 0 |
| R 0⁻2⁺ | 0 → 0 | 3 → 2 | 3 → 2 | 0.269 → 0.310 | 0.139 | 0 → 0 |
| R 1⁻3⁺ | 0 → 0 | 0 → 0 | 0 → 0 | 0.265 → 0.284 | 0.072 | 0 → 0 |
| **All six** | **32 → 10** (all falling with pain) | **43 → 18** | 43 → 18 | | **0.378** (q: 0.524) | **9 → 9** |

Correlation grid: the p of every one of 132 cells changes; median p 0.015 → 0.329 on R 0⁻3⁺, 0.001 →
0.050 on L 1⁻3⁺. Area-under-the-curve grid: every p changes through the random draw only (largest p
change 0.035, q 0.085); one verdict flips on the draw alone (L 1⁻3⁺ 18.5 Hz, p 0.049 → 0.058, already on
the edge).

### The Biomarkers page's settings (Left Leg VAS, 5 minutes, median split, sheets on)

| Sensing pair | Correlation: clears q | established | p ≤ 0.05 | chance 95th (median) | largest change in p | Area under the curve: clears q |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 15 → 8 | 15 → 13 | 15 → 13 | 0.199 → 0.234 | 0.130 | 0 → 0 |
| R 0⁻3⁺ | 10 → 9 | 14 → 9 | 14 → 9 | 0.138 → 0.198 | 0.315 | 9 → 9 |
| L 0⁻2⁺ | 9 → 0 | 11 → 3 | 11 → 3 | 0.313 → 0.356 | 0.084 | 0 → 0 |
| L 0⁻3⁺, R 0⁻2⁺, R 1⁻3⁺ | 0 → 0 | 0 → 0 | 0 → 0 | 0.29-0.35 → 0.32-0.36 | 0.12 at most | 0 → 0 |
| **All six** | **34 → 17** (1 rising and 33 falling → 17 falling) | **40 → 25** | 40 → 25 | | **0.315** (q: 0.326) | **9 → 9** |

Area under the curve on this grid: largest p change 0.031; no verdict or flag changes.

### Cells that change on the two pairs the device allows (L 1⁻3⁺, R 0⁻3⁺)

Every r (correlation of band power with pain) is negative except R 0⁻3⁺ 9.5 Hz on the page's grid.

**Daily defaults, L 1⁻3⁺** (188-201 ratings):

| Band | r, length | p | q | clears q | verdict |
|---|---|---|---|---|---|
| 18.5 Hz | −0.336, 45 s | 0.002 → 0.033 | 0.003 → 0.067 | yes → no | established → established |
| 19.5 Hz | −0.278, 45 s | 0.002 → 0.127 | 0.003 → 0.216 | yes → no | established → not resolved |
| 20.5 Hz | −0.280, 10 s | 0.003 → 0.138 | 0.005 → 0.216 | yes → no | established → not resolved |
| 21.5 Hz | −0.232, 10 s | 0.009 → 0.237 | 0.012 → 0.326 | yes → no | established → not resolved |
| 27.5 Hz | −0.178, 20 s | 0.042 → 0.337 | 0.054 → 0.398 | no → no | established → not resolved |
| 28.5 Hz | −0.232, 20 s | 0.004 → 0.218 | 0.006 → 0.319 | yes → no | established → not resolved |
| 29.5 Hz | −0.305, 15 s | 0.001 → 0.067 | 0.002 → 0.123 | yes → no | established → not resolved |

Unchanged on this pair: the 10 bands from 8.5 to 17.5 Hz still clear the correction; the 22.5-26.5 Hz
family never cleared it (24.5 Hz: p 0.127 → 0.409).

**Daily defaults, R 0⁻3⁺** (442-465 ratings): all 14 bands that cleared the correction lose it (14.5-25.5,
27.5 and 29.5 Hz; q 0.003-0.046 → 0.363-0.527); twelve also go from "established" to "not resolved";
14.5 Hz (−0.181, p 0.002 → 0.049) and 18.5 Hz (−0.217, p 0.001 → 0.048) stay "established" per band but
no longer clear the 22-band correction; 24.5 Hz r −0.211, p 0.001 → 0.236, q 0.003 → 0.527.

**Page settings, L 1⁻3⁺** (156-174 ratings): 8.5, 10.5, 11.5, 14.5 and 21.5 Hz lose the correction but
stay "established" (p 0.001-0.016 → 0.028-0.046, q 0.008-0.025 → 0.069-0.079); 9.5 Hz (−0.260, p 0.006 →
0.056) and 29.5 Hz (−0.220, p 0.025 → 0.101) lose both.

**Page settings, R 0⁻3⁺** (333-356 ratings): **9.5 Hz, r +0.213 at 60 s**, the one band rising with pain
that cleared the correction anywhere, goes p 0.001 → 0.074, q 0.002 → 0.164, "established" → "not
resolved"; it stays "supported" (its interval lies wholly above zero either way). 25.5-28.5 Hz (r −0.14 to
−0.15 at 1 s) go "established" → "not resolved". 22.5 and 24.5 Hz keep everything (r −0.293, p 0.001 →
0.006-0.007, q 0.002 → 0.017-0.018).

## 3. What does not change

- **The one-band rule: 0 of 50 usable** (the Stim Optimizer reads the daily NRS grid). Bands rising with
  pain with an interval wholly above zero are identical before and after: L 0⁻3⁺ 24.5-27.5 Hz; R 1⁻3⁺
  25.5-28.5 Hz; R 0⁻2⁺ 26.5 and 27.5 Hz; none on L 1⁻3⁺, R 0⁻3⁺ or L 0⁻2⁺. No band both rises with pain
  and is "established", before or after.
- **Every resampled interval** (decision 183), **every correlation, area under the curve and rating count.**
- **The bands the Closed-Loop card offers:** the same 22 per pair.
- **The Closed-Loop sign check** (`direction_consistency`, p ≤ 0.05 on the chosen band's best cell): at
  24.5 Hz under the page's settings, L 1⁻3⁺ p 0.319 → 0.393 (not significant either way), R 0⁻3⁺ 0.001 →
  0.006 (significant either way). A band chosen from the flipped cells in section 2 would change this
  sentence.
- **The stability column:** its checks run on every band regardless of the shuffle, but its answers are
  filed under the grid's key, so a switch that changes the key leaves every row "not tested" until the
  background run rebuilds (decision 246's lesson).

What would go stale: the RCS08 lines in the heat maps' "How to read this" drawer that quote the grid's
"established" cell, and counts from the 252-setting search (decisions 229, 246). Not re-measured here.

## 4. The other users of the shared shuffle

**The check before any decoder** (decision 310; "What the current explains"), rerun with nothing saved.
Today's code reproduces the saved 08:40 UTC run. All 12 readings already use a chunk length of 1; the
only change is 200 random slides with repeats → every slide once (86 to 458). 195 fields in common, 96
differing, all p-values, the shuffled data's median and 95th, and sentences quoting them. Largest change
in p: 0.059 plain (R 1⁻3⁺ 60 s, 0.194 → 0.253), 0.050 with the current taken out. Smallest p over 12:
0.090 → 0.076 plain, 0.184 → 0.193 current taken out; smallest q across 12: 0.333 → 0.339 plain,
0.478 → 0.478 current taken out. No reading beats its own chance level either way.

**The Biomarkers Compute response.** Today's test twice: 325,043 fields, 0 differing. Against every slide
once: 286 differ, 923 removed (the full-spectrum search's list of shuffled values shortens from 1,000 to
77). `auc_block_perm_null` (`summary.powerdomain.auc_perm`, the power-over-time area-under-the-curve test,
read by **no page**, including the Closed-Loop page and the deployment summary): observed 0.556, p
**0.198 → 0.657** (301,851 readings, chunks of 1,374). The full-spectrum search's own shuffle
(`summary.timedomain.perm_p`, no page reads it): p 0.0130 → 0.0128, the same band picked.

## 5. Made-up records at RCS08's own sizes

Each record is a true null (a band with no relationship to pain); one band at one length (not the grid's
best of nine lengths); p by the grid's own formula; today's test with its chosen chunk length and 1,000
draws against every slide once; 2,000 records per line (a rate near 5% is known to about ±1 point).

| | Daily NRS | Page (Left Leg VAS, sheets) |
|---|---|---|
| ratings the grid shuffles | 777 | 819 |
| pain's lag-1 correlation → chunk length | 0.543 → 2 | 0.595 → 2 |
| ratings with a recording at 24.5 Hz (L 1⁻3⁺) | 201 (5 s) | 174 (10 s) |
| band power's lag-1 correlation at that length | 0.434 | 0.367 |
| at 60 s | 0.598 (188 ratings) | 0.524 (156) |

Share with p ≤ 0.05 (p ≤ 0.01 in brackets), today → every slide once:

| Record | Daily NRS | Page settings |
|---|---|---|
| A: both series made up, measured persistence | 7.3% → 5.1% (2.2% → 1.2%) | 7.5% → 4.6% (2.5% → 0.7%) |
| B: RCS08's own pain series and recording pattern; band made up at measured persistence | **10.7% → 5.9%** (3.6% → 1.3%) | **8.7% → 5.8%** (2.9% → 1.2%) |
| B, band as persistent as at 60 s | **17.1% → 7.4%** (6.1% → 1.4%) | 10.4% → 5.5% (3.9% → 1.4%) |
| B, very persistent band (lag-1 0.9) | 41.2% → 9.1% (26.0% → 2.5%) | 20.7% → 3.7% (9.5% → 0.35%) |

On RCS08's own layout, today's test calls an unrelated band significant about twice as often as it
should, worse the more slowly the band drifts. Every slide once comes close to 5% but not exactly (7.4%
and 9.1% with slowly drifting bands under the daily settings), likely because the wrap-round pairing is
always unnatural and RCS08's pain does not hold a steady level.

## 6. Cost

Grid build, alternating (today / slide / today / slide): daily 7.40 / 7.36 / 8.50 / 7.22 s; page
4.65 / 4.56 / 4.44 / 4.53 s. Every slide once uses 776 (daily) and 818 (page) shuffles instead of 1,000,
so the smallest printable p is about 0.0013 instead of 0.0010. Compute request (one round each): 21.1 s
today, 19.6 s slide. Check before any decoder (one round each): 9.7 s and 6.5 s.

## 7. What a switch would involve (not done)

- One shared function, four callers; the band detector already carries the replacement
  (`band_detector.rotations`).
- The grid's rule version moves so saved grids rebuild; every stability answer reads "not tested" until
  its background run finishes under the new key.
- Published numbers resting on the correlation grid's q or its "established" word would need
  re-measuring: decisions 63, 147, 229, 246 and the drawer's RCS08 lines. Decisions 183, 199, 210 and 217
  would not (intervals and the one-band rule's answer unchanged).

Scratch probes (not tracked): `BRAVO/_agent_bridge/_nullcmp_*.py`, outputs in `BRAVO/_agent_bridge/_nullcmp/`.
