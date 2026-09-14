# Method contest, entry C: classical process identification and lambda tuning (`fopdt_lambda`)

**Written 2026-09-13.** Participant RCS08, the two left-sided sensing contacts at 24.5 Hz, never
pooled. Every number below was measured today by the scripts named in section 6; nothing is carried
forward from another document.

**Where this lives, and whether anyone can see it.** These nine numbers are settings a clinician
types into the Medtronic tablet. Nothing on this platform writes to the device. On the platform they
show up on the **Closed-Loop Deployment page**, in the "Full parameter recommendation" card and in
the "CL-DBS simulations" card at the foot of the page, which replays the controller using an onset
and two transition durations. **This report itself is a file in `artifacts/` that no page reads.**

---

## 1. The method, in five sentences

I treated the stimulation current as the knob and the 3-second band power as the measurement, which
is the ordinary setup of an industrial control loop. Every moment the current changed inside one
recording is a step test, so I fitted each one with the standard three-number process model — how
far the measurement moves per milliamp (the gain), how long it takes to get there (the time
constant), and how long before it starts moving at all (the dead time) — and separately measured how
much the band power scatters when the current is *not* changing (the noise). Lambda tuning then says:
pick one number, the time you want the loop to take to make its move, set it to at least three or
four times the loop's dead time depending on how much you trust the model, and every other setting
falls out of it — the device's ramp *is* that move, so the ramp duration is that number; the dead
time is the floor under the onset, because deciding faster than the dead time is deciding on the
previous setting; and the noise band fixes how far apart the two thresholds have to be and how long
the averaging window has to be. **The step tests failed to identify the process** — there are one to
five usable steps per band and the smallest change they could have seen is 20 to 30 times larger
than the whole effect — so the gain, the time constant and the plant's own dead time are all
unknown, and the tuning that follows rests on the measurement chain and the noise alone. That gives
settings that are slow and safe by construction, and the honest summary is that this record can tell
you how to keep the loop from chasing noise but cannot tell you whether the loop would do anything
useful.

---

## 2. The model I fitted, with its numbers

### 2a. The step tests, and why they cannot identify anything

A usable step is a current change with the current exactly constant for a few readings before and a
few after, and every band-power reading present. Counting them four different ways, on the 70/30
training set:

| Window (readings before / after) | Usable steps, L 1⁻3⁺ | Usable steps, L 0⁻2⁺ | Smallest change the test could see, at two standard errors |
|---|---|---|---|
| 3 / 5 | 3 | 2 | 294.4 units (L 1⁻3⁺) · 162.6 (L 0⁻2⁺) |
| 5 / 8 | 3 | 1 | 269.8 · 149.0 |
| 5 / 10 | 2 | 0 | 235.5 · 130.1 |
| 3 / 10 | 2 | 0 | 263.3 · 145.4 |

**The second column of that table is the whole finding.** The band power scatters by 161 units
(L 1⁻3⁺) and 89 units (L 0⁻2⁺) between one 3-second reading and the next at a constant current, so
comparing a five-reading average with an eight-reading average carries an uncertainty of about 135
and 75 units respectively, and **twice that — 270 and 149 units — is the smallest step the test
design could have distinguished from nothing.** The largest steady-state effect anywhere in this
record is about 16 units per milliamp (section 2b), so a 0.5 mA step moves the band by about 8
units. **The test is 20 to 34 times too blunt to see it.**

The fits behave exactly as that predicts. Across the three splits the fitted gain ranges from −25.0
to +3133.5 units per milliamp on L 1⁻3⁺ and is a single value of −57.0 on L 0⁻2⁺; the time constant
sits on its lower bound of 1 second in every fit; the dead time comes out 0 s (L 1⁻3⁺) and 6 s
(L 0⁻2⁺); and the fit quality is **negative** in most fits — median −0.055 to −0.626 — which means
the fitted curve describes the response window worse than a flat line through its own average does.
One of three fits, and none of one, is better than a flat line.

**The placebo control settles it.** I computed the same statistic at 400 windows where the current
did **not** change. A pure-noise pair of short windows moves by a median of 0.65 to 0.78 of the
scatter, its top tenth reaches 1.9 to 2.2, and **75 to 80 per cent of them reach 0.30 of the scatter
or more.**

