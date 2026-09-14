# What RCS08's own record says about the device's closed-loop timing settings

**Written 2026-09-13. Data only.** This is the participant's-own-data half of the PI's brief of
2026-09-13: the device's closed-loop timing settings (how long a crossing must last before the
device acts, how fast the current ramps, how long the device waits after switching on, and the
others) are to be chosen from RCS08's recorded dynamics with a stated reason, not from defaults.
Two other researchers are collecting the DOCUMENTED ranges from the manuals and the web; this file
supplies the numbers from the record, over a grid of candidate values, so the synthesis can pick
inside whatever range is documented. **No range is assumed here.**

Everything below was measured today on the live record of RCS08 (`2e3c75c00d7f4f37b53a048d195f11da`)
through the container bridge, by probe scripts under `BRAVO/_agent_bridge/_probe_tl/_timing/`
(gitignored; every table is beside them as a CSV, named in each section). Nothing in production
was edited and nothing was written to the shared store.

**Where the two bands live.** Both are on the LEFT electrode. "L 1-3+" is the sensing contact
pair `ONE_THREE_LEFT`, the band the PI has committed in his browser, at 24.5 Hz. "L 0-2+" is
`ZERO_TWO_LEFT`, the committed band of decision 139, at 24.5 Hz. The two contacts are never
pooled. The thresholds used for each are the ones stored in the Closed-Loop Deployment page's own
simulation entry for that band (read back, not retyped): L 1-3+ upper 210.58 / lower 161.90; L 0-2+
upper 196.13 / lower 190.89; current limits 1.4 to 4.8 mA on both. A third series, L 1-3+ at
23.5 Hz with the thresholds the DEVICE is running today (167 / 166, limits 2.0 to 3.0 mA), is
carried through the same analyses because that is the configuration the patient is on.

**The series.** The signal is the calibrated band power of every 3-second piece of voltage trace
on the contact, in the device's own units, with the current the device was delivering at that
moment (the same series the "CL-DBS simulations" card on the Closed-Loop Deployment page runs
over, decision 128), put on the device's 3-second clock inside each continuous stretch
(`simulation.regrid_stretches`). L 1-3+: 51,105 pieces, 538 unusable, 13,214 dropped because no
current was on record, leaving 37,891, in 325 continuous stretches of at least 3 pieces totalling
31.6 hours; the longest stretch 75 minutes, the 90th-percentile stretch 24.5 minutes, the median
stretch 26 seconds. L 0-2+: 32,904 pieces in 294 stretches totalling 27.4 hours. The
between-stretch gaps are ingestion gaps between clinic and home streaming sessions.

---

## 1. What is programmed today, verbatim from the device's newest session report

Newest ingested session report: `Rcs08.db - Report_Json_Session_Report_20260911T083131.json`,
`SessionDate` 2026-09-11T15:30:00Z. 572 session reports are ingested in all. The full list of
every group's fields is `t1_programmed_state_groups_final.csv`; the raw group tree is
`t1_groups_final.json`.

**The active group is GROUP_D, with adaptive therapy RUNNING on both sides, in Dual Threshold
mode.** Every adaptive-therapy field, with its exact key path:

```
Groups.Final[GROUP_D].ActiveGroup = true
Groups.Final[GROUP_D].ProgramSettings.RateInHertz = 55
Groups.Final[GROUP_D].GroupSettings.HighPassFilterInHertz = 1
Groups.Final[GROUP_D].GroupSettings.SensingBlankingDurationInMicroseconds = 1600

Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].HemisphereLocation = "HemisphereLocationDef.Left"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].Channel = "SensingElectrodeConfigDef.ONE_AND_THREE"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].BrainSensingStatus = "SensingStatusDef.ENABLED"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].AdaptiveTherapyStatus = "ADBSStatusDef.RUNNING"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].Mode = "AdaptiveModeDef.DUAL_THRESHOLD_DIRECT"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].UpperLfpThreshold = 167.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].LowerLfpThreshold = 166.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].MeasuredUpperLfp = 669
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].MeasuredLowerLfp = 655
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].UpperCaptureAmplitudeInMilliAmps = 3.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].LowerCaptureAmplitudeInMilliAmps = 2.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].UpperLimitInMilliAmps = 3.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].LowerLimitInMilliAmps = 2.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].SuspendAmplitudeInMilliAmps = 3.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].TransitionUpInMilliSeconds = 4000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].TransitionDownInMilliSeconds = 4000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].RateInHertz = 55
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].PulseWidthInMicroSecond = 100
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].SensingSetup.FrequencyInHertz = 23.44
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].SensingSetup.AveragingDurationInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].AdaptiveTherapy.UpperThresholdOnsetInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].AdaptiveTherapy.LowerThresholdOnsetInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].AdaptiveTherapy.DetectionBlankingDurationInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[0].AdaptiveTherapy.AdaptiveStartupDelayInMilliSeconds = 0

Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].HemisphereLocation = "HemisphereLocationDef.Right"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].Channel = "SensingElectrodeConfigDef.ONE_AND_THREE"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].GangedToHemisphere = "HemisphereLocationDef.Left"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].BrainSensingStatus = "SensingStatusDef.ENABLED"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].AdaptiveTherapyStatus = "ADBSStatusDef.RUNNING"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].Mode = "AdaptiveModeDef.DUAL_THRESHOLD_DIRECT"
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].UpperLfpThreshold = 167.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].LowerLfpThreshold = 166.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].MeasuredUpperLfp = 669
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].MeasuredLowerLfp = 655
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].UpperCaptureAmplitudeInMilliAmps = 3.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].LowerCaptureAmplitudeInMilliAmps = 2.0
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].UpperLimitInMilliAmps = 2.5
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].LowerLimitInMilliAmps = 1.5
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].SuspendAmplitudeInMilliAmps = 2.5
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].TransitionUpInMilliSeconds = 4000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].TransitionDownInMilliSeconds = 4000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].RateInHertz = 55
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].PulseWidthInMicroSecond = 150
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].SensingSetup.FrequencyInHertz = 23.44
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].SensingSetup.AveragingDurationInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].AdaptiveTherapy.UpperThresholdOnsetInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].AdaptiveTherapy.LowerThresholdOnsetInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].AdaptiveTherapy.DetectionBlankingDurationInMilliSeconds = 30000
Groups.Final[GROUP_D].ProgramSettings.SensingChannel[1].AdaptiveTherapy.AdaptiveStartupDelayInMilliSeconds = 0
```

