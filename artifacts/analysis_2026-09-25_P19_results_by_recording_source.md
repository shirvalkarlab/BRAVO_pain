# P-19: the band-to-pain correlation, split by recording source

2026-09-25. RCS08. Read-only. Nothing was written to the saved answers on disk. The page's saved heat-map grid was bypassed, so every number below was worked out from scratch. The two background jobs the page normally starts were switched off for the run. No source file of the platform was changed.

## What was asked
Handoff item P-19 asked whether recordings the patient triggered (made because something happened) create a false pain signal. The check is to split the result by where each band-power number came from. No page splits a result that way today.

## Where this sits on the pages today
- **Biomarkers page, the two heat maps at the bottom** ("band by length of signal"). Each cell is the correlation between band power and the chosen pain score across pain reports. Each pain report gets its band power from ONE of two sources:
  1. **The voltage trace.** This is the device's 250-samples-per-second recording of the brain signal. It is cut into 3-second chunks and turned into the device's band-power units with the transform constant. It is used whenever any trace falls inside the match window (60 minutes by default).
  2. **The device's FFT snapshots.** These are the 30-second frequency snapshots the device stores when the patient presses the event button. They are turned into the same units with the composed bridge constant. They are used only for a report with no trace in its window.
- The page already COUNTS the snapshot-read reports. The caption under each heat map says how many matched reports "were read from the device's 30 s FFT snapshots" (decision 106). The page never shows the correlation from each source on its own.
- **The device's own band power** is the number the device itself computes at one band centre: every 10 minutes in its chronic log, and twice a second while streaming. It is the quantity a closed-loop threshold acts on. It enters no heat map and no correlation on any page.

## How it was measured
- **Settings:** the daily defaults. That means NRS, a 60-minute match window, each chunk used once for its nearest report, a tertile split, clinic-sheet ratings off and no current adjustment. 777 NRS reports were handed in.
- **Method:** the page's own code built the grid. The probe captured its inputs, then re-ran the page's own matching and statistics with one source removed at a time. As a check, the page's own grid rebuilt this way came back identical: 22 band rows per pair, 0 fields differing, on both pairs.
- **The correlation:** Pearson on raw band power at 30 s of signal. One snapshot covers 30 s, so this is the length at which the two sources are like for like.
- **The interval:** the page's own 95% interval, which resamples whole pain reports in runs of neighbouring reports.
- **Outliers:** the page's own rule, which on these two pairs is the per-chunk ceiling table.
- **The device's own band power:**
  - For the chronic log: the nearest reading within 60 min of each report, on the named contacts only.
  - While streaming: the median of the nearest 30 s within 60 min.
  - Readings are grouped by the band centre in force.
  - The page's 5-MAD outlier rule was applied.
  - Unlike the grid, one reading may serve two nearby reports.

## The short answer
- **Left, L 1-3+.** Both sources show band power falling as pain rises, most strongly at 8.5-18.5 Hz.
  - The trace reads stronger: -0.47 to -0.61 (76 reports). The snapshots read -0.16 to -0.39 (135-137 reports).
  - At **23.5-28.5 Hz**, where the closed-loop candidate band sits, the two parts of the page's own cell disagree. The snapshot-read reports read -0.35 to -0.37, every interval wholly below zero (86 reports). The trace-read reports read -0.05 to -0.17, every interval spanning zero (76 reports).
  - The page's cell reads -0.04 to -0.12 there, near zero.
- **Right, R 0-3+.** The page's negative correlations come from different sources in different bands.
  - At 8.5-18.5 Hz they come mainly from the trace: -0.22 to -0.38 (87 reports). The snapshots alone read -0.07 to +0.01 (275 reports).
  - At 19.5-24.5 Hz they come mainly from the snapshot-read reports: -0.16 to -0.31 (221 reports). The trace reads -0.18 to +0.01.
  - On the 54 reports that have both sources, the two point in OPPOSITE directions at 8.5-20.5 Hz: trace -0.05 to -0.26, snapshots +0.08 to +0.26. The interval on the difference excludes zero in all 13 of those bands.
