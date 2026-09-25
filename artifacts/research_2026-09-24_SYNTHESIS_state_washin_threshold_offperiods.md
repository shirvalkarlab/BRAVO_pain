# Synthesis: same current, different effect; wash-in; tonic current and one threshold; the 0 mA periods

The PI, 2026-09-24. Four literature reports (one agent each, every citation checked against PubMed or
the publisher, with unverifiable ones listed apart) sit beside this file as
`research_2026-09-24_{1,2,3,4}_*.md`, and each describes every paper it cites. This file adds what
the record says and ties the four together. Nothing here changed any code or any stored product.

## 0. The implant date, and a correction

- The device record (`DBSDevice.implanted_date`, the one of RCS08's four Percept RC rows that carries
  it) gives **2025-07-16 18:06 UTC**. Every clinic-session product starts that day: impedance,
  surveys, streamed recordings and montages. REDCap ratings begin 2025-07-20. The PI confirmed
  July 16 2025 the same day, and every view and product now starts there (section 5).
- The therapy snapshots from before it name the leads "Right STN", model SenSight B33005; every
  record from implant on names them "Right VIM", model B33015. The earlier snapshots describe a
  different lead configuration, not this patient's.
- **Correction.** On 2026-09-24 I first said both sides had been on for six months (L 2.9 / R 3.1 mA
  from 2025-01-18) before the first 0 mA stretch. That was wrong. The January to April 2025 rows are
  four "Past Therapy" snapshots, 16 rows each, dated 2025-01-18, 02-17, 03-19 and 04-18 (exactly 30
  days apart). They were read off the device at the 2025-07-17 session and are not stimulation of
  the patient.
- The chronic band-power log (one reading every 10 minutes) and the patient-controller events run
  from 2025-06-18. Up to 2025-07-16 both leads read the same power distribution (median 40, 10th to
  90th percentile 26 to 58 on the left AND the right, 7,148 readings each). After 07-19 the power is
  about ten times higher and differs between sides (left median 499, right 156). The pre-July stretch
  is most likely pre-implant or in-house testing, as the PI suggested. The platform's chronic view
  shows it all the same.

## 1. The current-free periods in the record (both sides at 0 mA, from the settings stream)

| Stretch | Days after implant | REDCap reports | What else is changing |
|---|---|---|---|
| 2025-07-18 to 08-22 (left stays off until 10-21) | 2 to 37 | 96 (July 37, August 59) | the weeks after surgery; the first weeks of using the rating app |
| 2026-04-17 to 04-28 | 275 to 286 | 17 | coming off months of stimulation |
| 2026-05-14 to 05-28 | 302 to 316 | 18 | coming off stimulation |

- Pain barely moves in these stretches. Of the 251 reports with the left off, 203 (81%) are NRS 8 or 9;
  the 131 with both sides off have a standard deviation of 0.89. The 0-100 VAS (mean 84.8) resolves more finely.
- ~~Only 19 of the reports with the left off have a matched recording on L 1-3+ (decision 240).~~
  Wrong, and corrected in section 4 on the PI's challenge: decision 240's probe matched each report
  to recordings within 60 SECONDS (it passed the longest length of signal, 60 s, as the match
  window) and dropped the middle third of ratings; the page matches within 60 MINUTES. The real
  counts are in section 4.
- During the first stretch the device's chronic log mostly sensed 8.8 to 11.7 Hz, not 21.5 to 27.5
  Hz. The one exception is 23.44 Hz on R 0-2+: 15 days whose daily pain spread was 0.28, with a
  correlation of +0.04.

Pain across each switch, daily mean NRS (descriptive; 2 to 38 reports per window, no statistics):

| Switch | 14 days before | 0-2 d | 2-5 d | 5-9 d | 9-14 d | 14-28 d |
|---|---|---|---|---|---|---|
| both off 2025-07-18 | (no reports) | -- | 8.62 | 8.69 | 8.08 | 8.92 |
| right on 2025-08-22 | 8.86 | 8.83 | 8.89 | 8.45 | 8.25 | 7.64 |
| left on 2025-10-21 | 8.09 | 6.75 | 7.44 | 7.00 | 7.50 | 8.11 |
| both off 2026-04-17 | 6.79 | 6.40 | 6.67 | 7.60 | 8.88* | 8.62* |
| both on 2026-04-28 | 7.13 | 8.75 | 9.00 | 9.00 | 9.00 | 7.67 |
| both off 2026-05-14 | 8.62 | 7.60 | 8.00 | 7.20 | 7.71 | 6.85 |
| both on 2026-05-28 | 7.52 | 7.67 | 6.60 | 6.75 | 7.00 | 6.38 |