The one other group with sensing, GROUP_A (not active), has adaptive therapy NOT_CONFIGURED and
carries what look like the tablet's defaults: onset 1200 / 1200 ms, detection blanking 2000 ms,
startup delay 0, averaging 3000 ms, transitions 0 / 0, thresholds 30 / 20, limits 0 to 4.0 mA
(Left) and 0 to 3.0 mA (Right), `SensingBlankingDurationInMicroseconds` 1640.

**Three things to read off this before any of the analysis.**

1. **The right-side channel is `GangedToHemisphere = Left`** and carries the left channel's
   thresholds (167 / 166) and measured values (669 / 655) with its own current limits (1.5 to
   2.5 mA). One sensed signal, on the LEFT 1-3 pair at 23.44 Hz, drives both sides.
2. **The upper and lower thresholds are one device unit apart (167 / 166).** With that gap the
   two-threshold controller is, in effect, a single threshold: the signal is almost never
   "between" (section 2 below: 0.3 percent of pieces).
3. **`DEVICE_percept_rc.md` section 2 says the Dual Threshold timing is fixed at onset 1200 ms,
   blanking 2000 ms, transitions 2.5 min up and 5 min down. The device's own record says these
   are programmable and have been programmed to other values.** The record of every adaptive
   configuration RCS08 has actually run (`t1_running_configurations_in_record.csv`, all 572
   reports read, 527 group-channel rows with status RUNNING):

| dates (session reports) | group / side | mode | onset up / low ms | blanking ms | transition up / down ms | averaging ms | startup delay ms | thresholds | capture mA |
|---|---|---|---|---|---|---|---|---|---|
| 2025-07-17 | D, Left 0-2 and Right 1-3 | Dual | 1200 / 1200 | 2000 | 138000 / 300000 | 1200 (L), 3000 (R) | 10000 | 50 / 30 | 1.2 to 2.3 |
| 2025-10-21 to 10-29 | C, Right 0-3 | Single | 200 / 200 | 550 | 250 / 250 | 100 | 10000 | 385 / 385 | 0 to 2.0 |
| 2026-02-03 to 02-19 | D, both 0-3 | Single | 200 / 200 | 550 | 250 / 250 | 100 | 10000 | 1 / 1 | 0 to 1.0 |
| 2026-02-19 to 03-18 | D, both 0-3 | Single | 200 / 200 | 550 | 250 / 250 | 100 | 10000 | 120 / 120 | 0 to 1.2 |
| 2026-03-31 to 04-16 | D, both 0-3 | Single | 200 / 200 | 550 | 1600 / 800 (L), 1200 / 600 (R) | 100 | 10000 | 91 / 91 | 0 to 1.4 |
| 2026-04-16 to 04-28 | C, both 0-3 | Single | 200 / 200 | 550 | 2400 / 1200 | 100 | 10000 | 100 / 100 | 0 to 1.2 |
| 2026-05-14 to 05-26 | D, both 0-3 | Single | 200 / 200 | 550 | 1800 / 900 | 100 | 10000 | 60 / 60 | 0 to 1.2 |
| 2026-05-28 to 08-06 | D, both 0-3 | Single | 15000 / 15000 | 1000 | 2000 / 2000 | 1000 | 30000 | 60 / 60 | 0 to 1.2 |
| 2026-09-02 to 09-03 | D, both 1-3 | Dual | 30000 / 30000 | 30000 | 4000 / 4000 | 30000 | 0 | 167 / 1 | 2.0 to 3.0 |
| 2026-09-04 to 09-11 (today) | D, both 1-3 | Dual | 30000 / 30000 | 30000 | 4000 / 4000 | 30000 | 0 | 167 / 166 | 2.0 to 3.0 |