> **The Phase 10 figure — that a 0.5 mA step moves the band by 0.30 to 0.46 of its scatter — is
> refuted as evidence of a response. That range is *smaller* than what two short windows produce by
> chance when nothing at all has changed.** It is not wrong as an arithmetic summary of those
> windows; it simply is not a measurement of the band's response to current.

### 2b. The steady-state gain, from far more data

Pooling every settled constant-current segment, with one intercept per recording so that the
comparison is within a recording and never across days:

| Split | L 1⁻3⁺ gain (units per mA) | recordings with two currents | L 0⁻2⁺ gain | recordings |
|---|---|---|---|---|
| 70/30 | −0.21 ± 4.06 | 6 | −16.38 ± 4.92 | **1** |
| 60/40 | −8.78 ± 1.62 | 5 | −16.38 ± 4.92 | **1** |
| 80/20 | −3.63 ± 3.69 | 7 | −16.38 ± 4.92 | **1** |

On L 1⁻3⁺ the estimate moves by a factor of forty between splits and its uncertainty spans zero at
two of the three. On L 0⁻2⁺ **exactly one recording in the whole training set holds two different
currents**, so there is no replication at all and the standard error is meaningless. The sign is
negative wherever it is estimable, which is the direction the control law needs, but it is not
established.

### 2c. The noise, which the record *can* identify

This is the stable half of the model. Measured inside constant-current runs, each run centred on its
own average so that drift between recordings cannot masquerade as noise:

| | L 1⁻3⁺ (70/30 · 60/40 · 80/20) | L 0⁻2⁺ (70/30 · 60/40 · 80/20) |
|---|---|---|
| scatter of one 3 s reading | 161.26 · 162.02 · 160.63 | 89.07 · 89.10 · 89.20 |
| correlation with the next reading | 0.2005 · 0.2016 · 0.2009 | 0.0999 · 0.0997 · 0.1002 |
| readings behind it | 31,708 · 30,888 · 32,231 | 30,397 · 29,741 · 30,647 |

Three digits of agreement across splits. The correlation with the next reading corresponds to a
signal time constant of **1.86 seconds (L 1⁻3⁺) and 1.30 seconds (L 0⁻2⁺) — shorter than the
3-second sampling interval itself**, so whatever the tissue's real time constant is, the exported
series carries no memory of it beyond a single reading.

What averaging buys (scatter of the average of N readings, measured, not assumed):

| Averaging | 3 s | 6 s | 9 s | 15 s | 30 s |
|---|---|---|---|---|---|
| L 1⁻3⁺ | 161.03 | 124.67 | 108.27 | 92.84 | **76.57** |
| L 0⁻2⁺ | 88.95 | 65.72 | 55.42 | 45.66 | **34.63** |

**Against the thresholds stored today: on L 1⁻3⁺ the 30-second noise band (76.57) is 1.57 times the
entire gap between the two thresholds (48.68). On L 0⁻2⁺ it is 6.63 times the gap (5.24).** Even at
the documented maximum averaging, noise alone carries the signal across the whole threshold band
routinely.

### 2d. The level, and the start-of-recording dip

The 30-second averaged readings themselves — including the drift between recordings — spread far
more widely than the fast noise: L 1⁻3⁺ standard deviation 157.09, tenth percentile 106.1, ninetieth
492.0; L 0⁻2⁺ 71.78, 123.4, 306.5. And the participant's own middle level is **247.50** on L 1⁻3⁺
against a stored threshold midpoint of **186.24** — the stored pair is not centred on the level the
signal actually sits at, by more than the width of the pair itself. On L 0⁻2⁺ they nearly agree
(196.05 against 193.51).

At the start of a recording the first three readings on L 1⁻3⁺ read low by 0.47, 0.44 and 0.40 of
the scatter, each more than two standard errors from zero over 84–85 recordings; the fourth reading,
at 9 seconds, is no longer distinguishable. On L 0⁻2⁺ no reading is distinguishable (the standard
errors are about 0.42).

### 2e. The lambda arithmetic

