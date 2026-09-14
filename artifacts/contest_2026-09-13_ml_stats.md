# Method contest, arm F (`ml_stats`): the statistics-and-machine-learning yardstick

**Written 2026-09-13.** This arm was given no control-theory method on purpose. It is the plain
empirical comparison the five control-theory arms have to beat: learn the signal directly from the
recorded numbers, and pick the device settings by trying them all rather than by deriving them from
a model of how the brain responds.

Participant RCS08, the two sensing contact pairs the PI works with, both at 24.5 Hz, never pooled:
**L 1⁻3⁺** and **L 0⁻2⁺**. Every number below was measured today on her own recordings. Nothing was
written to the production store and no production file was changed.

---

## 1. The method in five sentences

I treat the 3-second brain-signal readings as plain data and never write down an equation for how
the brain works. To describe the signal I fit two ordinary prediction models — a penalised straight-
line fit on the last twenty readings (the last sixty seconds) plus the stimulation current, and
gradient-boosted trees on the same inputs — on the training recordings only, choosing their settings
on a held-out later slice of the training recordings so nothing from the test recordings leaks in.
To choose the device settings I do not derive them: I write down an objective first, then run the
device's own controller over the training recordings for every combination on a grid of onset
duration, the two transition durations, detection blanking and the gap between the two thresholds,
and keep the combination that wins. I then repeat that whole search 200 times on recordings drawn
with replacement — whole recording stretches, never pieces of them — so every recommended value
comes with an interval rather than a single number. Everything is scored exactly by the contest's
rule, with the training and test recordings split by stretch and in time order.

---

## 2. What I fitted, and the fitted numbers

### 2a. The prediction models

Inputs: the twenty most recent 3-second readings (60 s of history) and the stimulation current at
the moment of prediction. Target: the next 3-second reading. Rows are built inside one unbroken
recording stretch only, and a row is used only when all twenty inputs and the target are real
numbers. The penalty strength and the tree settings were chosen on the last 20 % of the training
stretches, then both models were refitted on all the training stretches.

| Band | Penalty strength chosen | Tree setting chosen (leaves, rounds, step) |
|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 1000 | (7, 400, 0.03) |
| L 0⁻2⁺ 24.5 Hz | 1000 | (7, 400, 0.03) |

The one number that summarises the signal's memory: the correlation between one reading and the
next, measured on the test recordings, is **0.33** on L 1⁻3⁺ and **0.25** on L 0⁻2⁺. That is the
whole of the short-term structure there is.

### 2b. The controller search — the objective, written down before the search ran

It is in the header of `s3_search.py`, committed to disk before the grid was run. Among settings on
the device's own grid, keep only those that satisfy all three of these **on the training
recordings**:

- **C1, no chattering:** the number of switches undone within one onset duration is **zero**.
- **C2, a real dead zone:** at least **10 %** of the training readings sit between the two
  thresholds. *Why 10 %:* the device's own programmed pair, 167 and 166, leaves **0.3 %** of
  readings between them — a single threshold in all but name — while the platform's stored pair for
  L 1⁻3⁺ leaves 13 %. Ten per cent is therefore the smallest dead zone this record demonstrably
  supports on the band it was designed for.
- **C3, the loop still does something:** at least **10 %** of training time at the upper current
  limit **and** at least 10 % at the lower one, so that "never switch" cannot win.

Among the settings that pass all three, take the one with the **fewest current changes per hour**.
Ties are broken by: shorter onset, shorter detection blanking, smaller threshold gap, then the
**longest** transition durations (a slower ramp is gentler and, as shown below, changes nothing the
objective can see).

**Why the search splits in two, and this is arithmetic rather than a shortcut.** The sequence of
decisions the controller adopts — and so the number of switches, the number of undone switches, and
the time in each state — is computed from the readings, the two thresholds, the onset and the
blanking only. The two transition durations appear nowhere in it; they only shape the current ramp
that follows a decision already made. So stage 1 sweeps threshold gap × onset × blanking with the
fastest ramps (which puts the most time at the limits, so anything failing C3 there fails it
everywhere), and stage 2 sweeps the two transition durations for the stage-1 winner. **Both claims
were checked numerically, not assumed:** across all 49 transition pairs the number of switches per
hour took exactly **1** distinct value and the number of undone switches exactly **1**, and time at
the upper limit was largest at the fastest ramps in every case.

