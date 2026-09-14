# Method contest, entry B (`kalman_est`): treating the band power as a slow hidden level watched through noisy 3-second readings

**Written 2026-09-13.** Contestant B of six. Method assigned: state estimation — model the band power
as a slow hidden level plus fast measurement noise, fit by maximum likelihood on TRAINING, test
whether a nonlinear version beats the plain one, and read the device's timing and threshold settings
off the fitted filter. Scored exactly by the contest brief's rule.

**Where this lives and whether anybody can see it.** **Nothing here is on any page.** It is a set of
disposable scripts in the agent scratch folder (`BRAVO/_agent_bridge/_probe_tl/_contest/kalman_est/`,
gitignored) plus this document. The settings it recommends are values a clinician types into the
Medtronic tablet; on the platform they would appear on the **Closed-Loop Deployment page**, in the
**"Full parameter recommendation"** card and in the **"CL-DBS simulations"** card, which replays the
controller with an onset and two ramp durations. Nothing on the platform writes to the device.

---

## 1. The method in five sentences a clinician can follow

Each 3-second band-power reading is treated as a slowly drifting true level plus a large, fast,
meaningless wobble, and the job of the model is to separate the two. A recursive estimator (a Kalman
filter) is fitted to 27 hours of this participant's own recordings by maximum likelihood, which sets
how fast the true level is allowed to drift and how big the wobble is. Once fitted, the estimator
answers four device questions directly: how much past signal a decision should rest on (the
averaging duration), how far apart the two thresholds must sit before the wobble alone stops flipping
the decision (the threshold separation), how long a reading must stay past a threshold before the
level has really moved (the onset duration), and how long the estimator takes to settle from a cold
start (the startup delay). A nonlinear version, in which the size of the wobble is allowed to grow
with the level or with the stimulation current, is fitted alongside and compared by likelihood. Every
recommended setting is then put through the device's own Dual Threshold controller, replayed over
held-out recordings, and reported beside the settings the device runs today.

---

## 2. The model that was fitted, and its numbers

### 2.1 The family of models

All of them are written on the device's own linear units. **The readings are never logged**; what a
model may do is let the *size of the noise* depend on the level or on the current, which is a
statement about the noise, not a transform of the reading.

| Short name | What it says | Free numbers |
|---|---|---|
| L1 local level | the true level is a slow random walk; each reading is the level plus wobble | 2 |
| L2 damped level | the same, but the level is pulled back toward a long-run average | 4 |
| L3 local linear trend | the level plus a drift that is itself allowed to wander | 4 |
| **L4 two components** | a slow level **plus** a faster component that dies away in a few readings, plus wobble | **6** |
| N1 | L4 with the wobble's size depending on the stimulation current | 7 |
| N2 / N8 | the wobble's size depends on the level the filter currently expects (the **extended, nonlinear** filter) | 7 / 5 |
| N3 | the level's own average depends on the stimulation current (a gain term) | 7 |
| N6 / N7 | L3 with the level-dependent wobble, without and with the current term | 5 / 6 |
| N4 / N5 / N9 | combinations of the above | 9 / 8 / 6 |

Each model is started at the first reading of every recording stretch and its likelihood is summed
from the second reading onward, so no arbitrary starting guess enters any of them and the comparison
is like for like. Missing readings are skipped without breaking the recursion. Every fit is on
TRAINING only.

### 2.2 What won, and the honest split between two different questions

**On TRAINING likelihood the nonlinear versions win by an enormous margin.** The brief asked for this
test explicitly, and the answer is unambiguous:

| Band | best linear (log-likelihood) | best nonlinear (log-likelihood) | likelihood-ratio statistic | extra numbers |
|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | L3, −223 854.2 | N7 (wobble grows with level **and** current), −205 949.0 | **35 810.5** | 2 |
| L 0⁻2⁺ 24.5 Hz | L3, −209 299.0 | N9 (same, one state), −193 606.0 | **31 386.0** | 2 |