So within RCS08's own history the device has accepted: onset 200 ms to 30,000 ms; detection
blanking 550 ms to 30,000 ms; transition 250 ms to 300,000 ms; averaging 100 ms to 30,000 ms;
startup delay 0, 10,000 and 30,000 ms. **These are values the tablet accepted, not the tablet's
limits** -- the documented range is the other researchers' job -- but any documented range must
at least contain them. The 2.5 min / 5 min figures in `DEVICE_percept_rc.md` appear in the record
exactly once, on 2025-07-17 (138 s / 300 s), as a programmed choice.

---

## 2. The signal's own time scales

Files: `t2_series_meta.csv`, `t2_acf.csv`, `t2_acf_robust.csv`, `t2_variance_by_timescale.csv`,
`t2_variance_split.csv`, `t2_dwell_summary.csv`, `t2_dwell_runs.csv`, `t2_chronic_acf*.csv`.

**The pieces are very noisy and heavy-tailed.** On L 1-3+ the median piece is 217 device units,
the 99.5th percentile 1,196, the largest 32,797; on L 0-2+ median 181, 99.5th percentile 639,
largest 34,268. So every statistic below is given twice: on the raw pieces, and with the top
0.5 percent set aside as the project's own ceiling rule does (decisions 52 and 94). The
threshold gap in units of the piece-to-piece scatter within a stretch: L 1-3+ 48.7 units = 0.22
raw SD (0.47 SD with the top 0.5 percent aside); L 0-2+ 5.2 units = 0.03 raw SD (0.08 SD).

**(a) How similar two readings T seconds apart are (the autocorrelation), within stretches.**
Each stretch's own mean removed first, so this is the short-term structure, not day-to-day shifts.

| lag | L 1-3+ raw | L 1-3+ top 0.5 % aside | L 0-2+ raw | L 0-2+ top 0.5 % aside |
|---|---|---|---|---|
| 3 s (next piece) | +0.05 | +0.19 | −0.05 | +0.08 |
| 6 s | +0.07 | +0.15 | 0.00 | +0.04 |
| 9 s | +0.05 | +0.13 | −0.01 | +0.05 |
| 15 s | +0.04 | +0.12 | −0.02 | +0.05 |
| 30 s | +0.01 | +0.07 | −0.05 | +0.03 |
| 60 s | +0.03 | +0.07 | +0.01 | +0.03 |
| 120 s | +0.03 | +0.06 | +0.01 | +0.03 |

- **1/e time: below the 3-second floor on both bands.** The correlation between one piece and
  the next is already under 0.37, so the "memory" of the fast part of the signal is shorter than
  one piece and cannot be measured with 3-second pieces.
- **First zero crossing:** L 1-3+ raw 324 s, L 0-2+ raw 3 s -- both figures are meaningless
  because the raw correlation is within ±0.05 of zero everywhere; with the spikes aside the
  correlation does not cross zero out to 2 minutes and sits at +0.06 to +0.07 (L 1-3+) and +0.03
  (L 0-2+). That is a small slow component riding on a large fast one.

**(b) Where the variance lives.** Rather than a power spectrum, which a clinician cannot read,
the same question asked directly: how much of the piece-to-piece variance is left after averaging
over T seconds. Pure noise would leave 3/T. Within stretches, top 0.5 percent aside:

| averaging T | L 1-3+ | L 0-2+ | pure noise would leave |
|---|---|---|---|
| 3 s (no averaging) | 100 % | 100 % | 100 % |
| 6 s | 60 % | 54 % | 50 % |
| 9 s | 45 % | 38 % | 33 % |
| 15 s | 33 % | 25 % | 20 % |
| 30 s | 22 % | 15 % | 10 % |
| 60 s | 16 % | 9 % | 5 % |
| 120 s | 11.5 % | 6 % | 2.5 % |
| 300 s | 8 % | 3.5 % | 1 % |
| 600 s | 6 % | 2 % | 0.5 % |

Read as the fraction of within-stretch variance at periods SHORTER than T: roughly 55 percent
under 10 s, 78 percent under 30 s, 84 percent under 1 min and 92 percent under 5 min on L 1-3+;
62, 85, 91 and 96 percent on L 0-2+. A Welch estimate on the raw series (12.8-minute windows,
`t2_variance_by_timescale.csv`) gives the same picture: 35 / 58 / 71 / 100 percent (L 1-3+) and
61 / 95 / 98 / 100 percent (L 0-2+) under 10 s / 30 s / 60 s / 5 min. **Periods of 30 minutes
cannot be resolved inside stretches** (90th-percentile stretch 24.5 min), so that cell is
empty by construction. What the stretches DO show about slower change: of the TOTAL variance of
all pieces, 73 percent (L 1-3+) and 86 percent (L 0-2+) is within-stretch scatter and 27 / 14
percent is the difference between stretch levels (stretch-mean SD 137 and 80 units; the SD of
daily means 111 and 56 units over 81 recording days). The device's own chronic 10-minute series,
within recordings and clipped at the 99th percentile, shows no correlation from 20 minutes to
24 hours on either side (`t2_chronic_acf_clipped.csv`; Right at 10 min +0.47, Left −0.04, then
zero) -- that series is spike-laden and quantised, so this is reported, not leaned on.

**(c) How long the signal dwells above the upper threshold, below the lower one, and between**
(state carried across a missing piece, top 0.5 percent aside; raw gives the same numbers to the
second):