**The grid.** Onset 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 36, 42, 48, 54, 60, 75, 90, 120 s (the
device's 3-second clock). Threshold gap 0.1 to 1.0 of the signal's own scatter, in eight steps,
placed symmetrically around the midpoint of the stored pair. Detection blanking 3, 15, 30, 60 s.
Each transition 3, 6, 15, 30, 60, 150, 300 s. That is 576 settings in stage 1 and 49 in stage 2.

### 2c. The replay I searched with is proven equal to the platform's own

The search needs thousands of controller replays, so I wrote one that runs many settings at the same
time. Before using it I compared it against `ClosedLoopDeployment/simulation.simulate_series`,
setting by setting and stretch by stretch, on 32 settings × 40 stretches for each band: **35,840
values compared, 0 differing** (exact equality on the whole-number counts, and agreement to one part
in a thousand million on the fractions). It reaches the same answers about **55 times faster**.
Two real differences were found and fixed during that check rather than papered over: how the
distance the current travels is counted on the very first step, and how a switch that happens on the
very first reading is treated when counting undone switches.

---

## 3. The scoring rule's numbers

### 3.0 The training and test split, and a warning about it

Stretches sorted by start time; the first 70 % by count are training, the last 30 % test.

| Band | Split | Training stretches | Training hours | Test stretches | Test hours |
|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 70/30 | 231 | 27.62 | 99 | 3.97 |
| L 1⁻3⁺ 24.5 Hz | 60/40 | 198 | 26.77 | 132 | 4.82 |
| L 1⁻3⁺ 24.5 Hz | 80/20 | 264 | 28.24 | 66 | 3.35 |
| L 0⁻2⁺ 24.5 Hz | 70/30 | 207 | 26.34 | 89 | 1.08 |
| L 0⁻2⁺ 24.5 Hz | 60/40 | 178 | 25.63 | 118 | 1.79 |
| L 0⁻2⁺ 24.5 Hz | 80/20 | 237 | 26.74 | 59 | 0.69 |

**Splitting by the number of stretches puts almost all the recorded time in training.** The median
stretch is **8 readings, 24 seconds** long; a handful of very long early recordings carry most of
the hours. On L 0⁻2⁺ the 70/30 split leaves **1.08 hours** of test recording in 89 stretches, of
which **84 are shorter than the onset duration any method here recommends**. On L 1⁻3⁺ it leaves
3.97 hours in 99 stretches, 79 of them shorter than the onset. This is not a defect in any method;
it is a property of the split the contest fixed, and it makes every long-onset setting look inert on
the test recordings. I report the training numbers beside the test numbers throughout for that
reason.

### 3.1 Prediction: how well the model describes the signal (test recordings)

"Typical error" is the root-mean-square error in the device's own linear units. "Share of the ups
and downs accounted for" is 1 − error²/variance, so the test mean scores exactly zero by
construction.

**L 1⁻3⁺ 24.5 Hz** (test scatter 168.04 units at 70/30)

| Model | 70/30 error | share | 60/40 error | share | 80/20 error | share |
|---|---|---|---|---|---|---|
| Straight-line fit, 20 lags + current | **152.56** | **+0.176** | **147.12** | **+0.217** | **157.04** | **+0.178** |
| Gradient-boosted trees | 153.00 | +0.171 | 147.02 | +0.218 | 157.16 | +0.176 |
| Baseline (a): next = last reading | 194.67 | −0.342 | 188.40 | −0.284 | 201.20 | −0.350 |
| Baseline (b): the test mean | 168.04 | 0.000 | 166.28 | 0.000 | 173.18 | 0.000 |
| Baseline: the training mean | 168.05 | −0.000 | 166.86 | −0.007 | 173.27 | −0.001 |

**L 0⁻2⁺ 24.5 Hz** (test scatter 106.37 units at 70/30)

| Model | 70/30 error | share | 60/40 error | share | 80/20 error | share |
|---|---|---|---|---|---|---|
| Straight-line fit, 20 lags + current | **102.01** | **+0.080** | **91.23** | **+0.121** | **107.27** | **+0.012** |
| Gradient-boosted trees | 103.27 | +0.058 | 92.63 | +0.094 | 108.86 | −0.017 |
| Baseline (a): next = last reading | 130.65 | −0.509 | 117.55 | −0.459 | 137.61 | −0.625 |
| Baseline (b): the test mean | 106.37 | 0.000 | 97.30 | 0.000 | 107.93 | −0.000 |
| Baseline: the training mean | 112.88 | −0.126 | 98.71 | −0.029 | 117.12 | −0.177 |

**What this says, plainly.** Both models beat "next reading equals last reading" by a wide margin on
both bands at every split — but that baseline is a very low bar here, because it is **worse than
simply guessing the average every time**. The honest bar is the average, and against it the models
buy **18 %** of the ups and downs on L 1⁻3⁺ and **8 %** on L 0⁻2⁺ (1 % at the 80/20 split, where
only 322 test rows survive). Trees bought nothing over the straight-line fit anywhere, so there is
no bend or interaction to find. **Roughly four-fifths of what this signal does from one 3-second
reading to the next cannot be predicted from the previous minute of it.** Any method in this contest
that claims to predict this signal well should be checked against these numbers first.

### 3.2 The controller score, my recommendation against the two references

Replayed on the device's 3-second clock with the averaging window not emulated — **the same clock
the Phase 10 sweeps used**, so the references are comparable. A separate averaging table is in §3.5,
and it matters.

**L 1⁻3⁺ 24.5 Hz, 70/30 split**

| Setting | Set | Changes /h | Undone | At upper | At lower | Between | Mean current | Readings between thresholds |
|---|---|---|---|---|---|---|---|---|
| **ml_stats recommendation** | TRAIN | **1.38** | 0 | 0.284 | 0.105 | 0.611 | 3.41 mA | 0.289 |
| device GROUP_D timing, stored thresholds | TRAIN | 2.50 | 0 | 0.453 | 0.279 | 0.267 | 3.40 mA | 0.133 |
| device GROUP_D timing and its own 167/166 | TRAIN | 3.11 | 0 | 0.557 | 0.286 | 0.156 | 3.56 mA | 0.003 |
| Phase 10 recommendation, stored thresholds | TRAIN | 2.50 | 0 | 0.448 | 0.276 | 0.276 | 3.39 mA | 0.133 |
| **ml_stats recommendation** | TEST | **1.01** | 0 | 0.209 | **0.000** | 0.791 | 3.46 mA | 0.387 |
| device GROUP_D timing, stored thresholds | TEST | 2.27 | 0 | 0.673 | **0.000** | 0.327 | 4.24 mA | 0.185 |
| device GROUP_D timing and its own 167/166 | TEST | 4.03 | 0 | 0.623 | 0.087 | 0.290 | 4.01 mA | 0.005 |
| Phase 10 recommendation, stored thresholds | TEST | 2.27 | 0 | 0.665 | **0.000** | 0.335 | 4.24 mA | 0.185 |

**L 0⁻2⁺ 24.5 Hz, 70/30 split**

| Setting | Set | Changes /h | Undone | At upper | At lower | Between | Mean current | Readings between thresholds |
|---|---|---|---|---|---|---|---|---|
| **ml_stats recommendation** | TRAIN | **0.99** | 0 | 0.102 | 0.195 | 0.703 | 2.94 mA | 0.347 |
| device GROUP_D timing, stored thresholds | TRAIN | 2.51 | 0 | 0.311 | 0.412 | 0.277 | 2.93 mA | 0.020 |
| device GROUP_D timing and its own 167/166 | TRAIN | 2.54 | 0 | 0.453 | 0.286 | 0.261 | 3.38 mA | 0.005 |
| Phase 10 recommendation, stored thresholds | TRAIN | 2.51 | 0 | 0.307 | 0.407 | 0.287 | 2.93 mA | 0.020 |
| **ml_stats recommendation** | TEST | **0.00** | 0 | 0.000 | 0.000 | **1.000** | 3.10 mA | 0.386 |
| device GROUP_D timing, stored thresholds | TEST | 3.71 | 0 | 0.329 | 0.005 | 0.666 | 3.65 mA | 0.031 |
| device GROUP_D timing and its own 167/166 | TEST | 4.63 | 0 | 0.403 | 0.005 | 0.592 | 3.78 mA | 0.006 |
| Phase 10 recommendation, stored thresholds | TEST | 3.71 | 0 | 0.319 | 0.000 | 0.681 | 3.65 mA | 0.031 |

**Read the test column with §3.0 in hand, and do not read it as a success.** On L 0⁻2⁺ my setting
makes **no current change at all** on the 1.08 hours of test recording, because 84 of its 89 test
stretches are shorter than the 36-second onset and the controller never gets to confirm anything.
That is the honest cost of an objective whose first term is "fewest changes per hour": it walks to
the edge of the constraint that keeps the loop alive, and the edge does not survive a test set made
of 24-second fragments. On L 1⁻3⁺ the same setting still makes 1.01 changes an hour on test, and
spends 21 % of the time at the upper current limit — but 0 % at the lower one, which is also true of
both references, so it is a property of those 99 test stretches rather than of my setting.

**Where my setting genuinely differs from both references, on 27 hours of training recording:** it
makes **45 % fewer current changes** than the device runs today (1.38 against 2.50 an hour on
L 1⁻3⁺; 0.99 against 2.51 on L 0⁻2⁺) while putting **2.2 to 17 times more of the signal inside the
dead zone** (0.289 against 0.133; 0.347 against 0.020). Every setting in every table, mine and both
references, makes **zero undone switches** — the current device onset of 30 seconds is already long
enough to stop the chattering, and that is worth saying because it means the switching rate, not the
chattering, is the thing left to improve.

### 3.3 Robustness — moving the split

| Band | Split | Onset | Blanking | Threshold gap | Thresholds | Transitions (stated rule) |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 70/30 | 48 s | 3 s | 0.4 scatter (105.9 units) | 239.2 / 133.3 | 300 / 60 s |
| L 1⁻3⁺ | 60/40 | 48 s | 3 s | 0.4 scatter | 239.2 / 133.3 | 300 / 150 s |
| L 1⁻3⁺ | 80/20 | 48 s | 3 s | 0.4 scatter | 239.2 / 133.3 | 300 / 60 s |
| L 0⁻2⁺ | 70/30 | 36 s | 3 s | 0.4 scatter (87.0 units) | 237.0 / 150.0 | 30 / 300 s |
| L 0⁻2⁺ | 60/40 | 36 s | 3 s | 0.4 scatter | 237.0 / 150.0 | 60 / 300 s |
| L 0⁻2⁺ | 80/20 | 36 s | 3 s | 0.4 scatter | 237.0 / 150.0 | 15 / 300 s |

**Onset, blanking, threshold gap and both threshold values do not move at all between the three
splits — not by one grid step, not by one unit.** The two transition durations move by several grid
steps and are **not robust**; I say so plainly. The reason is in §2b: the objective and two of the
three constraints cannot see the transition durations at all, so the tie-break alone is choosing
them, and the tie-break is choosing on a quantity that barely changes. §4 therefore recommends the
transitions on a stability rule instead, stated there.

### 3.4 Robustness — the block bootstrap, which is the number the other arms do not have

200 replicates per band. Each draws as many whole stretches as the training set has, with
replacement, and re-runs the entire stage-1 search and objective on them. Every one of the 400
replicates found a feasible setting.

| Band | Quantity | Point estimate | Bootstrap median | 95 % interval | Grid values ever chosen |
|---|---|---|---|---|---|
| L 1⁻3⁺ | Onset | 48 s | 54 s | **36 – 90 s** | 30, 36, 42, 48, 54, 60, 75, 90 |
| L 1⁻3⁺ | Threshold gap | 0.4 scatter | 0.4 | **0.2 – 0.5 scatter** | 0.2, 0.3, 0.4, 0.5 |
| L 1⁻3⁺ | Threshold gap, device units | 105.9 | 105.9 | **52.9 – 132.4** | — |
| L 1⁻3⁺ | Detection blanking | 3 s | 3 s | 3 – 3 s | 3 only |
| L 1⁻3⁺ | Changes per hour | 1.376 | 1.268 | 0.719 – 1.991 | — |
| L 0⁻2⁺ | Onset | 36 s | 42 s | **27 – 60 s** | 24, 27, 30, 36, 42, 48, 54, 60 |
| L 0⁻2⁺ | Threshold gap | 0.4 scatter | 0.3 | **0.2 – 0.6 scatter** | 0.2 … 0.6 |
| L 0⁻2⁺ | Threshold gap, device units | 87.0 | 65.2 | **43.5 – 130.5** | — |
| L 0⁻2⁺ | Detection blanking | 3 s | 3 s | 3 – 3 s | 3 only |
| L 0⁻2⁺ | Changes per hour | 0.987 | 0.929 | 0.544 – 1.284 | — |

**This is the finding I most want the judge to carry away.** Moving the split does not move the
onset at all, which looks like a robust recommendation; resampling the same recordings moves it from
36 to 90 seconds on L 1⁻3⁺ and from 27 to 60 on L 0⁻2⁺. **The split test flatters every method in
this contest.** Any arm reporting "my onset does not move between splits" has shown much less than
it appears to have shown, because there are only a handful of long recordings and all three splits
share nearly all of them. The threshold gap is wide too: 53 to 132 device units on L 1⁻3⁺, against a
device grid step of about one unit. **In device grid steps, my recommendation for the onset spans
roughly eighteen steps and for the threshold gap roughly eighty. By the contest's own definition of
robust, neither is robust** — and by that same definition, nor is anything derived from this record
by any method, because the uncertainty is in the record, not in the method.

**Detection blanking is not determined at all, and that is a fact rather than a shortcoming of the
search.** At the recommended onsets, all four blanking values give identical results to four decimal
places — 1.376 changes an hour and 0 undone switches at every one of 3, 15, 30 and 60 seconds on
L 1⁻3⁺; 0.987 and 0 at every one on L 0⁻2⁺. Blanking only does anything when the onset is very
short: at a 3-second onset it takes L 1⁻3⁺ from 504 changes an hour with 5,475 undone down to 59 an
hour with 0 undone at 60 seconds of blanking. Blanking and onset are two ways of buying the same
thing, and once the onset is long the blanking is idle.

### 3.5 The averaging window, which the replay can express — and a warning about it

Run on the stretches with at least 20 readings, so that a 30-second averaging window has at least
two of them. The onset stays at the recommended value **in seconds**, which is how a clinician
enters it.

**L 1⁻3⁺, onset 48 s, training recordings**

| Averaging | Controller clock | Changes /h | Undone | At upper | At lower | Mean current |
|---|---|---|---|---|---|---|
| 3 s | 3 s | **1.39** | **0** | 0.295 | 0.109 | 3.42 mA |
| 6 s | 6 s | 2.29 | 0 | 0.458 | 0.170 | 3.59 mA |
| 15 s | 15 s | 4.75 | 4 | 0.515 | 0.268 | 3.52 mA |
| 30 s | 30 s | 8.40 | 40 | 0.572 | 0.280 | 3.60 mA |

**L 0⁻2⁺, onset 36 s, training recordings**

| Averaging | Controller clock | Changes /h | Undone | At upper | At lower | Mean current |
|---|---|---|---|---|---|---|
| 3 s | 3 s | **1.02** | **0** | 0.106 | 0.202 | 2.94 mA |
| 6 s | 6 s | 2.83 | 0 | 0.267 | 0.311 | 3.02 mA |
| 15 s | 15 s | 10.12 | 38 | 0.458 | 0.369 | 3.25 mA |
| 30 s | 30 s | 9.94 | 55 | 0.459 | 0.389 | 3.22 mA |

**The averaging window and the onset duration are not two independent settings.** The device forms
one signal estimate per averaging window and the onset is counted in those estimates, so a
30-second averaging window turns a 48-second onset into **two** estimates of confirmation, while a
3-second window turns the same 48 seconds into **sixteen**. That is why lengthening the averaging
window in the table above makes the loop switch *more*, not less, and makes undone switches appear
where there were none. It also means the device's own programmed pair today — averaging 30 s with a
30-second onset — asks the controller to confirm on **exactly one** signal estimate: there is no
temporal confirmation in the device's current programming at all, and the averaging window is doing
all of the smoothing. Every onset number in §3.2, in the Phase 10 synthesis and in the `t3` sweep is
an onset applied to raw 3-second readings, and none of them describes the device as it is programmed
today.

### 3.6 Cost

| Step | Seconds |
|---|---|
| Prediction models, one band, one split (search over penalty and tree settings, then refit) | 47 – 64 |
| The controller search, one band, one split (576 + 49 settings over 27 hours of recording) | **2.4 – 2.6** |
| The 200-replicate block bootstrap, one band | 313 – 315 |
| Proving my fast replay equal to the platform's, both bands | 22 |

The whole controller search costs about two and a half seconds a band. Almost all the cost in this
arm is the gradient-boosted trees, and they bought nothing.

---

## 4. The recommended value for each parameter, per band

Where my stated tie-break gave an unstable answer I say so and recommend on a stated stability rule
instead, rather than quoting the unstable number.

### L 1⁻3⁺ at 24.5 Hz

| Parameter | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Onset, upper timer | **48 s** | The search's winner at all three splits, and the shortest onset that still leaves the loop at each current limit at least a tenth of the time while making the fewest changes an hour (1.38 against the device's 2.50). | **Medium** — identical at all three splits, but the bootstrap runs 36 to 90 s, so treat anything in 36–60 s as the same recommendation. |
| Onset, lower timer | **48 s, the same** | The replay applies one onset to both directions, so the record as replayed here cannot tell the two apart; the dwell tables do show the above-threshold runs lasting about 1.4 times the below-threshold ones, which argues for testing a shorter lower timer, and my method cannot test it. | **Low** — not separately measured. |
| Transition up | **60 s** | The longest ramp on the grid that keeps at least a tenth of the time at each current limit at **all three splits** (at 150 s the lower limit falls to 0.099 and fails); my stated tie-break picked 300 s at two splits and is not robust, so I use the stability rule instead and say so. | **Low** — the objective cannot see this setting at all; anything from 3 to 60 s scores identically to three decimal places. |
| Transition down | **60 s** | Same evidence and same rule; the record gives no reason for down to differ from up. | **Low** — same reason. |
| Averaging duration | **3 s** (the shortest this record can express) | With the onset entered in seconds, a short averaging window is what makes the onset mean sixteen confirmations instead of two: 3 s gives 1.39 changes an hour with 0 undone, 30 s gives 8.40 with 40 undone. | **Medium** — clearly measured, but the 3-second pieces are themselves the finest the record has, so anything shorter is untested, and this recommendation only holds if the onset is kept long. |
| Detection blanking | **30 s (keep what the device runs)** | At a 48-second onset every blanking value from 3 to 60 s gives the identical 1.376 changes an hour and 0 undone switches, so the record cannot choose, and keeping today's value costs nothing. | **Low** — genuinely undetermined, shown rather than assumed. |
| Adaptive startup delay | **12 s** | The first four readings of a recording sit 0.21, 0.19, 0.17 and 0.13 of the signal's scatter below that recording's own later level, each interval excluding zero, and the bias is gone by the fifth reading at 12 s (81 training stretches). | **Medium** — measured directly with an interval; whether the dip is the device or the tissue is unknown, and the replay cannot express this setting so it is not in the controller score. |
| Upper threshold | **239.2 device units** | The midpoint of the stored pair plus half a gap of 0.4 of the signal's scatter — the winner at all three splits, and it puts 29 % of readings in the dead zone against 13 % for the stored pair and 0.3 % for the device's own 167/166. | **Medium** on the placement rule, **Low** on the exact number — the bootstrap gap runs 53 to 132 units, i.e. an upper threshold anywhere from 213 to 252. |
| Lower threshold | **133.3 device units** | Same rule, the other side of the same midpoint. | Same: **Medium** on the rule, **Low** on the number (bootstrap range 120 to 160). |