| Step | Value | Where it comes from |
|---|---|---|
| Averaging window | 30 s | The documented maximum. Forced by 2c: even at 30 s the noise band is wider than the threshold gap, so there is no reason to average less. |
| Dead time of the measurement chain | 30 s | The standard half-rule: an averaging window of A seconds behaves as A/2 of dead time plus A/2 of lag, and a controller that acts once per window adds another A/2 of dead time. A/2 + A/2 = A. |
| Dead time of the tissue | ≤ 3 s, carried at 3 s | Not resolvable: the fits give 0 s and 6 s from one and three usable steps, and nothing below one 3-second reading can be seen at all. Carried at its upper bound. |
| Onset floor | 60 s (two windows) | The loop must not decide faster than its own 33 s of dead time; 60 s is the first whole averaging window past it. |
| Total loop dead time | 93 s | 33 s of measurement and tissue, plus 60 s of confirmation. |
| **Lambda** | **372 s** | The skill's own table: four times the dead time when model confidence is LOW. It is low — the plant is unidentified. |
| Transition up and down | 360 s (6 min) | The device's ramp *is* the closed-loop move, so the ramp duration is lambda, rounded to the half minute. |
| Filter consistency check | **passes** | The standard one-tenth rule wants the averaging no longer than a tenth of lambda: 30 s against 37.2 s. |
| Blanking | 60 s | The first decision made on genuinely fresh information is one dead time later; 60 s is the first whole window past 33 s. |
| Threshold half-width | k × the 30 s noise scatter, about the participant's own middle level | See below. |

**The threshold rule, stated once and applied identically to both bands and all three splits:** the
half-width is the smallest k on the grid whose **measured** current-change rate on the training
recordings is at or under one an hour, subject to the lower threshold staying above zero, because a
band power cannot be negative and a negative number cannot be entered on the tablet. If no band with
a positive lower threshold reaches the target, the largest one that is still programmable is taken
and the rate it does reach is reported rather than hidden.

The trade-off this rule is choosing from, measured on the 70/30 training recordings at the 60 s
onset:

| Half-width k | L 1⁻3⁺ band (lower … upper) | changes/h | L 0⁻2⁺ band | changes/h |
|---|---|---|---|---|
| 1.75 | 113.5 … 381.5 | 6.46 | 135.2 … 256.9 | 8.31 |
| 2.50 | 56.1 … 438.9 | 2.96 | 109.2 … 282.9 | 4.01 |
| **3.00** | **17.8 … 477.2** | **2.74** | 92.3 … 299.8 | 3.31 |
| 3.50 | −20.5 … 515.5 (**not programmable**) | 2.66 | 74.4 … 317.7 | 2.82 |
| **5.00** | −135.3 … 630.3 (**not programmable**) | 1.52 | **22.3 … 369.8** | **0.56** |
| 7.00 | −288.4 … 783.4 (**not programmable**) | 0.34 | −47.2 … 439.3 (**not programmable**) | 0.04 |

So: **on L 0⁻2⁺ the target is met at k = 5.0. On L 1⁻3⁺ it is not met by any programmable band** —
the widest band whose lower threshold is still a positive number is k = 3.0, and it still switches
2.74 times an hour. That is a real limit of this record and this contact, not a tuning failure:
the level of the band power moves so much between recordings that no fixed pair of thresholds can
both sit inside the signal and be crossed less than once an hour.

---

## 3. The scoring rule's numbers

### 3.0 The split

Sorted by start time, the first fraction of stretches by count is TRAINING.

| Band | Total | Split | TRAIN stretches / hours | TEST stretches / hours |
|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 330 stretches, 31.59 h | 70/30 | 231 / 27.62 | 99 / 3.97 |
| | | 60/40 | 198 / 26.77 | 132 / 4.82 |
| | | 80/20 | 264 / 28.24 | 66 / 3.35 |
| L 0⁻2⁺ 24.5 Hz | 296 stretches, 27.42 h | 70/30 | 207 / 26.34 | 89 / 1.08 |
| | | 60/40 | 178 / 25.63 | 118 / 1.79 |
| | | 80/20 | 237 / 26.74 | 59 / 0.69 |