The fitted growth exponent is the interesting part: on L 1⁻3⁺ the wobble's standard deviation grows
as the level to the power **1.224**, that is, very close to proportional. Band power with a roughly
constant relative scatter is exactly what that describes, and it is why the plain models are so badly
beaten — they are forced to use one wobble size for readings near 20 and readings near 30 000.

**On out-of-sample prediction every one of those nonlinear versions is worse than doing nothing.**
This is the finding that matters, and only the brief's held-out prediction score exposes it:

| Predictor, L 1⁻3⁺, 70/30 split | RMSE (device units) | fraction of TEST variance explained |
|---|---|---|
| persistence (next = last) | 186.47 | **−0.3511** |
| the TEST mean | 160.40 | 0.0002 |
| **L4, two components** | **146.82** | **0.1624** |
| L1 local level | 148.63 | 0.1416 |
| L3 local linear trend | 150.58 | 0.1189 |
| N8 (wobble grows with level) | 169.67 | −0.1187 |
| N6 (L3 + wobble grows with level) | 194.98 | −0.4773 |
| N2 (L4 + wobble grows with level) | 442.48 | −6.6082 |

Two things are going on and they should not be confused. The nonlinear models earn their likelihood
by getting the *spread* of the readings right — how surprised to be by a spike — not by placing the
*middle* of the next reading any better; and because their weight on each new reading now moves with
the level, a spike raises the expected level, which raises the assumed wobble, which mis-weights the
readings that follow. Separately, the local-linear-trend family (L3, N6, N7) fits a drift within each
recording stretch, which lifts its in-sample likelihood but does not carry to the next stretch: the
drift is a per-stretch quantity the parameter count does not see, so AIC cannot catch it and only the
held-out score does.

**So two models are carried forward for two different purposes, and both are named wherever their
numbers are used.** The device's timing and thresholds are read off **L4, two components**, the best
out-of-sample predictor on both bands at all three splits. The statement that the wobble grows with
the level is reported as a finding in its own right and is the reason section 5 says the thresholds
cannot be placed by a single fixed margin everywhere on the scale.

### 2.3 The fitted numbers of the model carried forward (L4), 70/30 split

| | L 1⁻3⁺ 24.5 Hz | L 0⁻2⁺ 24.5 Hz |
|---|---|---|
| slow component, carry-over per 3 s | 0.999906 | 0.999998 |
| slow component, new variance per step | 21.08 | 0.713 |
| fast component, carry-over per 3 s | 0.7291 | 0.8489 (not identified, see below) |
| fast component, new variance per step | 1221.8 | 0.0 |
| wobble variance | 51 443.1 | 42 349.6 |
| weight put on the newest reading once settled | 0.0195 (slow), 0.0432 (fast) | 0.0041 (slow), 0.0 (fast) |
| gap between a reading and what the filter expected, standard deviation | 234.27 | 206.21 |
| uncertainty left on the level once settled, standard deviation | 56.77 | 13.16 |
| **flat average that would suppress the wobble equally** | **196.9 s** | **987.7 s** |
| average age of the readings the estimate rests on | 142.4 s | 441.3 s |
| time for the estimate to cover 63 % / 95 % of a real step | 141 s / 480 s | 522 s / 1062 s |

On L 0⁻2⁺ the fast component's new variance is fitted at zero, so that band is a slow level plus pure
wobble and its carry-over number is not identified — it lands at 0.849, 0.147 and 0.264 on the three
splits without changing anything else. That is stated rather than quoted as a result.

### 2.4 The Riccati cross-check through ctrlsys

The settled weight on the newest reading was computed twice: once by running my own covariance
recursion to its fixed point, and once by handing the same problem to `ctrlsys.sb02md` as a
discrete Riccati equation in its dual form (the matrix passed is the state matrix transposed, the
weighting matrix is the observation row divided by the wobble variance). **The two agree to about
2 × 10⁻⁹ in absolute terms on a matrix whose largest entry is 173 to 2 520 — a relative difference of
about 10⁻¹² — for every model at every split.**

Getting there required one correction worth recording: `sb02md`'s `hinv` argument must be `'I'`, not
`'D'`. With `'D'` it returns the other root of the equation (for the scalar test case, −2.6806
instead of the correct 3.7306). This was found by running it against a scalar and a 2 × 2 case whose
answer I had already obtained by direct iteration, not by assuming the call was right
(`k0b_ctrlsys.py`).