| band | state | runs | 10th / median / 90th pct | mean | share shorter than 6 s / 15 s / 30 s / 60 s |
|---|---|---|---|---|---|
| L 1-3+ (210.6 / 161.9) | above upper | 5,192 | 3 / 6 / 24 s | 11 s | 43 / 79 / 92 / 98 % |
| | below lower | 4,734 | 3 / 3 / 15 s | 8 s | 55 / 88 / 96 / 99 % |
| | between | 4,266 | 3 / 3 / 6 s | 4 s | 81 / 100 / 100 / 100 % |
| L 0-2+ (196.1 / 190.9) | above upper | 5,641 | 3 / 3 / 15 s | 8 s | 51 / 87 / 97 / 99 % |
| | below lower | 5,741 | 3 / 6 / 18 s | 9 s | 47 / 85 / 95 / 99 % |
| | between | 629 | 3 / 3 / 3 s | 3 s | 96 / 100 / 100 / 100 % |
| L 1-3+ at 23.5 Hz, device's 167 / 166 | above | 4,856 | 3 / 6 / 27 s | 15 s | 41 / 76 / 90 / 96 % |
| | below | 4,789 | 3 / 3 / 18 s | 9 s | 54 / 87 / 96 / 99 % |
| | between | 119 | 3 / 3 / 3 s | 3 s | 99 / 100 / 100 / 100 % |

Occupancy: L 1-3+ 51 percent of pieces above the upper threshold, 34 percent below the lower;
L 0-2+ 44 / 54 percent with 2 percent between; the device's own pair 62 / 37 percent with 0.3
percent between.

**In one sentence:** on both bands the 3-second readings are close to independent draws around a
level that moves slowly, the typical excursion past a threshold lasts one or two pieces, and nine
in ten excursions are over within 30 seconds.

---

## 3. Crossing chatter against the onset duration

File: `t3_onset_sweep.csv`. The Dual Threshold controller of the simulation module (M0, the zero
response curve -- the replay as it is) was run over every stretch with the onset duration swept,
the other settings at the replay's defaults (blanking 2000 ms, transition up 150 s, down 300 s,
current started at the midpoint of the limits). "Reversal" = a transition undone by the opposite
transition within one onset duration; "within 60 s" = undone within a minute whatever the onset.

**The documented 1.2 s cannot be expressed:** the replay runs on the 3-second clock of the pieces
and rounds the onset up to whole pieces, so 1.2 s and 3 s are the same row (one piece). The
device's own detector updates five times a second on a 1.2-second average, so its chatter at a
1.2-second onset would be at least what the 3-second row shows, not less.

**L 1-3+ at 24.5 Hz, 31.6 h of signal**

| onset | transitions / h | transitions | reversals within one onset | undone within 60 s | time at upper limit | at lower limit | mean current | current travelled |
|---|---|---|---|---|---|---|---|---|
| 1.2 s = 3 s (1 piece) | 447.5 | 14,136 | 5,111 | 8,002 | 44.1 % | 14.0 % | 3.65 mA | 20.8 mA/h |
| 6 s | 89.1 | 2,816 | 503 | 1,413 | 47.7 % | 19.5 % | 3.60 | 16.3 |
| 9 s | 27.6 | 871 | 74 | 304 | 49.8 % | 21.7 % | 3.61 | 13.5 |
| 15 s | 7.3 | 232 | 1 | 13 | 51.2 % | 25.3 % | 3.53 | 8.2 |
| 30 s | 2.5 | 78 | 0 | 0 | 44.9 % | 20.8 % | 3.51 | 4.2 |
| 60 s | 1.5 | 47 | 0 | 0 | 26.2 % | 9.7 % | 3.38 | 2.3 |
| 120 s | 0.7 | 23 | 0 | 0 | 11.1 % | 3.6 % | 3.23 | 1.2 |

**L 0-2+ at 24.5 Hz, 27.4 h of signal**

| onset | transitions / h | transitions | reversals within one onset | undone within 60 s | time at upper limit | at lower limit | mean current | current travelled |
|---|---|---|---|---|---|---|---|---|
| 1.2 s = 3 s | 437.8 | 12,004 | 5,364 | 10,037 | 27.2 % | 17.4 % | 3.41 mA | 32.7 mA/h |
| 6 s | 109.2 | 2,994 | 708 | 2,257 | 28.9 % | 25.2 % | 3.27 | 25.1 |
| 9 s | 42.3 | 1,161 | 128 | 605 | 31.8 % | 29.0 % | 3.22 | 19.6 |
| 15 s | 11.4 | 312 | 9 | 52 | 35.3 % | 35.3 % | 3.10 | 11.9 |
| 30 s | 2.6 | 70 | 0 | 0 | 28.5 % | 34.1 % | 2.99 | 4.5 |
| 60 s | 1.1 | 31 | 0 | 0 | 11.9 % | 19.4 % | 2.96 | 1.9 |
| 120 s | 0.3 | 8 | 0 | 0 | 0.7 % | 4.8 % | 3.02 | 0.5 |