\* These windows overlap the switch back on at 04-28.

## 2. What ties the four together

The pain map, the heat-map grid and the confound checks all treat pain as a function of the current
in force at the moment of the rating. All four literatures say the response to stimulation has
**memory** (wash-in, carry-over, tolerance) and **context** (the brain state it lands on). The PI's
own rule 196 ("drift is a current effect") already implies memory: a stimulation-history term is how
to model drift as a current effect without modelling calendar time. Decision 253's drift at an
unchanged setting is the first test case.

## 3. Proposed analyses (read-only; none built)

1. Confirm the implant date. Start every analysis there, and decide what the chronic view does with
   the rows from before implant.
2. The PI's test, run properly: band against pain WITHIN each of the three current-free stretches
   (never between them), on VAS as well as NRS. Correct across the 22 bands, draw intervals by
   resampling whole days, and report any trend within each stretch beside the correlation. Then read
   the same band at a later unchanged setting, as a check of whether the relationship holds under
   stimulation.
3. Stimulation history: replace the current in force with an exponentially weighted history of
   current, trying time constants of 0, 1 h, 6 h, 1 d, 3 d and 7 d inside the held-out blocks of
   time. A time constant of 0 is today's model. Re-run decision 253's diagnosis with the history in
   place of the current.
4. Up-leg against down-leg at matched currents on the ladders already recorded (1,588 falling rows,
   decision 213). Lower pain on the way down would suggest carry-over.
5. Check decision 253's drift for regression to the mean: was each block preceded by an unusually
   good stretch?
6. Next clinic visit: a 55 to 60 Hz swap at fixed current, to see whether the band moves with the
   stimulator's harmonic, plus hold-and-return steps held for days at home.

## 4. Results, run 2026-09-24 (read-only probes; the page's own matcher and band-power cache)

### 4a. How many 0 mA reports have a recording (the corrected count)

| Stretch (both sides 0 mA) | Reports | Recordings in the stretch | Matched within 60 min (page default) | Matched to the nearest recording the same day (within 12 h) |
|---|---|---|---|---|
| 2025-07-16 to 08-22 | 96 | 12 streamed, 43 indefinite streams, 63 surveys, 24 montages; 24 of 33 report days have one | 16-17 per sensing pair, 13 days | 75 per sensing pair, 25 days |
| 2026-04-17 to 04-28 | 17 | none streamed; 144 device snapshots from patient events | R 0-3+ only: 13, 8 days | R 0-3+ 17, 10 days; left pairs 0-1 |
| 2026-05-14 to 05-28 | 18 | none streamed; 209 device snapshots | R 0-3+ only: 16, 10 days | R 0-3+ 18, 11 days; left pairs 0 |
| left off, right on, 2025-08-22 to 10-21 | 120 | | 35-37 per left pair, 32 days | 103 per left pair, 47 days |

The reports and the recordings are mostly hours apart: in July-August 2025 the median gap from a
report to the nearest streamed or survey recording is 5.1 h, 13 reports have one within 60 minutes,
32 within 3 h, 74 within 12 h. With 75 reports on 25 days, days as the independent unit, a
correlation of about 0.53 is detectable (80% power, p < 0.05), about 0.68 across 22 bands.

### 4b. Band against pain WITHIN each stretch (Spearman; intervals resample whole days; q across 22 bands)

- **2025-07-16 to 08-22, same-day matching, 60 s of signal.** On the left, 21.5-25.5 Hz rises with
  pain on the 0-100 VAS, with the current off on both sides: L 1-3+ 21.5 Hz +0.38 (+0.15 to +0.59),
  22.5 Hz +0.35 (+0.12 to +0.54), both q 0.044; L 0-2+ 21.5 Hz +0.36, 22.5 Hz +0.40, q 0.022;
  23.5-25.5 Hz positive with intervals above zero but q 0.08-0.09. On NRS the same bands read
  +0.17 to +0.30 and nothing survives correction (NRS spread 0.49 in this stretch: almost every
  rating is 8 or 9). WHAT COULD MAKE THIS: on L 1-3+ both the bands (+0.34 to +0.48) and pain
  (+0.17) drift upward over the five weeks, so part of it can be two things settling after surgery;
  on L 0-2+ the bands barely drift (-0.07 to +0.18) and the correlation is as large, which a shared
  drift does not explain.
- **At 60-minute matching** (16-17 reports) nothing survives correction; one or two bands have an
  uncorrected interval above zero.