---

## 3. The scoring rule's numbers

### 3.0 The split, stated once

Stretches sorted by start time; the first 70 % by count are TRAINING, the last 30 % TEST.

| Band | TRAIN stretches | TRAIN hours | TEST stretches | TEST hours | TEST readings scored |
|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 231 | 27.39 | 99 | 3.79 | 4 446 |
| L 0⁻2⁺ 24.5 Hz | 207 | 26.17 | 89 | 1.00 | 1 116 |

**A warning about this split that every method in this contest inherits.** Splitting by stretch
*count* does not split the *time*: the later stretches are far shorter, so 96 % of L 1⁻3⁺'s hours and
**96 % of L 0⁻2⁺'s hours are in TRAINING**. L 0⁻2⁺'s whole TEST period is one hour. Everything in
section 3.2 for that band rests on under an hour of recording and should be read accordingly.

### 3.1 Prediction score — predicting the next 3-second reading from the past ones

Scored on every TEST reading that has a previous reading in the same stretch. "Fraction of variance
explained" is 1 − RMSE²/variance against the TEST readings' own variance, as the brief defines it.

**L 1⁻3⁺ 24.5 Hz** (TEST standard deviation 160.42, variance 25 733.8)

| Predictor | RMSE | fraction of variance explained |
|---|---|---|
| persistence (next = last) | 186.47 | −0.3511 |
| the TEST mean | 160.40 | 0.0002 |
| the TRAIN mean | 160.44 | −0.0003 |
| **filter, L4 two components** | **146.82** | **0.1624** |
| filter, L1 local level | 148.63 | 0.1416 |

**L 0⁻2⁺ 24.5 Hz** (TEST standard deviation 105.62, variance 11 156.5)

| Predictor | RMSE | fraction of variance explained |
|---|---|---|
| persistence (next = last) | 122.14 | −0.3371 |
| the TEST mean | 105.58 | 0.0009 |
| the TRAIN mean | 107.14 | −0.0288 |
| **filter, L4 two components** | **98.64** | **0.1278** |
| filter, L1 local level | 99.51 | 0.1123 |

**The filter beats persistence and it beats the mean, so it has learned something about the
dynamics** — but the amount is small, 16 % and 13 % of the variance, and the honest reading of the
same table is that **persistence is much worse than simply guessing the average**. Guessing that the
next reading equals the last one is 35 % worse in squared error than guessing the average. A
3-second reading on this participant carries little information about the next one; almost all of
what a filter can add is the small, slow part underneath.

The same numbers below the project's own spike ceiling (the 99.5th percentile of TRAINING, 1 212.9
and 640.3) tell the same story: L4 reaches 133.89 / 0.1846 and 96.84 / 0.0965. The spikes are not
what the ranking rests on.

### 3.2 Controller score — replaying the device's Dual Threshold controller over TEST

Every row is the same replay code (`ClosedLoopDeployment/simulation.py`, the zero-response curve,
which is the plain replay) over the same TEST stretches of the same band, with the amplitude limits
1.4–4.8 mA. The adaptive startup delay is applied by discarding the first readings of every stretch,
which is what the delay does — no decision is taken during it.

**Two things to know before reading the table.** First, the module's own convention is that a reading
**above** the upper threshold raises the current (`high_power_action = "increase"`); the brief
describes the opposite direction. Every row uses the same convention, so the comparison is fair, but
"time at the upper limit" should be read with that in mind. Second, **a 30-second averaging duration
makes most TEST stretches undecidable**: the controller needs at least two averaging windows, so at
30 s averaging only 19–20 of L 1⁻3⁺'s 99 TEST stretches and 5 of L 0⁻2⁺'s 89 can be replayed at all.
The stretch count and hours used are therefore printed on every row.

**L 1⁻3⁺ 24.5 Hz, 70/30 split**