### L 0⁻2⁺ at 24.5 Hz

| Parameter | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Onset, upper timer | **36 s** | The search's winner at all three splits, making 0.99 changes an hour against the device's 2.51 while keeping a tenth of the time at each current limit. | **Medium** — identical at all three splits, bootstrap 27 to 60 s. |
| Onset, lower timer | **36 s, the same** | As above, the replay applies one onset to both directions; on this contact it is the below-threshold runs that last about 1.2 times the above-threshold ones, the opposite way round from the other contact, which is itself a reason not to assume the two timers should match. | **Low** — not separately measured. |
| Transition up | **15 s** | The longest ramp on the grid that keeps a tenth of the time at each limit at all three splits (at 30 s the upper limit reaches exactly 0.100 at the 80/20 split and then falls below); my stated tie-break gave 30, 60 and 300 s at the three splits and is not robust. | **Low** — the objective cannot see it, and the margin here is one thousandth. |
| Transition down | **15 s** | Same evidence, same rule. | **Low** — same reason. |
| Averaging duration | **3 s** (the shortest this record can express) | Same arithmetic as the other contact and a sharper version of it: 3 s gives 1.02 changes an hour with 0 undone, 15 s gives 10.12 with 38 undone. | **Medium** — same caveat: only holds with a long onset. |
| Detection blanking | **30 s (keep what the device runs)** | At a 36-second onset every blanking value from 3 to 60 s gives the identical 0.987 changes an hour and 0 undone switches. | **Low** — undetermined. |
| Adaptive startup delay | **9 s** | The first three readings sit 0.11, 0.16 and 0.09 of the scatter below the recording's own later level with intervals excluding zero, and the bias is gone by the fourth reading at 9 s (71 training stretches). | **Medium** — measured with an interval; not expressible in the replay. |
| Upper threshold | **237.0 device units** | Midpoint of the stored pair plus half a 0.4-scatter gap; the stored pair 196.13/190.89 leaves only 2 % of readings between the thresholds and is a single threshold in all but name, exactly like the device's 167/166. | **Medium** on the rule, **Low** on the number — bootstrap gap 43 to 130 units, upper threshold 215 to 259. |
| Lower threshold | **150.0 device units** | Same rule, other side. | Same: **Medium** on the rule, **Low** on the number (bootstrap 128 to 172). |