**Read the hours, not the stretch counts.** Splitting by count in time order puts 87 per cent of the
recorded time in TRAINING at the 70/30 split on L 1⁻3⁺ and **96 per cent** on L 0⁻2⁺, because the
early recordings are the long ones. The L 0⁻2⁺ test set is **one hour of signal**, and at 80/20 it is
41 minutes. Every test number for that band rests on that.

### 3.1 Prediction: one step ahead on TEST, in the device's own units

The model is the identified plant (the steady-state gain times the current) plus a tracked local
level and a lag-1 term, both fitted on TRAINING only. "Variance explained" is 1 − RMSE² / TEST
variance. The TEST-mean baseline is 0.000 by construction; it is the yardstick, not a competitor.

**L 1⁻3⁺ at 24.5 Hz**

| Split | readings scored | TEST variance | **my model** | my model with the current term removed | persistence | TEST mean |
|---|---|---|---|---|---|---|
| 70/30 | 4,447 | 25,725 | **151.45 (+0.108)** | 151.45 | 186.46 (−0.352) | 160.39 (0.000) |
| 60/40 | 5,395 | 26,096 | **148.40 (+0.156)** | 148.33 | 182.43 (−0.275) | 161.54 (0.000) |
| 80/20 | 3,769 | 27,322 | **154.49 (+0.126)** | 154.49 | 192.45 (−0.356) | 165.29 (0.000) |

**L 0⁻2⁺ at 24.5 Hz**

| Split | readings scored | TEST variance | **my model** | without the current term | persistence | TEST mean |
|---|---|---|---|---|---|---|
| 70/30 | 1,116 | 11,147 | **103.48 (+0.039)** | 103.13 | 122.14 (−0.338) | 105.58 (0.000) |
| 60/40 | 1,909 | 10,052 | **97.15 (+0.061)** | 96.94 | 117.31 (−0.369) | 100.26 (0.000) |
| 80/20 | 708 | 10,322 | **101.97 (−0.007)** | 101.59 | 119.31 (−0.379) | 101.60 (0.000) |

Three things to read off this table, and the third is the important one.

1. **The model beats persistence on every split of both bands**, by 19 to 22 per cent of the error.
   But persistence is a low bar here: it is *worse than the plain average*, on every split, which is
   the signature of a series with almost no memory. Beating it proves the readings are close to
   independent draws, not that the model has learned dynamics.
2. **The model barely beats the TEST mean.** It explains 4 to 16 per cent of the variance, and on
   L 0⁻2⁺ at 80/20 it explains **−0.7 per cent**, which is worse than doing nothing. The whole gain
   comes from the tracked level, which is an admission that the level drifts and nothing else is
   predictable.
3. **The current term contributes nothing.** With the identified gain in and with it removed the
   error agrees to two decimals on L 1⁻3⁺ (151.45 against 151.45, and 148.40 against 148.33), and on
   L 0⁻2⁺ removing it makes the prediction **better** on all three splits (103.48 → 103.13,
   97.15 → 96.94, 101.97 → 101.59). **On this record the stimulation current has no measurable
   effect on the next band-power reading.**

### 3.2 Controller: the Dual Threshold replay on TEST

Primary table: the averaging window is emulated, so the controller runs on the device's own 30-second
grid, as the real device does. All three settings use a 30-second averaging window, so all three are
compared on the same grid. "Reversals" counts a state change undone within one onset duration.

**Two things must be read with this table.** First, emulating a 30-second averaging window needs a
recording at least two windows long, so short recordings drop out: on L 1⁻3⁺ 20 of 99 recordings
survive but they carry **3.38 of the 3.97 test hours**; on L 0⁻2⁺ only 5 of 89 survive, carrying
**0.52 of 1.08 hours**, so that band's controller score rests on five recordings and half an hour.
Second, at a 30-second grid **any transition duration of 30 seconds or less completes inside one
controller step**, which is why the device's 4-second ramp and the Phase 10 30-second ramp give
identical numbers to every digit — the replay cannot tell them apart.

**L 1⁻3⁺ at 24.5 Hz, 70/30 split** (TEST 3.38 h over 20 recordings)