| Settings | transitions / h | reversals undone within one onset | time at upper limit | at lower limit | between | mean current | TEST readings between the thresholds | hours replayed (stretches used / too short) |
|---|---|---|---|---|---|---|---|---|
| device GROUP_D today (thresholds 167 / 166) | 17.44 | 16 | 93.8 % | 6.2 % | 0.0 % | 4.591 mA | 0.49 % | 3.38 (20 / 77) |
| GROUP_D timing, stored thresholds | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 21.08 % | 3.38 (20 / 77) |
| Phase 10 recommendation | 35.85 | 43 | 90.9 % | 7.3 % | 1.8 % | 4.520 mA | 21.72 % | 3.29 (19 / 74) |
| **kalman_est: averaging 3 s, onset 30 s, stored thresholds** | **2.53** | **0** | **73.6 %** | **0.0 %** | **26.4 %** | **4.359 mA** | **18.53 %** | **3.56 (93 / 0)** |
| kalman_est, but averaging 30 s and onset 180 s | 2.73 | 0 | 68.4 % | 0.0 % | 31.6 % | 4.262 mA | 21.72 % | 3.29 (19 / 74) |
| kalman_est, but onset 60 s | 1.12 | 0 | 35.8 % | 0.0 % | 64.2 % | 3.713 mA | 18.53 % | 3.56 (93 / 0) |

**L 0⁻2⁺ 24.5 Hz, 70/30 split** — one hour of TEST, read with care

| Settings | transitions / h | reversals | at upper | at lower | between | mean current | readings between thresholds | hours (used / too short) |
|---|---|---|---|---|---|---|---|---|
| device GROUP_D today (167 / 166) | 23.23 | 5 | 91.9 % | 8.1 % | 0.0 % | 4.526 mA | 0.00 % | 0.52 (5 / 82) |
| GROUP_D timing, stored thresholds | 34.84 | 5 | 82.3 % | 17.7 % | 0.0 % | 4.197 mA | 1.59 % | 0.52 (5 / 82) |
| Phase 10 recommendation | 30.00 | 4 | 90.0 % | 10.0 % | 0.0 % | 4.460 mA | 3.33 % | 0.50 (5 / 79) |
| **kalman_est: averaging 3 s, onset 30 s, stored thresholds** | **5.61** | **0** | **44.4 %** | **0.0 %** | **55.6 %** | **3.869 mA** | **2.85 %** | **0.71 (84 / 0)** |
| kalman_est, thresholds widened to ± 40 | 2.81 | 0 | 21.4 % | 0.0 % | 78.6 % | 3.473 mA | 33.33 % | 0.71 (84 / 0) |
| kalman_est, but onset 60 s | 0.00 | 0 | 0.0 % | 0.0 % | 100.0 % | 3.100 mA | 2.85 % | 0.71 (84 / 0) |

### 3.3 Where the Phase 10 recommendation and this one actually differ, and why

The Phase 10 report recommends **averaging 30 s with a 30 s onset**. Replayed with the averaging
actually applied, that pair gives **35.85 transitions an hour with 43 of them undone within one
onset** on L 1⁻3⁺ — not the 2.5 an hour the Phase 10 table reports.

The explanation is not a disagreement about the data. The Phase 10 onset sweep
(`_timing/probe_t3_t4c_sweeps.py`) passed the replay only `onset_ms` and left the averaging at the
replay's own 1 200 ms default; its own comment on the device-today line says so. At that setting the
comparison grid stays at 3 s, so Phase 10's "onset 30 s" is **ten confirmations of 3 s each**, while
the device's programmed 30 s averaging turns the same onset into **one single window**. My replay at
3 s averaging and a 30 s onset returns **2.53 transitions an hour**, reproducing Phase 10's 2.5 —
which is the check that this pipeline and that one agree wherever they are asked the same question.

The estimator's own noise simulation says the same thing without touching the replay. Holding the
true level still at the midpoint between the two thresholds and counting the crossings the wobble
alone produces, the smallest threshold separation that keeps false crossings at or below one an hour
is:

| averaging | onset 30 s | onset 60 s | onset 120 s | onset 180 s |
|---|---|---|---|---|
| 3 s | ± 25 | ± 5 | ± 5 | ± 5 |
| 6 s | ± 120 | ± 5 | ± 5 | ± 5 |
| 15 s | never below 1/h on the grid | ± 120 | ± 5 | ± 5 |
| 30 s | never | never | ± 60 | ± 15 |

(L 1⁻3⁺, 70/30; identical to the unit at 60/40 and 80/20.) **Requiring several consecutive readings
on the same side suppresses the wobble far more effectively than averaging them.** Ten 3-second
readings all on one side is a much stronger demand than one 30-second average on one side, even
though both take 30 seconds.

### 3.4 Robustness — the same two scores with the split moved

| Quantity, L 1⁻3⁺ | 60/40 | 70/30 | 80/20 |
|---|---|---|---|
| TEST stretches / hours | 132 / 4.60 | 99 / 3.79 | 66 / 3.19 |
| L4 fraction of variance explained | 0.2055 | 0.1624 | 0.1689 |
| persistence, same | −0.2750 | −0.3511 | −0.3551 |
| flat average the filter is equivalent to | 201.8 s | 196.9 s | 191.4 s |
| separation needed at averaging 3 s, onset 30 s | ± 25 | ± 25 | ± 25 |
| recommended settings, replayed: transitions / h | 3.74 | 2.53 | 1.62 |
| … reversals | 0 | 0 | 0 |
| Phase 10 settings, replayed: transitions / h | 35.74 | 35.85 | 36.45 |

| Quantity, L 0⁻2⁺ | 60/40 | 70/30 | 80/20 |
|---|---|---|---|
| TEST stretches / hours | 118 / 1.69 | 89 / 1.00 | 59 / 0.64 |
| L4 fraction of variance explained | 0.1254 | 0.1278 | 0.1103 |
| persistence, same | −0.3683 | −0.3371 | −0.3771 |
| flat average the filter is equivalent to | 996.2 s | 987.7 s | 982.5 s |
| separation needed at averaging 3 s, onset 30 s | ± 5 | ± 5 | ± 5 |
| recommended settings, replayed: transitions / h | 5.39 | 5.61 | 2.25 |
| … reversals | 0 | 0 | 0 |

**Every one of the nine recommended values in section 4 is identical at all three splits** — not
within one grid step of the device, identical. The fitted numbers behind them move very little too:
on L 1⁻3⁺ the slow component's new variance is 20.86 / 21.08 / 21.50, the fast component's carry-over
0.7276 / 0.7291 / 0.7301, the wobble variance 52 572 / 51 443 / 50 616. On L 0⁻2⁺ the slow variance is
0.691 / 0.713 / 0.728 and the wobble 43 253 / 42 350 / 41 949. What is *not* stable is the fast
component of L 0⁻2⁺, which is fitted at zero size and whose carry-over therefore wanders freely
(0.147 / 0.849 / 0.264); nothing is derived from it.

### 3.5 Cost

Wall clock on TRAINING, from my own timer inside the container, 70/30 split: **51.7 s** to fit the
model carried forward (L4) on L 1⁻3⁺ and **67.0 s** on L 0⁻2⁺. Fitting the whole menu of thirteen
models, which is what the likelihood comparison in section 2.2 required, took **466.2 s** and
**257.2 s**. The trimmed refits for the two robustness splits took 124.8–140.7 s per band per split.
One likelihood evaluation over a 227-stretch, 32 868-reading training panel costs **0.027 s**, which
is what made maximum likelihood affordable here: every stretch is one row of a padded array and the
recursion runs over columns, so one evaluation is one pass over the longest stretch rather than one
pass over every reading.

---

## 4. Recommended settings, per band

The two bands get the same timing and differ only on the thresholds. Values sit inside the documented
ranges where a range exists (FDA SSED P960009/S478 Table 2; averaging from the BrainSense tip cards).

### L 1⁻3⁺ at 24.5 Hz