- **No source creates a band that rises with pain on either pair.**
  - On the page's own split (2 pairs x 2 sources x 22 bands = 88 readings), every reading is negative or has an interval spanning zero.
  - The only intervals wholly above zero are two:
    - The snapshots on the 54 shared right reports at 9.5 and 10.5 Hz (+0.22, +0.25), with 12.5 Hz touching zero.
    - The device's chronic reading at 8.79 Hz on the right: +0.34, 19 reports. It does not clear the shuffled level.
- **Mixing the two sources does not create the page's correlations.** The check removes each source's own average from band power and pain before correlating.
  - On the right, the result is within 0.02 of the page's value at every band.
  - On the left, it is within 0.04 at 8.5-15.5 Hz.
  - Higher on the left, the page's pooled value is WEAKER than inside each source: by 0.04-0.06 at 16.5-19.5 Hz and by 0.08-0.14 at 20.5-29.5 Hz. At 24.5 Hz it is -0.04 pooled against -0.16 with the source averages removed.
- **The device's own band power shows no relationship with pain** at its best-covered centres:
  - Left chronic, 23.44 Hz: +0.00 (-0.25 to +0.26), 63 reports.
  - Right chronic, 26.37 Hz: -0.04 (-0.22 to +0.14), 117 reports.
  - It shares at most 8 reports with the trace, too few to test agreement on the same reports.