**One recommendation that is High confidence and is not a number.** On both bands the pair of
thresholds actually in the device, and the stored pair on L 0⁻2⁺, leave under 3 % of readings
between them — they are single thresholds wearing two names. Every replay in §3.2 shows that
separating them by roughly 0.4 of the signal's own scatter cuts the number of current changes by
about half with no undone switches. **Separating the two thresholds is the change this record
supports most strongly, on both bands, at every split, in every bootstrap replicate.** The exact
separation is not settled; that there should be one is.

---

## 5. What this method cannot tell from this record

1. **It cannot predict the signal.** Four-fifths of what the 3-second reading does next is not in
   the previous minute of it, and trees found nothing a straight line missed. Any arm here that
   reports a large prediction gain over the mean should be asked how, on this data.
2. **It cannot separate the upper onset timer from the lower one,** nor the averaging window from
   the onset, because the replay applies one onset on whatever clock the averaging leaves.
3. **It cannot choose the detection blanking,** and it shows why: at these onsets the blanking never
   fires.
4. **It cannot choose the transition durations.** They are invisible to the objective and nearly
   invisible to the constraints; the numbers it does produce move by several grid steps between
   splits.
5. **It cannot tell what would actually have happened.** The replay feeds the controller a recording
   made while the current was doing something else. If the band really does fall when the current
   rises, the real loop would have retreated from a limit sooner than these numbers show. This
   caveat belongs to every arm in the contest equally; no arm can remove it from retrospective data,
   and only the titration session (open item 30) can.
