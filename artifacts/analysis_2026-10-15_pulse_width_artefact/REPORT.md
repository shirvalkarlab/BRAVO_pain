# Pulse width and stimulation artefact on RCS08 (2026-10-15)

Offline analysis. On no page, feeds no calculation, writes nothing to the store or the device.
Worked from the device exports directly because the container was down (OrbStack not running).

## The question

The A610 programming guide (p. 73) says that above 5 mA or 120 µs, "the artifact of stimulation
may cause the LFP to appear elevated" when the Lower LFP Threshold is captured. BRAVO enforces this
as a blocking device rule (D27, `ClosedLoopDeployment/constraints.py`). Since decision 471
(2026-10-14) its pulse-width limit applies only to a stimulator on the same lead as the sensing
contacts. For RCS08 it refuses the right stimulator driven from right-lead sensing, because the
right side runs at 160 µs (decision 470's live check lists D27). Every comparison below is of this
kind: artefact on the stimulating lead's own sensing pair. The questions were:

1. Does a pulse width above 120 µs (for example 150–160 µs) produce more artefact than ≤60 µs?
2. What does the detected artefact look like, in numbers?
3. Does it matter for closed loop?

## Short answers

1. **The record cannot test ≤60 µs against >120 µs head to head.** With the same sensing pair, the
   same rate and an overlapping current range, ≤60 µs offers 3 steps in total (left 1–3 pair) and
   none on the right. **What it can test:** at the same rate and pair, **wider pulses give a larger
   stimulation line per milliamp.** On the right 0–3 pair, 150–180 µs grows 2.5 times faster than
   100 µs at 55 Hz (95 % interval 1.8–3.4) and 2.4 times faster at 110 Hz (1.7–4.8). If the
   artefact scaled with the charge per pulse (current × pulse width), the expected ratios would be
   1.6 and 1.9. The left 1–3 pair at 55 Hz gives 0.42, with an interval of 0.32–12.9: no answer.
2. **The artefact is narrow lines at the stimulation rate and its folded multiples, mostly outside
   the sensing range.** On the right 0–3 pair at >120 µs, the lines' combined amplitude has a median
   of 9.8, 20.4, 30.6 and 51.5 µV at 0–1, 1–2, 2–3 and 3–4 mA. Inside 5–32.5 Hz the lines are found
   no more often than with stimulation off.
3. **Up to 3 mA at 150–180 µs, stimulation does not raise the device's own band power.** On the
   right 0–3 pair at 55 Hz, band power with current on, divided by the same recording's 0 mA value,
   has a median of 1.01 (interval 0.98–1.10; 34 recordings, 14 days, 0–4 mA). A rise of 10 % or
   more would have shown. **At 3–4 mA it is 1.19** (only 2 recordings on 2 days), which is in line
   with the guide. The record gives no reason to drop D27, and no evidence that 160 µs inflates a
   capture at or below 3 mA on this lead.

## Data

- 580 device exports, 448 unique streaming recordings (copies in several exports merged; 15 more
  had no matching band-power stream and are left out).
- Each recording carries its own pulse width, rate and contacts for the sensed side (the recording's
  therapy snapshot) and the current on both sides twice a second.
- **A step** is a stretch where the sensed side's current holds still for at least 4 s, after
  dropping the first 1 s and last 0.5 s. 749 steps from 326 recordings. The other side's current is
  recorded beside each step.
- Power from the voltage trace (TD), computed by me: 2 s windows, 0.5 Hz bins, linear units
  (µV²/Hz), only inside stretches without missing packets. No log power anywhere.

Where the pulse widths are (seconds with the sensed side's current on, all recordings):

| Sensing pair | ≤60 µs | 61–120 µs | >120 µs |
|---|---|---|---|
| Right 0–3 | 28 min, 4 recordings, ≤2.0 mA (125 and 165 Hz) | 41 min | **1,063 min**, mostly 160 µs at 55 Hz (923 min, 17 days) |
| Left 1–3 | 22 min, 4 recordings | 160 min, mostly 100 µs | 34 min |
| Left 0–2 | 18 min, 3 recordings, 1 day | 18 min | 2 min |

Left-side recordings at 180 µs never went above 0.1 mA, so they carry no stimulation to test.

## How the artefact was measured

- **Landing frequencies.** At 250 samples per second, the 1st to 8th multiples of the stimulation
  rate fold back below 125 Hz (the project's own rule, `harmonic_landings_hz`). At 55 Hz they land
  at 5, 25, 30, 55, 60, 80, 85, 110 and 115 Hz.
- **Line size.** At each landing, the power in the three bins at that frequency above the local
  background (the median 1.5–4 Hz on either side). Then subtract the same quantity measured on that
  sensing pair's own stimulation-off steps (both sides at 0 mA). Amplitude = square root, in µV.
- **"Found".** A step's line size is above the 95th percentile of its pair's stimulation-off steps,
  so 5 % of stimulation-off steps would count as found by chance.
- **Growth per milliamp.** A straight line through zero (no current, no artefact) of line amplitude
  against current. Intervals: resampling whole recordings, 4,000 times.

**A fixed device peak sits at 111 Hz, with a weaker one at 55.5 Hz, with both stimulators off.**
Across 178 stimulation-off stretches its median height is about 1,600 times the power beside it.
It is not stimulation, but it is 0.5–1 Hz from where 55 Hz stimulation lands (55 and 110 Hz).
That is why each pair's stimulation-off steps are the baseline. Separately, 6 of 97 stimulation-off
steps (all right 0–3, 2026, 55 Hz / 160 µs) carry a peak at exactly 55 Hz, 3,700 to 32,000 times
the power beside it. The record does
not say why; possibly current the 2 Hz log does not report.

## 1. Pulse width against artefact

**Matched comparisons with ≤60 µs (same pair, same rate, overlapping currents).**

| Pair, rate | ≤60 µs | >120 µs | Result |
|---|---|---|---|
| Left 1–3, 55 Hz | 1 step, 1 recording, 1.0 mA | 3 steps, 3 recordings, ≤1.0 mA | 23.8 against 21.2 µV per mA; 1 recording, no interval |
| Left 1–3, 165 Hz | 2 steps | 1 step | no line found in either |
| Right 0–3, 165 Hz | 1 step at 2.0 mA | ≤1.2 mA only | no shared currents |
| Left 0–2, 55 Hz | 5 steps at 3.5 mA | 2 steps at 1.6 mA | no shared currents |

**100 µs against wider pulses at the same rate and pair.**

| Pair, rate | 100 µs | 150–220 µs | Ratio of growth per mA (95 % interval) | Charge-scaled prediction |
|---|---|---|---|---|
| Right 0–3, 55 Hz | 8.8 µV/mA; 3 recordings, **1 day** | 22.3 µV/mA; 75 recordings, 15 days | **2.53 (1.80–3.39)** | 1.60 |
| Right 0–3, 110 Hz | 2.4 µV/mA; 8 recordings, 3 days | 5.6 µV/mA; 10 recordings, 3 days | **2.37 (1.68–4.78)** | 1.90 |
| Left 1–3, 55 Hz | 16.8 µV/mA; 20 recordings, 5 days | 7.1 µV/mA; 3 recordings, 2 days | 0.42 (0.32–12.9) | 2.73 |

Inside 5–32.5 Hz the same growth is 0.03–0.12 µV per mA in every row: 60 to 200 times smaller.

**Confounds that stay.** Pulse width changed with date, with the stimulating contacts and with the
rate, so a pulse-width effect cannot be separated from those. The 100 µs side of the 55 Hz row is
one visit day. One participant.

## 2. What the artefact looks like (right 0–3 pair, where the data are)

| Current | Steps (recordings, days) | Line found | Line amplitude, median (90th pct) | Found inside 5–32.5 Hz | 99.9th pct of the voltage trace |
|---|---|---|---|---|---|
| **>120 µs** 0–1 mA | 29 (24, 8) | 14 % | 9.8 µV (27.8) | 3 % | 46 µV |
| 1–2 mA | 141 (72, 18) | 53 % | 20.4 µV (49.7) | 5 % | 74 µV |
| 2–3 mA | 67 (29, 11) | 75 % | 30.6 µV (96.3) | 0 % | 119 µV |
| 3–4 mA | 44 (20, 6) | 98 % | 51.5 µV (117.6) | 2 % | 137 µV |
| **61–120 µs** 1–2 mA | 12 (10, 4) | 33 % | 1.9 µV (5.4) | 0 % | 28 µV |
| 2–3 mA | 8 (5, 3) | 100 % | 11.3 µV (26.6) | 0 % | 68 µV |

- At 55 Hz the strongest line is the 55 Hz bin itself, 1,000 to 12,000 times the power beside it
  (median by current band). It sits outside the 8–30 Hz range the device allows for sensing.
- **No clipping seen.** The largest voltage in any step is 1,063 µV; in the whole record 2,408 µV.
  The device's rail value is not in the exports, so clipping cannot be ruled out by value alone.
- **Device band-power spikes** (one sample 10 or more times its step's median) are not tied to
  stimulation: 297 of 119,500 samples with current on (0.25 %), 533 of 135,068 at 0 mA (0.39 %).

## 3. What it means for closed loop

- **The device's usual control band (26.4 Hz ± 2.5 Hz) contains the 25 Hz landing of 55 Hz
  stimulation.** The share of that band's power taken by the line (right 0–3, >120 µs): median 0 %
  at 0–1 mA, 1.5 % at 1–2 mA, 0 % at 2–3 mA, 0.2 % at 3–4 mA. The worst single step is 31 % (1–2 mA);
  with stimulation off the worst is 11 %, which is the noise in this measure.
- **The device's band power does not rise with current up to 3 mA**, within one recording, against
  that recording's 0 mA step:

| Current | Recordings, days | Device band power ×, median (95 % interval) | TD power 5–32.5 Hz × |
|---|---|---|---|
| 0–1 mA | 4, 3 | 0.94 (0.89–1.00) | 0.97 (0.94–1.02) |
| 1–2 mA | 29, 10 | 1.01 (0.98–1.10) | 0.99 (0.95–1.06) |
| 2–3 mA | 5, 4 | 0.87 (0.84–1.16) | 1.06 (0.83–1.69) |
| 3–4 mA | 2, 2 | **1.19 (1.18–1.21)** | **2.04 (1.27–2.82)** |

- **Practical reading.** A Lower LFP Threshold captured at 160 µs and ≤3 mA on the right 0–3 pair
  would not, on this evidence, be inflated by artefact. Above 3 mA it may be, as the guide says.
  The record has no ≤60 µs data to show that a narrower pulse would do better.
- **D27 stays as written.** Making it advisory for RCS08 below 3 mA would be a ruling for the PI,
  and it would rest on two days above 3 mA and no matched ≤60 µs data.

## What would answer question 1 directly

One short block at a visit: right side, 0–3 sensing pair, 55 Hz, holding current at 0, 1, 2, 3 and
4 mA for 60 s each, once at 60 µs and once at 160 µs, contacts unchanged. That is 10 holds, about
12 minutes with ramps. It gives the matched comparison this record lacks, on one day (so it would
need repeating on a second day before it counts as established).

## Files

- `scripts/extract.py` reads the exports (path as an argument; nothing named is written).
  `scripts/steps.py` holds the shared functions; `steps4.py` builds the steps; `final*.py` build
  the tables above. Run with the study's Python: `~/.venvs/bravo-stim-rl/bin/python -I`.
- `matched.csv`, `descriptive.csv`: the derived tables. No recordings or patient data are in this
  folder.