**L 1-3+ at 23.5 Hz with the device's own 167 / 166 and 2.0 to 3.0 mA** (31.6 h): 309 / 80.7 /
32.5 / 9.8 / 3.0 / 1.9 / 0.9 transitions per hour at 3 / 6 / 9 / 15 / 30 / 60 / 120 s; reversals
within one onset 4,417 / 637 / 131 / 4 / 0 / 0 / 0. With the device's timing as programmed today
(onset 30 s, blanking 30 s, transitions 4 s; the 30 s averaging is not emulated, so this is an
upper bound on the chatter): 3.0 transitions per hour, 0 reversals, 54 percent of the time at
3.0 mA and 28 percent at 2.0 mA.

**The knee.** Two things are read off the tables: where a transition stops being undone within
its own onset (chatter), and where each further doubling of the onset stops cutting the rate
three- to five-fold (the signature of noise) and starts merely halving it (the signature of a
slowly drifting level). On L 1-3+ the rate falls 5.0-fold from 3 to 6 s, 3.2-fold from 6 to
9 s, 3.8-fold from 9 to 15 s, 2.9-fold from 15 to 30 s, then 1.7-fold from 30 to 60 s and 2.1-fold
from 60 to 120 s; reversals fall from 5,111 to 1 at 15 s and 0 at 30 s. On L 0-2+ the fall is
4.0-, 2.6-, 3.7- and 4.4-fold over the same four steps up to 30 s and then 2.4- and 3.7-fold;
reversals reach 9 at 15 s and 0 at 30 s.

- **L 1-3+ at 24.5 Hz: knee 15 s.** At 15 s one transition in 232 is a reversal; the rate is
  1.6 percent of the 3-second rate; beyond 15 s the residual rate is set by the slow drift, not
  by noise.
- **L 0-2+ at 24.5 Hz: knee 30 s.** The 5-unit gap between its thresholds is 0.08 SD of the
  scatter, so this band never has a "between" state to rest in, and chatter is not gone until
  30 s (9 reversals of 312 at 15 s; 0 of 70 at 30 s).
- **A value that satisfies both is 30 s**, which is what the device is running today; 60 s and
  120 s buy little further reduction in transitions and cost the loop most of its time at the
  limits (L 1-3+: 45 percent of the time at the upper limit at 30 s, 26 percent at 60 s, 11
  percent at 120 s).

---

## 4. Transition durations

### 4a. How fast the band power settles after a current step (titration runs)

File: `t4a_step_settling.csv`. From the stored per-run points table, every run of rising current
on each contact, and within each run every hold of at least 5 pieces (15 s) at a new constant
current: a single exponential fitted to band power against time from the start of the hold, and
the time at which a 3-piece running mean reaches 63.2 percent of the change from the previous
hold's level to this hold's late level.

| contact | runs | steps | step size | hold length (median, range) | change in level (median, units) | change / scatter of the pieces (median, max) | exponential fit: variance explained (median, max) | fits stuck at a bound |
|---|---|---|---|---|---|---|---|---|
| L 1-3+ | 4 (2025-08-21, 2025-09-04, 2026-08-18) | 14 | 0.48 to 0.50 mA | 63 s (39 to 147 s) | 8.5 | 0.30 SD, 0.85 SD | 3.8 %, 21.6 % | 9 of 14 |
| L 0-2+ | 1 (2025-08-21) | 8 | 0.1 to 0.5 mA | 106 s (12 to 255 s) | 15.9 | 0.46 SD, 1.09 SD | 12.8 %, 48.4 % | 4 of 8 |

The simulation module's own settling-time routine (time to 63.2 percent of the change after the
largest step in each run, `simulation.measured_settling_time`) gives 3.0 s on L 1-3+ (per run 3,
3, 3, 6 s; 4 of 4 runs) and 15 s on L 0-2+ (1 run). **Neither number is a settling time.** The
response to a 0.5 mA step is a third to a half of the piece-to-piece scatter, the exponential
fits explain a median 4 to 13 percent of the variance, and most land on a bound of the fit. What
the record supports is only: **whatever settling there is after a 0.5 mA step is not visible
above the 3-second scatter, so any time constant from the 3-second floor (decision 128) up to the
length of a hold (about 1 to 2 minutes) is compatible with these runs.** The titration session of
open item 30 (0 to 5 mA in 0.5 mA steps, 60 s holds, streaming) is what would measure it.

### 4b. The pain ratings' own time scale

File: `t4b_pain_rating_autocorrelation.csv`. 766 ratings, a median of 10 hours between
consecutive ones. The correlation between two ratings as a function of the time between them:

| gap | NRS | overall VAS | left-leg VAS | back VAS | MPQ sum | relief |
|---|---|---|---|---|---|---|
| under 1 h (mostly repeat entries) | 0.92 | 0.94 | 0.71 | 0.88 | 0.96 | 0.82 |
| 1 to 3 h | 0.45 | 0.53 | 0.42 | 0.33 | 0.61 | 0.25 |
| 3 to 6 h | 0.59 | 0.57 | 0.46 | 0.55 | 0.78 | 0.49 |
| 6 to 12 h | 0.55 | 0.53 | 0.47 | 0.54 | 0.79 | 0.43 |
| 12 to 24 h | 0.53 | 0.49 | 0.40 | 0.45 | 0.76 | 0.43 |
| 1 to 2 days | 0.43 | 0.39 | 0.28 | 0.34 | 0.68 | 0.32 |
| 2 to 4 days | 0.37 | 0.36 | 0.19 | 0.31 | 0.59 | 0.27 |
| 4 to 7 days | 0.31 | 0.29 | 0.05 | 0.25 | 0.55 | 0.24 |
| 1 to 2 weeks | 0.29 | 0.31 | 0.07 | 0.26 | 0.49 | 0.22 |
| 2 to 4 weeks | 0.22 | 0.27 | 0.08 | 0.18 | 0.38 | 0.13 |