| Setting | changes/h | reversals | at upper limit | at lower limit | between | mean current | TEST readings inside the band |
|---|---|---|---|---|---|---|---|
| **fopdt_lambda (mine)** | **0.30** | **0** | 0.0 % | 0.0 % | 100.0 % | 3.102 mA | 97.5 % |
| device GROUP_D today | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 21.2 % |
| Phase 10 recommendation | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 21.2 % |

**L 1⁻3⁺, the other two splits**

| Split | Setting | changes/h | reversals | upper | lower | between | mean mA | inside band |
|---|---|---|---|---|---|---|---|---|
| 60/40 (4.04 h) | mine | 0.25 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.102 | 97.7 % |
| | GROUP_D | 38.10 | 54 | 83.5 % | 14.8 % | 1.6 % | 4.267 | 19.8 % |
| | Phase 10 | 38.10 | 54 | 83.5 % | 14.8 % | 1.6 % | 4.267 | 19.8 % |
| 80/20 (2.96 h) | mine | 0.34 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.102 | 96.9 % |
| | GROUP_D | 39.21 | 42 | 90.7 % | 8.2 % | 1.1 % | 4.503 | 21.7 % |
| | Phase 10 | 39.21 | 42 | 90.7 % | 8.2 % | 1.1 % | 4.503 | 21.7 % |

**L 0⁻2⁺ at 24.5 Hz** (test hours 0.52, 1.05, 0.31 — thin, see the warning above)

| Split | Setting | changes/h | reversals | upper | lower | between | mean mA | inside band |
|---|---|---|---|---|---|---|---|---|
| 70/30 | mine | 0.00 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.100 | 95.2 % |
| | GROUP_D | 34.84 | 5 | 82.3 % | 17.7 % | 0.0 % | 4.197 | 1.6 % |
| | Phase 10 | 34.84 | 5 | 82.3 % | 17.7 % | 0.0 % | 4.197 | 1.6 % |
| 60/40 | mine | 0.00 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.100 | 96.8 % |
| | GROUP_D | 39.05 | 7 | 67.5 % | 32.5 % | 0.0 % | 3.694 | 4.8 % |
| | Phase 10 | 39.05 | 7 | 67.5 % | 32.5 % | 0.0 % | 3.694 | 4.8 % |
| 80/20 | mine | 0.00 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.100 | 94.6 % |
| | GROUP_D | 32.43 | 2 | 86.5 % | 13.5 % | 0.0 % | 4.341 | 2.7 % |
| | Phase 10 | 32.43 | 2 | 86.5 % | 13.5 % | 0.0 % | 4.341 | 2.7 % |

**Secondary table, averaging not emulated** (the controller runs on the raw 3-second grid, which
keeps 97 of 99 and 87 of 89 recordings and all the test hours; 70/30 split). This is a diagnostic,
not the device:

| Band | Setting | changes/h | upper | lower | mean mA | inside band |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ | mine | 0.00 | 0.0 % | 0.0 % | 3.100 | 89.9 % |
| | GROUP_D | 2.27 | 67.3 % | 0.0 % | 4.244 | 18.5 % |
| | Phase 10 | 2.27 | 66.5 % | 0.0 % | 4.237 | 18.5 % |
| L 0⁻2⁺ | mine | 0.00 | 0.0 % | 0.0 % | 3.100 | 90.8 % |
| | GROUP_D | 3.71 | 32.9 % | 0.5 % | 3.649 | 3.1 % |
| | Phase 10 | 3.71 | 31.9 % | 0.0 % | 3.652 | 3.1 % |

**What the controller table says, plainly.** The settings running on the device today, and the
Phase 10 recommendation, put the stimulation at one of its two limits **98.3 per cent of the time**
on L 1⁻3⁺ and **100 per cent** on L 0⁻2⁺, changing about 39 times an hour with about 50 of those
changes undone within a single onset duration. That is not a controller tracking a signal; it is a
controller being thrown between its stops by noise, because 79 to 98 per cent of the readings sit
outside the threshold band. My settings switch **0.00 to 0.34 times an hour with no reversals at
all**, and the cost is that the current then sits at neither limit and averages 3.10 mA, the midpoint
of the 1.4–4.8 mA range — **the loop is almost inert.** Given that section 3.1 found the current has
no measurable effect on the band power, an almost-inert loop is the defensible answer, not a failure;
but it must be said out loud that it is close to open-loop stimulation at a fixed middling current.