- **Left off, right on (2025-08-22 to 10-21), same-day.** The SAME left bands now FALL with pain:
  L 1-3+ 21.5 Hz -0.37, 22.5 Hz -0.36 (q 0.002 and < 0.001), 17-18 of 22 bands negative on each left
  pair. Here the bands rise over the eight weeks (+0.22 to +0.53) while pain falls (-0.41 to -0.47,
  as the right-side stimulation began), so this sign is what two opposite trends produce.
- **2026-04 (R 0-3+ only, 17 reports on 10 days).** 8.5-12.5 Hz rises with NRS (+0.66 to +0.75,
  q < 0.01) and several bands with VAS -- in a stretch where pain climbs steeply after the current
  went off (+0.82 against time). Ten days cannot separate that from the climb.
- **2026-05 (R 0-3+ only, 18 reports on 11 days).** Nothing positive; five bands negative with NRS
  uncorrected.

Read: the one current-free stretch with real coverage, the weeks after implant, shows the left
21.5-25.5 Hz family rising with VAS pain, two bands surviving correction on each of two left pairs.
It is one stretch of 25 days, sitting in the post-surgical window and next to a stretch where the
same bands read the other way under a trend. It is a lead to confirm, not an established result.

### 4c. Decision 240's diagnostic at the page's 60-minute match window (NRS, tertile split)

At 60 s it had matched 53 reports on L 1-3+. At 60 minutes it matches 201 (30 s) and 187 (60 s):

| L 1-3+ | 30 s of signal (201 reports) | 60 s (187 reports) |
|---|---|---|
| current alone | 0.600 | 0.708 |
| every band | 0.722 (null 95th 0.716, p 0.035) | 0.743 (null 95th 0.673, p 0.040) |
| every band, current taken out (spline) | 0.681, inside the null | 0.683, OUTSIDE the null |

The other five pairs stay inside their nulls (R 0-3+, 459 reports: bands 0.445, current alone
0.357). Decision 240's "0.879 current alone, 0.701 bands, 0.526 without the current" came from the
60-second window and 53 reports; at the page's window the current is the weaker predictor on the
left and the bands carry something the current does not explain at 60 s -- p 0.04, uncorrected for
the 12 pair-and-length combinations tried.

### 4d. Stimulation history (time constant tau; 5 held-out blocks of time, neighbours dropped)

| tau | NRS, held-out R2 (777 ratings) | change in error vs tau 0 | Left Leg VAS, held-out R2 (612) |
|---|---|---|---|
| 0 (current in force) | +0.237 | -- | -0.067 |
| 1 h | +0.225 | +0.019 (+0.001 to +0.041) | -0.162 |
| 6 h | +0.228 | +0.015 (-0.004 to +0.036) | -0.245 |
| 1 d | +0.222 | +0.025 (-0.010 to +0.063) | -0.369 |
| 3 d | +0.207 | +0.050 (-0.002 to +0.105) | -0.904 |
| 7 d | +0.129 | +0.178 (+0.091 to +0.270) | -1.674 |
| 14 d | -0.082 | +0.525 (+0.351 to +0.710) | -2.095 |

A current with memory never predicts better than the current in force; up to 3 days it is no worse
within the interval, beyond it clearly worse. The Left Leg VAS is not predicted out of sample by any
version of the current (a squared term per side). Decision 253's drift at the unchanged setting is
not explained by history: with the epoch currents replaced by their dose at each tau, the left-leg
55 Hz 60/160 us surface still "moves between blocks of time" at every tau (61-63% of the miss shared
by whole blocks, p < 1e-7). As the time constant grows the dose tracks calendar time more closely
(r 0.54 to 0.68 on the left), which is the identifiability limit stated in report 2.

## 5. The implant-date cutoff (built 2026-09-24, decision 260)

Nothing dated before 2025-07-16 18:06 UTC reaches a view or a product; the rows stay in the database.

What went, measured on RCS08 against the committed code: 29 patient events (from 2025-06-18),
3,778 chronic-view timestamps (from 2025-05-26), 793 therapy-history timestamps (from 2024-11-16)
and 14 settings-stream rows. The heat-map grid does not move (34,129 fields, only timing and its key
differ). The Stim Optimizer's rated settings, currents and 776 ratings are identical; its settings
are renumbered (three unrated pre-implant settings gone) and four bench-only readiness cells lose
their one amplitude. On the Closed-Loop report the band-stability test and E2's interval move
slightly; every verdict is the same. Proving it exposed a separate bug (decision 261): the coverage
check miscounted rating days whenever the matched table was read back from the store.