| Setting | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **3 s** (the shortest this record can speak to; the device's own 1.2 s Dual default is inside the range and this record cannot tell it from 3 s) | The estimator says a decision should rest on about 197 s of history, which is far more than the 30 s maximum the device offers, so the history has to come from the onset instead — and once it does, a long averaging actively hurts, because at 30 s averaging a 30 s onset is one single window and the replay switches 35.85 times an hour with 43 switches undone, against 2.53 times an hour with none at 3 s averaging. | **High** — same direction on both bands, at all three splits, confirmed independently by the noise simulation and by the replay |
| Onset, upper and lower timers | **30 s each** (ten confirmations of 3 s) | Ten consecutive readings on the same side is the shortest demand that holds noise-only false crossings at or below one an hour at this band's stored separation, and the replay gives 2.53 transitions an hour with zero reversals; 60 s is already too slow for this participant, leaving the current mid-ramp 64 % of the time. | **High** — the separation this rule needs is ± 25 at all three splits, and the replay's reversal count is zero at all three |
| Transition up | **30 s** | The filter puts no useful upper bound here — this band's slow level carries over with a time constant of about nine hours, so every ramp on the device's grid is fast compared with it — so the argument is only that the ramp should finish before the next decision could arrive, and onset plus blanking is 60 s. | **Low** — the estimator cannot decide this; the settling time that would needs the titration session (open item 30) |
| Transition down | **30 s** | Same argument; nothing in this record distinguishes the two directions. | **Low**, same reason |
| Detection blanking | **30 s** (equal to the onset) | Blanking shorter than the onset would let a decision be re-classified while the ramp it triggered is still running; the manufacturer's own troubleshooting direction (A610 Table 16) is to lengthen blanking until an immediate ramp-back stops, which is the same rule. | **Low** — no measurement at 3-second resolution can separate this from the onset |
| Adaptive startup delay | **15 s** | The record's first 12 s of sensing read low, and 15 s covers it; the filter's own settling time is much longer (its weight on new readings is within 5 % of settled after 270 s) but that number is about how precisely the level is known, not about a start-up artefact, and a delay of that length is not a sensible device setting. | **Medium** — the 15 s comes from the Phase 10 measurement, not from my filter; my filter only confirms that 0 is wrong |
| Upper threshold | **210.58** (the stored value; keep) | At 3 s averaging and a 30 s onset the wobble alone produces at most one false crossing an hour once the thresholds are ± 25 apart from their midpoint, and the stored pair is ± 24.3, so it is at the edge of sufficient and no change is needed. | **Medium** — the separation needed is identical at all three splits, but the placement itself is a capture question (decision 139), not one this filter settles |
| Lower threshold | **161.90** (the stored value; keep) | Same. | **Medium**, same |

### L 0⁻2⁺ at 24.5 Hz

| Setting | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **3 s** | Same argument, and stronger here: the estimator wants about 988 s of history, thirty-three times the device's maximum. | **High** |
| Onset, upper and lower | **30 s each** | The replay gives 5.61 transitions an hour with zero reversals against 30.00 with 4 reversals for the Phase 10 pair, and at 60 s the loop stops moving altogether (zero transitions, current pinned mid-range for the whole hour). | **Medium** — the direction is clear but this band's TEST period is 0.71 replayed hours |
| Transition up / down | **30 s each** | As on the other band; nothing in this record distinguishes them. | **Low** |
| Detection blanking | **30 s** | As on the other band. | **Low** |
| Adaptive startup delay | **15 s** | As on the other band. | **Medium** |
| Upper threshold | **at least 198.5, and 233.5 measured better** (stored: 196.13) | The stored pair sits ± 2.62 from its midpoint, below the ± 5 this band's own wobble requires for one false crossing an hour, so it is a single threshold in all but name — only 2.85 % of TEST readings ever fall between the two; widening to ± 40 halves the switching rate, from 5.61 to 2.81 an hour, and puts a third of the readings in the middle state the controller exists to use. | **Medium** on the fact that ± 2.62 is too narrow (identical at all three splits); **Low** on ± 40 being the right width, which is a capture and clinical judgement |
| Lower threshold | **at most 188.5, and 153.5 measured better** (stored: 190.89) | Same. | **Medium / Low**, same |

**Both bands.** The thresholds above are in the same linear device units as the recorded series, not
in the µVrms the FDA range is written in; **no conversion between the two was done here**, so whether
these values sit inside 0.55–400 µVrms is not something this report establishes.

---

## 5. What this method cannot tell from this record

1. **Anything about the ramp durations.** The fitted slow level carries over with a time constant of
   about nine hours on L 1⁻3⁺ and longer on L 0⁻2⁺, so every transition duration on the device's grid
   is fast compared with it and the estimator has no basis to prefer one. The 30 s recommendation
   rests on an argument about not overlapping the next decision, not on a measurement.
2. **Anything shorter than 3 seconds.** The series is on the device's 3 s clock, so the device's own
   1.2 s Dual default and my 3 s recommendation are indistinguishable here.
3. **Whether the start-up dip is the device or the tissue**, and therefore whether a startup delay is
   the right cure for it. The filter's own settling time (270 s to a settled weight, 174 s to a
   settled uncertainty on L 1⁻3⁺) is a different quantity and must not be read as a startup delay.