### 3.3 Robustness across the split

| Recommendation | L 1⁻3⁺ at 70/30 · 60/40 · 80/20 | Moves? |
|---|---|---|
| Averaging | 30 s · 30 s · 30 s | no |
| Onset up and down | 60 s · 60 s · 60 s | no |
| Blanking | 60 s · 60 s · 60 s | no |
| Transition up and down | 360 s · 360 s · 360 s | no |
| Startup delay | 60 s · 60 s · 60 s | no |
| Upper threshold | 477.18 · 480.76 · 476.64 | **moves 4.12 units** |
| Lower threshold | 17.81 · 18.00 · 18.48 | moves 0.67 units |

| Recommendation | L 0⁻2⁺ at 70/30 · 60/40 · 80/20 | Moves? |
|---|---|---|
| Every timing | identical (30 / 60 / 60 / 360 / 30 s) | no |
| Upper threshold | 369.77 · 370.10 · 370.86 | **moves 1.09 units** |
| Lower threshold | 22.33 · 22.03 · 21.86 | moves 0.47 units |

**Every timing value is identical across all three splits on both bands — robust by the brief's
rule.** Of the four threshold values, two move by more than the one-unit yardstick the brief sets
(the upper threshold on both bands, by 4.12 and 1.09 units) and two do not. **So: the timings are
robust; the upper threshold is not, by that yardstick.** The half-width multiplier itself never
moved — k = 3.0 on L 1⁻3⁺ and k = 5.0 on L 0⁻2⁺ at all three splits — so the movement comes entirely
from the participant's own middle level shifting by one or two units between splits.

### 3.4 Cost

Wall clock on the container, from the scripts' own timers. Identification and the noise model:
**0.010 to 0.020 seconds** per band per split. The whole fit including the training-set replays that
choose the threshold band: **1.58 to 2.15 seconds** per band per split. The complete run — six band
and split combinations, fitting plus the prediction score plus 36 replays — **45.1 seconds**.

---

## 4. The nine recommended settings, per band

Confidence is High only where a number is fixed by something measured with thousands of readings and
identical across splits; Medium where a measurement fixes it but the measurement rests on tens of
recordings; Low where the record could not measure the quantity that should decide it.

### L 1⁻3⁺ at 24.5 Hz

| Parameter | Recommend | Reason, one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **30 s** | The documented maximum, and forced: even at 30 s the noise band (76.57 units) is 1.57 times the entire gap between today's two thresholds, so averaging less would leave the loop more noise-driven still. | **High** — measured on 31,708 readings, agreeing to three digits across splits |
| Onset, upper timer | **60 s** | The loop's own dead time is 33 s (30 s from the averaging window and the once-per-window action, plus the tissue's dead time carried at its 3 s upper bound), and deciding faster than that is deciding on the previous setting; 60 s is the first whole averaging window past it. | **High** — the 33 s is arithmetic on the averaging window, not an estimate |
| Onset, lower timer | **60 s** | Same floor, and the record gives no reason to treat the two directions differently: the noise crosses upward and downward at rates that pick the same value of the threshold multiplier. | **High** |
| Transition up | **360 s (6 min)** | Lambda tuning's one knob is the time the loop should take to make its move, set at four times the 93 s total dead time because model confidence is low, and the device's ramp *is* that move. | **Medium** — the arithmetic is sound but the multiplier of four is a rule of thumb, and the plant it is protecting against is unidentified |
| Transition down | **360 s (6 min)** | The same number; the record shows nothing that distinguishes the two directions, and making the down-ramp faster would be a safety choice rather than a measured one. | **Medium** |
| Detection blanking | **60 s** | A decision must not be re-examined until the information behind it is fresh, which is one dead time (33 s) later, so 60 s is the first whole window past it; this also matches the manufacturer's own direction to lengthen blanking until the loop stops ramping straight back. | **Medium** — derived from the dead time, not measured directly |
| Adaptive startup delay | **60 s** | The first averaging window must contain no pre-start data (30 s) and the record shows the first three readings after a recording begins sit low by 0.40–0.47 of the scatter, each more than two standard errors over 84–85 recordings, with the fourth reading at 9 s already normal — 30 + 9 s rounded up to a whole window. | **Medium** — 85 recordings, and whether the dip is the device or the tissue is unknown |
| Upper threshold | **477** device units | Three noise standard deviations above the participant's own middle 30-second reading (247.50), which is the widest band whose lower threshold is still a positive, programmable number. | **Low** — see the warning below |
| Lower threshold | **18** device units | The same three standard deviations below; note this is only 18 units above zero, so the band is nearly one-sided. | **Low** — see the warning below |