The correlation halves from its 3-to-6-hour value at 4 to 7 days (NRS, back VAS), 2 to 4 days
(left-leg VAS) and 2 to 4 weeks (MPQ). **The pain state changes on a scale of days.** Every
transition duration on the grid (4 s to 10 min) is three to four orders of magnitude faster than
that, so the ratings cannot tell the candidates apart; what they do say is that no candidate is
too slow for the pain.

### 4c. The transition sweep in the replay

File: `t4c_transition_sweep.csv`. Up and down durations set equal and swept, at two onsets.
The replay refuses a transition shorter than one piece (3 s carries the whole range in one
step), so the shortest expressible value is the 4 s the device runs today.

**L 1-3+ at 24.5 Hz**

| transition (up = down) | onset 3 s: at upper / at lower / mean / travelled | onset 30 s: at upper / at lower / mean / travelled |
|---|---|---|
| 4 s | 53.1 % / 32.8 % / 3.43 mA / 591 mA/h | 48.1 % / 24.4 % / 3.50 mA / 4.3 mA/h |
| 30 s | 46.2 / 25.7 / 3.50 / 117 | 47.6 / 24.1 / 3.50 / 4.3 |
| 60 s | 44.0 / 24.3 / 3.50 / 63 | 46.9 / 23.7 / 3.50 / 4.3 |
| 150 s (2.5 min) | 40.1 / 22.0 / 3.48 / 29 | 44.9 / 22.5 / 3.49 / 4.3 |
| 300 s (5 min) | 35.3 / 19.2 / 3.45 / 17 | 41.8 / 20.8 / 3.48 / 4.1 |
| 600 s (10 min) | 28.8 / 15.2 / 3.42 / 10 | 36.4 / 18.0 / 3.45 / 3.7 |

**L 0-2+ at 24.5 Hz**

| transition (up = down) | onset 3 s: at upper / at lower / mean / travelled | onset 30 s: at upper / at lower / mean / travelled |
|---|---|---|
| 4 s | 33.9 % / 44.8 % / 2.92 mA / 1,082 mA/h | 31.1 % / 39.6 % / 2.96 mA / 5.0 mA/h |
| 30 s | 24.0 / 33.5 / 2.95 / 211 | 30.7 / 39.1 / 2.96 / 5.0 |
| 60 s | 22.3 / 31.1 / 2.98 / 110 | 30.2 / 38.4 / 2.96 / 4.8 |
| 150 s | 19.6 / 28.3 / 2.99 / 47 | 28.5 / 36.7 / 2.96 / 4.7 |
| 300 s | 16.5 / 25.2 / 2.98 / 25 | 25.8 / 34.1 / 2.96 / 4.5 |
| 600 s | 11.8 / 20.4 / 2.95 / 14 | 21.1 / 29.8 / 2.95 / 4.1 |

**What the data can and cannot discriminate.** With a short onset the transition duration is the
only thing limiting how far the current travels: 591 to 1,082 mA per hour at 4 s against 10 to 14
at 10 min, which is to say the patient would feel the current sweeping the range hundreds of
times an hour. With the onset at 30 s the transition rate is 2.5 per hour and the transition
duration no longer matters below about a minute: 4 s, 30 s and 60 s give the same time at the
limits within 1.2 percentage points and the same 4.3 to 5.0 mA of travel per hour. From 150 s
upward the ramp starts to be longer than the dwell times of section 2 and the loop stops reaching
the limits (time at the upper limit 48 to 36 percent on L 1-3+ as the transition goes 4 s to
10 min). **So: between 4 s and 60 s the record cannot separate the candidates; 2.5 min and
longer are visibly different, in the direction of the loop never completing a move.** Two things
outside this replay bear on the choice and are stated rather than assumed: the device blanks its
own sensing for the programmed blanking duration around a change, and the settling time of
section 4a is unmeasured (compatible with anything from 3 s to about a minute).

---

## 5. Adaptive startup delay

Files: `t5_stretch_start_transient.csv`, `t5_after_programming_by_bin.csv`,
`t5_settling_after_programming_pieces.csv`, `t5_settling_after_programming_chronic.csv`.

Three sources were asked how long band power takes to reach its level after something starts.

**(i) The start of every continuous stretch of sensing** -- the moment the device begins
producing pieces -- against the same stretch's level from 2 minutes onward, in units of the
stretch's own scatter (stretches of at least 4 minutes; 85 on L 1-3+, 71 on L 0-2+):