6. **It cannot say whether any of this helps the patient.** Nothing here touches pain. The objective
   is about how often the current changes, not about whether changing it does any good.
7. **It cannot speak for the right side.** One left-side signal drives both stimulators on this
   participant; every number here is a left-signal number.
8. **It cannot judge a setting on the test recordings the contest's split produces.** The median
   test stretch is 24 seconds; any onset longer than that cannot express itself there.

---

## 6. The files I wrote

All under `BRAVO/_agent_bridge/_probe_tl/_contest/ml_stats/` (this whole folder is ignored by git),
and this report at `artifacts/contest_2026-09-13_ml_stats.md`.

| File | What is in it |
|---|---|
| `fastreplay.py` | the many-settings-at-once controller replay, proven equal to `simulation.simulate_series` |
| `s1_selfcheck.py` | the inspection of the recordings, the split table, and the equality proof |
| `s1_split_and_equality.csv` | the split sizes and the 35,840-value equality count |
| `s2_predict.py` | the prediction models and the start-of-recording bias |
| `s2_prediction_scores.csv` | every prediction number in §3.1 |
| `s2_startup_bias.csv` | the start-of-recording bias by reading, with bootstrap intervals |
| `s3_search.py` | the objective, written before the search, and the two-stage search |
| `s3_stage1_grid.csv` | all 576 settings × 3 splits × 2 bands |
| `s3_stage2_transitions.csv` | all 49 transition pairs × 3 splits × 2 bands |
| `s3_controller_scores.csv` | my setting and the two references, training and test |
| `s3_chosen_and_sensitivity.csv` | the chosen setting and the constraint-level sensitivity sweep |
| `s4_bootstrap.py` | the 200-replicate block bootstrap by stretch, and the averaging sweep |
| `s4_bootstrap_ONE_THREE_LEFT_20260913.csv`, `s4_bootstrap_ZERO_TWO_LEFT_20260913.csv` | every replicate's chosen setting |
| `s5_final.py`, `s5_final_scores.csv` | the final scoring at all three splits, the stretch-length tables, the averaging tables |