> **Warning on the two thresholds for this contact, which the method found and cannot fix.** The
> rule asks for a band the noise crosses at most once an hour. **No programmable band achieves it
> here.** The widest one with a positive lower threshold still switches 2.74 times an hour on the
> training recordings, and the one that would meet the target needs a lower threshold of −135 device
> units, which cannot be entered. The reason is in section 2d: the participant's 30-second readings
> run from about 106 to about 492 units between the tenth and ninetieth percentiles, so the level
> itself moves further than any fixed band can absorb. **Separately, the stored pair today is
> centred 61 units below the level the signal actually sits at, which is more than the pair's own
> width — that alone explains why today's settings pin the current at a limit 98 per cent of the
> time.** The thresholds should be captured again, at this contact, before any of this is programmed.

### L 0⁻2⁺ at 24.5 Hz

| Parameter | Recommend | Reason, one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **30 s** | Same rule and a stronger case: the 30-second noise band is 34.63 units against a stored threshold gap of 5.24, so noise crosses the whole gap 6.6 times over. | **High** — 30,397 readings, three digits stable |
| Onset, upper timer | **60 s** | The same 33 s dead-time floor rounded up to a whole averaging window. | **High** |
| Onset, lower timer | **60 s** | The same. | **High** |
| Transition up | **360 s (6 min)** | The same lambda: four times a 93 s dead time. | **Medium** |
| Transition down | **360 s (6 min)** | The same. | **Medium** |
| Detection blanking | **60 s** | The same one-dead-time rule. | **Medium** |
| Adaptive startup delay | **30 s** | One averaging window, so the first estimate holds no pre-start data; unlike the other contact, **no** reading at the start of a recording is distinguishable from the rest here (the offsets are 0.32–0.75 of the scatter with standard errors of about 0.42), so nothing argues for adding more. | **Medium** — 74 recordings, and the check has little power |
| Upper threshold | **370** device units | Five noise standard deviations above the participant's own middle reading (196.05); this is the smallest band that meets the rule — 0.56 noise-driven current changes an hour on the training recordings. | **Medium** — the rule is met and k = 5.0 at all three splits; the value itself moves 1.09 units between splits |
| Lower threshold | **22** device units | The same five standard deviations below, still a positive programmable number. | **Medium** — moves 0.47 units between splits |

> **Warning on this contact's stored thresholds.** 196.13 and 190.89 are 5.24 units apart on a signal
> whose 30-second noise alone is 34.63 units. That is a single threshold in all but name, and the
> replay shows the consequence: the current sits at one limit or the other **100 per cent** of the
> time, on every split.

### The recommendation that matters more than the nine numbers

**Do not run adaptive stimulation on either band on this evidence yet.** Section 3.1 found the
current has no measurable effect on the next band-power reading — removing it from the model changes
the error by nothing, or improves it. Section 2a found the record's step tests are 20 to 34 times too
blunt to have seen the effect even if it is there. A loop needs a gain with a known sign and size;
this record supplies neither. The settings above are what a control engineer would program to keep
such a loop from doing harm while the evidence is gathered — slow, wide, and almost inert — and the
thing to do instead of programming them is the titration session already written up as open item 30:
one rate, 0.5 mA steps from zero to the side-effect level, at least 60 seconds at each step, up and
then down, streaming throughout. With 60-second holds the same step test would see a change of about
40 units instead of 270, which is the range where the effect would actually be visible.

---

## 5. What this method cannot tell from this record

1. **The process gain, its sign, and its size.** One to five usable steps per band; the smallest
   change the design could see is 20 to 34 times the largest plausible effect; the steady-state gain
   moves by a factor of forty between splits on one contact and rests on a single recording on the
   other. Everything lambda tuning would normally derive from the gain — most importantly, the ramp
   duration — is therefore derived from the measurement chain instead, which is why the ramp
   recommendation is Medium and not High.