- **Caution on the left disagreement.** An approximate test (Fisher's transformation) of the two groups was run across all 44 band-and-pair comparisons.
  - The smallest uncorrected p is 0.013 (right, 22.5 Hz); left 24.5 Hz is 0.031.
  - None survives correction for having tested 44 comparisons.
  - The test treats neighbouring reports as independent, which makes its p-values too small.
  - This is a lead, not an established difference.

## Results, L 1-3+ (30 s)
Each entry is the correlation, its 95% interval, then the number of reports.
- "Trace alone" is exactly the page's trace-read reports, because the page prefers the trace.
- "Snapshots alone" uses every report with a snapshot, including the 51 that also have a trace.
- "Snapshot-read" means the 86 reports the page actually reads from snapshots.

| Band | Page, both | Trace alone | Snapshots alone | Page's snapshot-read | Source averages removed |
|---|---|---|---|---|---|
| 8.5 | -0.44 (-0.56 to -0.31), 161 | -0.60 (-0.74 to -0.39), 76 | -0.39 (-0.52 to -0.26), 135 | -0.33 (-0.52 to -0.15), 85 | -0.42 (-0.56 to -0.29), 161 |
| 12.5 | -0.43 (-0.56 to -0.30), 161 | -0.57 (-0.72 to -0.32), 76 | -0.30 (-0.45 to -0.16), 136 | -0.36 (-0.55 to -0.19), 85 | -0.43 (-0.56 to -0.29), 161 |
| 16.5 | -0.42 (-0.54 to -0.27), 161 | -0.57 (-0.73 to -0.35), 76 | -0.24 (-0.38 to -0.09), 136 | -0.38 (-0.56 to -0.20), 85 | -0.46 (-0.59 to -0.32), 161 |
| 20.5 | -0.28 (-0.45 to -0.10), 162 | -0.33 (-0.53 to -0.12), 76 | -0.16 (-0.34 to +0.01), 137 | -0.38 (-0.63 to -0.12), 86 | -0.35 (-0.52 to -0.19), 162 |
| 22.5 | -0.14 (-0.28 to -0.00), 162 | -0.19 (-0.39 to +0.01), 76 | -0.07 (-0.21 to +0.04), 137 | -0.34 (-0.58 to -0.13), 86 | -0.25 (-0.39 to -0.09), 162 |
| 23.5 | -0.09 (-0.22 to +0.03), 162 | -0.12 (-0.32 to +0.06), 76 | -0.04 (-0.16 to +0.09), 137 | -0.36 (-0.55 to -0.19), 86 | -0.20 (-0.34 to -0.06), 162 |
| 24.5 | -0.04 (-0.16 to +0.08), 162 | -0.05 (-0.23 to +0.12), 76 | -0.02 (-0.14 to +0.11), 137 | -0.37 (-0.56 to -0.19), 86 | -0.16 (-0.30 to -0.03), 162 |
| 26.5 | -0.04 (-0.17 to +0.09), 162 | -0.06 (-0.27 to +0.13), 76 | -0.03 (-0.16 to +0.10), 137 | -0.35 (-0.52 to -0.20), 86 | -0.17 (-0.31 to -0.04), 162 |
| 28.5 | -0.12 (-0.25 to +0.02), 162 | -0.17 (-0.38 to +0.05), 76 | -0.09 (-0.20 to +0.03), 137 | -0.37 (-0.53 to -0.23), 86 | -0.26 (-0.39 to -0.12), 162 |
| 29.5 | -0.24 (-0.36 to -0.11), 162 | -0.36 (-0.56 to -0.11), 76 | -0.14 (-0.25 to -0.02), 137 | -0.39 (-0.55 to -0.25), 86 | -0.37 (-0.50 to -0.22), 162 |
(All 22 centres are in _p19_by_source.json and _p19_groups.json.)

**Counts.**
- Of 777 reports, 76 have a trace in their window, 137 have a snapshot and 51 have both.
- At 30 s the page reads 162: 76 from the trace and 86 from snapshots, so 53% come from snapshots.
- The trace-read reports fall on 62 California days, the snapshot-read on 66, with 6 days shared.

**Why the left 22.5-28.5 Hz cell sits near zero.** Between the two groups, higher band power goes with higher pain. That offsets the falling relationship inside each group.
- The trace-read reports carry more pain: mean NRS 7.32 against 6.74. The difference (snapshot minus trace) is -0.57, interval -1.14 to -0.04 resampling whole days; rank test p 0.00016.
- They also carry about twice the band power at these centres. Median device units, trace-read against snapshot-read:
  - 24.5 Hz: 227 against 104
  - 26.5 Hz: 205 against 101
  - 28.5 Hz: 155 against 80
  - At 8.5-12.5 Hz the two groups are within 20%.
- The doubling is not the difference between the two conversions. On the 51 reports with both sources:
  - the median snapshot power is 0.82-1.02 times the trace power (0.93 at 24.5 Hz);
  - the two powers rank the reports alike (+0.34 to +0.81).
- The two groups are different occasions (6 shared days of 122). Why the trace-read occasions run higher is not answered here.

**On the 51 reports with both sources:**
- The sources agree in sign at 8.5-26.5 Hz.
- The trace is more negative at 8.5-17.5 Hz: -0.40 to -0.52, against -0.09 to -0.37 for the snapshots.
- The difference's interval excludes zero at 3 of 22 centres only (14.5, 28.5 and 29.5 Hz).

**Best of all nine lengths** (the page's headline rows). "Established" is the page's word: the interval excludes zero AND the value beats what the same best-of-nine choice reaches on shuffled pain scores.
- The page: 16 of 22 centres established, all negative.
- The trace alone: 17.
- The snapshots alone: 9 (8.5-16.5 Hz).

## Results, R 0-3+ (30 s)
| Band | Page, both | Trace alone | Snapshots alone | Page's snapshot-read | Source averages removed |
|---|---|---|---|---|---|
| 8.5 | -0.15 (-0.25 to -0.08), 308 | -0.38 (-0.55 to -0.18), 87 | -0.02 (-0.10 to +0.07), 275 | -0.09 (-0.15 to -0.03), 221 | -0.15 (-0.24 to -0.08), 308 |
| 12.5 | -0.16 (-0.26 to -0.08), 307 | -0.28 (-0.46 to -0.04), 87 | +0.01 (-0.08 to +0.10), 274 | -0.10 (-0.20 to -0.03), 220 | -0.15 (-0.24 to -0.07), 307 |
| 16.5 | -0.23 (-0.33 to -0.13), 307 | -0.32 (-0.50 to -0.13), 87 | -0.05 (-0.16 to +0.04), 274 | -0.18 (-0.31 to -0.07), 220 | -0.22 (-0.33 to -0.13), 307 |
| 20.5 | -0.21 (-0.32 to -0.10), 308 | -0.14 (-0.31 to +0.03), 87 | -0.07 (-0.17 to +0.02), 275 | -0.29 (-0.40 to -0.17), 221 | -0.20 (-0.31 to -0.09), 308 |
| 22.5 | -0.14 (-0.26 to -0.04), 308 | +0.01 (-0.15 to +0.16), 87 | -0.09 (-0.19 to +0.01), 275 | -0.30 (-0.44 to -0.15), 221 | -0.13 (-0.24 to -0.01), 308 |
| 24.5 | -0.19 (-0.30 to -0.08), 308 | -0.11 (-0.31 to +0.14), 87 | -0.13 (-0.24 to -0.03), 275 | -0.25 (-0.35 to -0.13), 221 | -0.18 (-0.29 to -0.07), 308 |
| 26.5 | -0.09 (-0.20 to +0.02), 306 | -0.20 (-0.36 to +0.08), 87 | -0.07 (-0.18 to +0.03), 273 | -0.04 (-0.15 to +0.06), 219 | -0.09 (-0.19 to +0.02), 306 |

**Counts.**
- 87 reports have a trace in their window, 275 a snapshot and 54 both.
- At 30 s the page reads 308: 87 from the trace and 221 from snapshots, so 72% come from snapshots.
- Days: 70 trace-read, 134 snapshot-read, 8 shared.
- Pain does not differ between the groups: NRS 7.05 against 7.25 (+0.21, -0.21 to +0.64; p 0.24). It is less spread on the snapshot-read reports (SD 0.97 against 1.85).
- Upper-band power is again higher on the trace-read reports: 124 against 66 at 24.5 Hz. The same-report ratio is 0.84-1.02.

**On the 54 reports with both sources:**
| Band | Trace | Snapshots | Difference (trace minus snapshots) |
|---|---|---|---|
| 8.5 | -0.26 (-0.58 to +0.14) | +0.19 (-0.03 to +0.35) | -0.45 (-0.76 to -0.06) |
| 10.5 | -0.11 (-0.44 to +0.18) | +0.25 (+0.05 to +0.42) | -0.36 (-0.70 to -0.08) |
| 15.5 | -0.23 (-0.45 to -0.02) | +0.19 (-0.09 to +0.38) | -0.42 (-0.63 to -0.19) |
| 20.5 | -0.07 (-0.30 to +0.10) | +0.08 (-0.15 to +0.30) | -0.15 (-0.36 to -0.00) |
| 24.5 | -0.18 (-0.52 to +0.21) | +0.01 (-0.30 to +0.27) | -0.19 (-0.35 to +0.05) |
- The difference's interval excludes zero at 8.5-20.5 Hz (13 of 13 bands), and at 27.5-29.5 Hz by a small 0.06.
- These intervals are uncorrected, and neighbouring bands are not independent, so this is one effect across the lower bands.
- The two powers rank these reports alike only moderately: +0.41 to +0.75.
- A snapshot and a chunk of trace are different minutes, up to an hour apart. So this cannot separate a measurement difference from a change in the brain within the hour.

**Best of nine lengths:**
- The page: 16 of 22 established, all negative.
- The trace alone: 10.
- The snapshots alone: 0.

## The device's own band power
Readings after implant on these pairs:
- Left chronic log: 10,446 on contacts 1-3. Left streaming: 44,833 samples.
- Right chronic log: 27,274 on contacts 0-3. Right streaming: 237,494 samples.

Correlations with NRS:
- **L 1-3+:**
  - Chronic 23.44 Hz: +0.00 (-0.25 to +0.26), 63 reports.
  - Chronic 7.81 Hz: -0.29 (-0.69 to +0.17), 21 reports.
  - Chronic 10.74 Hz: -0.72 (-0.91 to -0.52), 12 reports.
  - Streaming 23.4 Hz: -0.21 (-0.65 to +0.32), 15 reports.
- **R 0-3+:**
  - Chronic 26.37 Hz: -0.04 (-0.22 to +0.14), 117 reports.
  - Chronic 7.81 Hz: -0.02 (-0.22 to +0.21), 64 reports.
  - Chronic 8.79 Hz: +0.34 (+0.11 to +0.56), 19 reports. It does not clear the shuffled level.
  - Chronic 9.77, 10.74 and 11.72 Hz: +0.07, -0.08 and +0.01 (25, 33 and 24 reports), every interval spanning zero.
  - Streaming 7.8 and 26.4 Hz: -0.19 and -0.10 (16 and 13 reports), both spanning zero.

What these readings say:
- **The device's own quantity near the closed-loop candidate band (L 1-3+ at 23.44 Hz) shows no relationship with NRS.** The trace at 23.5 Hz reads -0.12 (-0.32 to +0.06). Only the snapshot-read reports resolve one (-0.36).
- **Same reports:** the chronic log shares at most 8 reports with the trace on either pair. Against the snapshots:
  - left, 36 reports at 23.5 Hz: device -0.02, snapshots +0.06, difference -0.08 (-0.50 to +0.32);
  - right, 43 reports at 26.5 Hz: device +0.16, snapshots -0.05, difference +0.20 (-0.08 to +0.47).
  - No disagreement is detectable.
- **Streaming against the trace:** the device's band power and the trace-derived band power rank the same reports closely:
  - +0.77 on 11 left reports at 23.4 Hz;
  - +0.92 and +0.63 on 12 right reports at 7.8 and 26.4 Hz.

## Do the sources agree?
- **Direction:** yes, almost everywhere. Every trace reading and every page-split snapshot reading with an interval excluding zero is negative. The exception is the 54 right reports with both sources, where the snapshots read positive at 8.5-20.5 Hz.
- **Size:** no.
  - On the left, the trace is 0.2-0.4 more negative than the snapshots alone at 8.5-17.5 Hz.
  - At 23.5-28.5 Hz on the left, the snapshot-read reports carry a relationship (-0.35 to -0.37) that the trace does not (-0.05 to -0.17).
  - On the right, the trace carries the lower bands and the snapshot-read reports carry 19.5-24.5 Hz.
- **Calibration:** yes. On the same reports the two conversions agree within a factor of 0.82-1.02.
- **Device's own power:** too little overlap to test. On its own it shows no relationship at its best-covered centres.
- **Did the patient-triggered recordings create a false pain signal?** Not a rising one.
  - No source gives a band that rises with pain on either pair. The one-band rule's pain leg (decision 210) is unmet from every source, as decision 217 found for the pooled grid.
  - The snapshots do shape the falling signal. On the right, the page's 19.5-24.5 Hz readings rest mainly on them. On the left, the snapshot-read reports carry a 23.5-28.5 Hz relationship that the pooled cell hides.

## Limits
- One participant, NRS only, the 60-minute window only. Other scores, windows and the clinic-sheet switch were not run.
- The page's two groups are different occasions (6 and 8 shared days). A difference between them can be the source, the occasion or both.
- The two-group test is approximate, treats reports as independent and is uncorrected. Nothing survives correction for the 44 comparisons.
- A device reading may serve two nearby reports, which the grid does not allow.
- At 45 and 60 s a snapshot-read report needs two snapshots, so fewer reports qualify.

## Should a page show the split?
**Recommended: yes, descriptively, in two places. The split should never select a band or change a verdict. The PI decides.**

1. **Biomarkers heat-map cell side panel (the drill-down with the scatter and violin).** For the selected cell, print the correlation from the trace-read reports and from the snapshot-read reports, each with its count and interval. Draw the two kinds of point differently, as clinic-sheet points are already drawn hollow (decision 228). The reasons:
   - Snapshots answer 53% (left) and 72% (right) of the reports behind a 30-second cell on the two pairs the device allows.
   - At left 23.5-28.5 Hz the two parts disagree (-0.35 to -0.37 against -0.05 to -0.17) while the cell reads -0.04 to -0.12.
   - On the right, which part carries the cell changes with the band.
   - The page already computes which reports are snapshot-read (`from_device_spectrum`), so no new matching is needed.
2. **Closed-Loop page, beside the chosen band.** Show the device's own band power against pain where the chronic log holds the band (L 1-3+ 23.44 Hz: +0.00, -0.25 to +0.26, 63 reports). Label it as the quantity the device's threshold acts on. It is on no page today.

**Not recommended:**
- A separate heat map per source. It doubles the grid, and the snapshot grid is constant below 30 s.
- Letting either source choose a band or move a verdict. The left disagreement does not survive correction, so the split is a caution beside the number.

========== END OF DOCUMENT TEXT ==========

DRAFT DECISION ROW:
2XX. Results split by recording source, P-19 (read-only, 2026-09-25; no code changed).
- **Method.** On RCS08 at the daily defaults (NRS, 60 min, 777 reports), the heat-map correlation at 30 s was rebuilt three ways: from the voltage trace alone, from the device's FFT snapshots alone, and from the device's own band power. The page's own matching and statistics were used; the page's grid came back with 0 of its row fields differing.
- **Coverage.** Snapshots answer 86 of 162 left reports and 221 of 308 right reports.
- **No source gives a band that rises with pain on either pair.**
- **Left, L 1-3+.**
  - Both sources fall with pain at 8.5-18.5 Hz: trace -0.47 to -0.61 (76 reports), snapshots -0.16 to -0.39 (135-137).
  - At 23.5-28.5 Hz the snapshot-read reports read -0.35 to -0.37 (intervals below zero, 86) and the trace-read -0.05 to -0.17 (spanning zero, 76). The page's cell reads -0.04 to -0.12.
  - The trace-read reports carry more pain (NRS 7.32 against 6.74, difference -0.57, -1.14 to -0.04) and about twice the band power there (24.5 Hz: 227 against 104).
  - On the 51 reports with both sources, the two conversions agree within 0.82-1.02.
- **Right, R 0-3+.**
  - The trace carries 8.5-18.5 Hz (-0.22 to -0.38, 87 reports); the snapshot-read reports carry 19.5-24.5 Hz (-0.16 to -0.31, 221).
  - On the 54 reports with both, the two point opposite ways at 8.5-20.5 Hz; the difference's interval excludes zero at all 13 of those bands (uncorrected).
- **Mixing does not create the correlations.** With each source's average removed, the page's correlation moves by at most 0.02 on the right and by at most 0.04 on the left at 8.5-15.5 Hz. At 20.5-29.5 Hz on the left the pooled value is 0.08-0.14 weaker than inside the sources (24.5 Hz: -0.04 against -0.16).
- **The device's own chronic band power shows no relationship with pain:** left 23.44 Hz +0.00 (-0.25 to +0.26, 63 reports); right 26.37 Hz -0.04 (-0.22 to +0.14, 117).
- **No two-group difference survives correction** for 44 comparisons (smallest uncorrected p 0.013).
- **Recommended to the PI:** show the split descriptively in the heat-map cell's side panel, and the device's own band power beside the chosen band on the Closed-Loop page.
- `artifacts/analysis_2026-09-25_P19_results_by_recording_source.md`.