4. **Whether the wobble really grows with the level, or whether the 1.22 exponent is absorbing the
   device-side spikes.** The likelihood cannot separate those two readings, and the fitted exponent
   on L 0⁻2⁺ comes out *negative* (−2.12) with a degenerate level — a sign that on that band this
   part of the model is not identified. The strong version of this claim should not be made.
5. **Which averaging and onset pair is better once the band responds to the stimulation current.**
   Every replay here uses the zero response curve, so it assumes the same power would have been
   recorded under closed-loop control, which is false exactly when the band responds — the
   assumption the replay's own documentation states.
6. **Anything about L 0⁻2⁺ with much confidence at all.** The brief's split leaves that band one hour
   of TEST recording, and the fast component of its model is fitted at zero size.
7. **The right side.** Only left-side sensing contacts were modelled, and the right sensing channel
   is ganged to the left signal.
8. **Whether any of this improves pain.** Nothing here touches the pain ratings; every score is about
   how the controller behaves, not about whether it helps.

---

## 6. The files written

All under `BRAVO/_agent_bridge/_probe_tl/_contest/kalman_est/` (the container path is
`/usr/src/BRAVO/_agent_bridge/_probe_tl/_contest/kalman_est/`). Scratch, gitignored, disposable.
**No production file was edited and nothing was committed.**

| File | What it is |
|---|---|
| `kf.py` | the three filters (one state, two components, local linear trend), written so one likelihood evaluation is one pass over the longest stretch with every stretch in parallel |
| `common.py` | the stretch split, the padded panel, the parameter transforms, the model menu |
| `k0_inspect.py` | the first look at the arrays: shapes, dtypes, missing readings, the split's stretch and hour counts |
| `k0b_ctrlsys.py` | the `sb02md` convention worked out against a scalar and a 2 × 2 case whose answer is known by iteration |
| `k1_models.py` | the maximum-likelihood fits (`linear`, `ext`, `extended`, `extended2`, `extended3`, `robust`) |
| `k2_derive.py` | settled weights and equivalent averaging window, the Riccati cross-check, cold-start settling, the false-crossing simulation, the filtered level's dwell times, and the prediction score |
| `k3_controller.py` | the Dual Threshold replay over TEST: the two references and the candidate grid |
| `k1_fitted_<contact>_<split>.json` | every fitted model's numbers, likelihood, AIC and fit seconds (6 files) |
| `k2_derived_<contact>_<split>.json` | everything section 3 and 4 quote (6 files) |
| `k2_prediction_<contact>_<split>.csv` | the prediction table, every model and both baselines (6 files) |
| `k2_false_crossings_<contact>_<split>.csv` | false crossings an hour by averaging × onset × separation (6 files) |
| `k3_controller_<contact>_<split>.csv` | the controller replay, every case (6 files) |
| `k1_fit.py` | the superseded first fitting script, kept because it is the run that exposed the local-linear-trend problem; it writes no table (it stopped on an error before that point) and nothing in this report comes from it |

Thirty result files in all: six of each of the five kinds, one per band per split.

This report: `artifacts/contest_2026-09-13_kalman_est.md`.