| pieces after the start | L 1-3+: mean deviation ± SE, share beyond 1 SD | L 0-2+: mean deviation ± SE, share beyond 1 SD |
|---|---|---|
| 1st (0 to 3 s) | −0.24 ± 0.13 SD, 25 % | −0.24 ± 0.11 SD, 30 % |
| 2nd (3 to 6 s) | −0.28 ± 0.10, 30 % | −0.41 ± 0.10, 30 % |
| 3rd (6 to 9 s) | −0.27 ± 0.11, 23 % | −0.11 ± 0.11, 27 % |
| 4th (9 to 12 s) | −0.12 ± 0.10, 27 % | +0.02 ± 0.13, 25 % |
| 5th (12 to 15 s) | −0.06 ± 0.12, 35 % | −0.15 ± 0.10, 26 % |
| 6th to 10th (15 to 30 s) | −0.04 ± 0.07, 7 % | +0.03 ± 0.08, 8 % |
| 11th to 20th (30 to 60 s) | +0.01 ± 0.08, 8 % | −0.02 ± 0.05, 3 % |
| 21st to 40th (60 to 120 s) | −0.10 ± 0.04, 0 % | −0.07 ± 0.04, 0 % |

The first three pieces (0 to 9 s) read a quarter to two-fifths of a standard deviation LOW on both
contacts (two to four standard errors from zero); by the fourth piece the bias is gone and by
15 s the 5-piece averages sit where the later level is. **The record shows a sensing start-up
transient of about 9 seconds, and nothing after 15 seconds.**

**(ii) After each programming change** (the 122 starts of the settings epochs from the device's
own therapy history). Only 3 changes per contact have pieces both in the 5 minutes before and the
15 minutes after (streaming is usually started after programming, not across it), and only ONE
change per contact has pieces in the first minute: 2026-09-02 on L 1-3+ (first minute −0.29 SD
from the 5-to-15-minute level, n = 20 pieces, standard error 0.22) and 2026-06-24 on L 0-2+
(+0.63 SD, n = 20, SE 0.22). Across the changes that have pieces in a later bin, the deviation
from the 5-to-15-minute level: 1 to 3 minutes after the change, mean +0.02 ± 0.28 SD (9 changes,
L 1-3+) and −0.13 ± 0.15 (9, L 0-2+); 3 to 5 minutes, −0.13 ± 0.15 (17) and −0.13 ± 0.13 (16). No
bin differs from zero by two standard errors. The exponential fits on the three fully-covered
changes explain a median 3 to 4 percent of the variance. **Minutes after a programming change the
band power is at its later level as far as the pieces can tell; the first minute is one event
per contact and says nothing either way.**

**(iii) The device's own chronic 10-minute series after each programming change**, per side,
against that change's 24-to-48-hour level (35 changes on the Left, 53 on the Right with at least
60 samples in the following 48 hours at one sensing centre): median deviation in hours 0-1, 1-3,
3-6, 6-12 and 12-24 is +0.12, +0.26, −0.14, −0.05, +0.33 SD on the Left and −0.12, −0.18, −0.22,
−0.05, −0.09 SD on the Right, with no trend from the first hour to the first day. **At the
10-minute cadence there is no settling to see over hours.** (The means are dominated by a handful
of changes whose later level had almost no spread and are not quoted; the medians are.)

**The startup delay in the record itself:** every earlier RUNNING configuration carried
`AdaptiveStartupDelayInMilliSeconds` = 10,000 (July 2025 to May 2026) or 30,000 (May to August
2026); today's carries 0.

---

## 6. One sentence per parameter, from the data

- **Onset duration (`UpperThresholdOnsetInMilliSeconds` / `LowerThresholdOnsetInMilliSeconds`):
  the data support 15 s on L 1-3+ and 30 s on L 0-2+, and 30 s for either, because the 3-second
  readings are nearly independent draws with excursions past a threshold that last one or two
  pieces, so a 1.2-second onset would switch the current about 440 times an hour with a third of
  the switches undone within one onset, a 15-second onset cuts that to 7 to 11 an hour with 0.4
  to 3 percent undone, and a 30-second onset to 2.5 an hour with none undone -- beyond which each
  doubling only halves the rate and halves the loop's time at its limits.**
- **Averaging duration (`SensingSetup.AveragingDurationInMilliSeconds`): the data support
  averaging of at least 15 to 30 s because a 3-second reading carries about 55 to 62 percent of
  its variance at periods under 10 seconds and only 16 (L 1-3+) or 9 percent (L 0-2+) of it
  survives a 60-second average, against 5 percent for pure noise -- the slow part of the signal
  the controller should follow is that residual, not the piece-to-piece scatter.** The device is
  running 30 s today; the replay cannot emulate the averaging and the onset separately, so their
  split is a documented-range question.
- **Transition up and down (`TransitionUpInMilliSeconds` / `TransitionDownInMilliSeconds`): the
  data cannot separate 4 s from 60 s once the onset is 30 s (time at the limits within 1.2
  percentage points, 4.3 to 5.0 mA of travel per hour either way), can separate 2.5 min and
  longer (the ramp outlasts the typical dwell, so the loop stops reaching its limits), and
  provide no settling time to anchor the choice because a 0.5 mA step moves the band by a third
  to a half of the scatter and the exponential fits explain 4 to 13 percent of the variance;**
  the pain ratings change over days, so no candidate on the grid is too slow for them.