2. **The tissue's own time constant and dead time.** The measured signal's memory runs out inside a
   single 3-second reading (a time constant of 1.3 to 1.9 seconds), so anything faster than 3 seconds
   is invisible, and the fitted time constant sat on its lower bound in every step fit.
3. **Whether the loop would help the patient.** Nothing here touches pain. The replay assumes the
   band power would have been the same under closed-loop control as it was under the participant's
   real programming, which is false exactly when the band responds to current — the module's own
   documentation says so.
4. **The right absolute placement of the thresholds.** The method can size the *gap* from the noise;
   it cannot say where the pair should sit, because that comes from the device's threshold-capture
   procedure at a low and a high current, and this record holds no capture I could redo. The best it
   can say is that today's pair on L 1⁻3⁺ is 61 units below the participant's own level.
5. **Anything about the right-hand side.** The right sensing channel is driven by the left signal
   (it is ganged), and every number here is a left-signal number.
6. **Whether the start-of-recording dip is the device or the tissue**, and therefore whether the
   startup delay is protecting against an artefact or a real settling.
7. **Transition durations of 30 seconds or less, told apart.** At a 30-second averaging window they
   all complete inside one controller step, so the replay scores them identically — which is exactly
   why the device's present 4 s and the Phase 10 30 s produce the same six numbers in section 3.2.
8. **Whether the recommended thresholds are inside the device's documented range.** That range is
   given in µVrms (0.55–400) and these series are in the device's own linear units, with no
   conversion available here, so the only constraint I could check is that a threshold must be a
   positive number.
9. **The L 0⁻2⁺ controller score, with any confidence.** Emulating the 30-second averaging window
   leaves five test recordings and half an hour on that band at the 70/30 split, and 0.31 hours at
   80/20.

---

## 6. The files I wrote

All under `BRAVO/_agent_bridge/_probe_tl/_contest/fopdt_lambda/` (gitignored scratch; the container
sees it as `/usr/src/BRAVO/_agent_bridge/_probe_tl/_contest/fopdt_lambda/`). Nothing under
`BRAVO/modules/`, no production file, and no cache entry was touched.

**Scripts**

| File | What it does |
|---|---|
| `s1_identify.py` | Loads and prints every array of both series; splits the stretches by time order; finds the step tests and fits the three-number process model to each; fits the steady-state gain with one intercept per recording and a standard error clustered by recording; measures the noise at constant current. |
| `s2_design.py` | Step-test sensitivity under four window definitions; the smallest step each design could have seen; the placebo control at 400 windows with no current change; the start-of-recording transient; the first pass of the lambda arithmetic. |
| `s3_score.py` | The device's own classify-confirm-blank logic run over the measured noise; the one-step-ahead predictor and its two baselines; the Dual Threshold replay wrapper. |
| `s4_validate.py` | The skill's step 4: replays the first-pass design on the training recordings, finds it misses its own target, and widens the band until the measured rate meets it. |
| `s5_final.py` | The final settings under the single stated selection rule, and the complete scoring tables. |

**Tables**

`c1_step_fits.csv`, `c1_static_gain.csv`, `c1_noise_model.csv`, `c1_splits.csv`,
`c2_step_sensitivity.csv`, `c2_placebo_control.csv`, `c2_noise_decision_rate.csv`,
`c2_start_transient.csv`, `c2_design.csv`, `c2_design.json`, `c3_design_final.csv`,
`c3_noise_decision_rate_statemachine.csv`, `c3_prediction_score.csv`, `c3_controller_score.csv`,
`c4_train_validation_sweep.csv`, `c4_design_validated.csv`, `c4_prediction_score.csv`,
`c4_controller_score.csv`, **`c5_train_sweep.csv`, `c5_design_final.csv`, `c5_prediction_score.csv`,
`c5_controller_score.csv`** — the last four are the ones this report's sections 3 and 4 are read
from; the earlier ones are the working record, including the two intermediate designs that were
superseded and why.

This report: `artifacts/contest_2026-09-13_fopdt_lambda.md`.