- **Adaptive startup delay (`AdaptiveStartupDelayInMilliSeconds`): the data support a delay of
  about 10 to 15 s because the first three pieces after sensing starts read 0.24 to 0.41 SD low
  (two to four standard errors) and the bias is gone by the fourth piece, while minutes after a
  programming change the band is at its later level and the device's own 10-minute series shows
  no settling over hours -- nothing in the record argues for a delay longer than 15 s.**
- **Detection blanking (`DetectionBlankingDurationInMilliSeconds`): the data supply no direct
  measurement (the pieces are 3 s and the device's blanking hides its own readings, so the effect
  of a current change on the reading cannot be seen in this series); what bears on it is the same
  9-second start-up dip, which says readings taken in the first few seconds after the device
  starts sensing run low.**
- **Threshold gap (not a timing setting, but it sets how the timing behaves): the data say the
  device's 167 / 166 pair leaves 0.3 percent of readings "between", and L 0-2+'s stored pair
  (5.2 units) 2 percent, so on those two the controller behaves as a single threshold and needs
  the 30-second onset to avoid chatter; L 1-3+'s stored pair (48.7 units, 0.47 SD of the scatter)
  leaves 11 percent between and reaches its knee at 15 s.**

---

## 7. What this record cannot decide, and why

1. **The settling time of band power after a current step (4a).** 4 runs on L 1-3+ and 1 on
   L 0-2+, steps of 0.5 mA, holds of 40 to 250 s; the step response is 0.30 to 0.46 SD of the
   3-second scatter and the fits explain a median 4 to 13 percent of the variance. Any time
   constant from 3 s to about a minute is compatible. Open item 30's titration session (0 to 5 mA,
   0.5 mA steps, 60 s holds, streaming, one rate) is the measurement.
2. **Anything shorter than 3 seconds.** The pieces are 3 s long; the documented 1.2-second onset,
   200-millisecond onset, 550-millisecond blanking and 250-millisecond transitions all fall
   below the floor and appear in the tables as their 3-second equivalents.
3. **The device's 30-second averaging.** The replay averages onto the piece clock; it cannot run a
   30-second average and a 30-second onset as two separate stages, so the "device today" row
   (2.5 to 3.0 transitions per hour) is an upper bound on today's chatter.
4. **The first minute after a programming change.** One change per contact has pieces in it
   (−0.29 ± 0.22 and +0.63 ± 0.22 SD); the clinic starts streaming after programming, not across
   it.
5. **Periods of 30 minutes and longer inside the signal.** The 90th-percentile stretch is 24.5
   minutes; slower change is visible only as differences between stretches (27 and 14 percent of
   the total variance) and the chronic series, which is spike-laden and shows no correlation
   beyond 10 minutes.
6. **The right side.** Both bands are on the left electrode; the device gangs the right channel to
   the left sensing signal, so nothing here measures a right-side band.
7. **Transition durations between 4 s and 60 s** once the onset is 30 s: indistinguishable in the
   replay (section 4c); a preference among them has to come from the settling time (unmeasured,
   item 1) or from the documented behaviour of the blanking.
8. **Whether the 9-second start-up dip is the device or the tissue.** It is measured at the start
   of every stretch of the offline calibrated pieces; the device's own detector after a group
   switch is not in the record.

---

## 8. Files

All under `BRAVO/_agent_bridge/_probe_tl/_timing/` (gitignored, on this machine and in the
container at `/usr/src/BRAVO/_agent_bridge/_probe_tl/_timing/`):

| probe | writes |
|---|---|
| `probe_t1_programmed_state.py`, `probe_t1b_compact.py` | `t1_programmed_state_groups_final.csv`, `t1_groups_final.json`, `t1_groups_final_adaptive_fields.csv`, `t1_group_history_adaptive.csv` |
| `probe_t1c_adaptive_history.py`, `probe_t1d_running_table.py` | `t1_adaptive_fields_every_report.csv`, `t1_adaptive_fields_changes.csv`, `t1_running_configurations_in_record.csv` |
| `probe_t2_timescales.py` | `series_*.npz` (the three series), `t2_series_meta.csv`, `t2_acf.csv`, `t2_variance_by_timescale.csv`, `t2_dwell_summary.csv`, `t2_dwell_runs.csv` |
| `probe_t2b_slow_scales.py`, `probe_t2c_robust.py` | `t2_variance_split.csv`, `t2_chronic_acf.csv`, `t2_chronic_acf_clipped.csv`, `t2_acf_robust.csv` |
| `probe_t3_t4c_sweeps.py` | `t3_onset_sweep.csv`, `t4c_transition_sweep.csv` |
| `probe_t4ab_t5_settling.py` | `t4a_step_settling.csv`, `t4b_pain_rating_autocorrelation.csv`, `t5_settling_after_programming_pieces.csv`, `t5_settling_after_programming_chronic.csv`, `t5_chronic_series.csv` |
| `probe_t5b_transients.py` | `t5_stretch_start_transient.csv`, `t5_after_programming_by_bin.csv` |

The replay used is `ClosedLoopDeployment/simulation.py`'s `simulate_series` with the zero response
curve (M0), the same arithmetic the "CL-DBS simulations" card runs, over the stretches of
`regrid_stretches`; the series come from `adapter.simulation_inputs_for_participant`. `store.clear()`
was never called.
