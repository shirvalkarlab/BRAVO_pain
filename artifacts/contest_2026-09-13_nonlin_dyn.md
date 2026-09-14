# Contest entry E — `nonlin_dyn`: the band power as a nonlinear dynamical system with fast and slow parts

**Written 2026-09-13.** Method assigned: treat RCS08's 3-second band-power readings as a trajectory
of a dynamical system, reconstruct that system from the readings alone (delay embedding), test
whether it is genuinely nonlinear, separate the fast part from the slow part, predict one step
ahead with a nearest-neighbour predictor, and treat the closed loop as a switching system whose
return map has bifurcation values that set the timing parameters.

Scored exactly by the contest brief's rule. Everything ran in the container through the bridge.
Nothing was written to the production store; no production file was edited.

---

## 1. The method, in five sentences

1. A single 3-second reading is not the state of the brain, so I rebuild a state out of several
   readings spaced a fixed distance apart in time — the reading now, the one 9 seconds ago, and so
   on — which is the standard way to recover a system's state from one measured quantity.
2. I then check whether the rebuilt system is genuinely nonlinear, by making 39 artificial
   copies of the recording that keep its exact set of values and its exact rhythm content but
   scramble everything else, and asking whether the real recording is more predictable than they
   are.
3. I split each reading into a fast part and a slow part by averaging over windows of different
   lengths, and I measure how much of the slow part is real rather than an accident of the very
   spiky value distribution, by comparing against the same readings shuffled into random time
   order.
4. I predict the next reading from the rebuilt state using its nearest matches in the training
   record, and score that against doing nothing clever (guess the last reading; guess the average).
5. Finally I treat the device's loop as a switching system: after each switch the current ramps
   toward a limit, so the amplitude at successive switches follows a simple map, and that map has
   two critical values — the onset duration below which the fast part alone keeps flipping the
   loop, and the ramp duration above which the ramp outlasts the excursion and the current never
   reaches either limit.

---

## 2. The model I fitted, with its numbers

All fitted on TRAINING only. Never pooled across the two contacts. All values are the device's own
linear units; nothing was log-scaled.

### 2a. The rebuilt state: spacing and how many readings

The spacing between the readings that make up the state is chosen as the first dip in how much one
reading tells you about a later one (mutual information, in nats). How many readings are needed is
chosen by the false-nearest-neighbour test: add one more reading to the state and count how many
points that looked like close neighbours turn out to be far apart — when that fraction stops
falling, the state is big enough.

| Band | Information carried, lags 1 to 6 (nats) | Spacing chosen | False neighbours at 1,2,3,4,5 readings | Readings in the state |
|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 0.2466, 0.2260, **0.2154**, 0.2175, 0.2145, 0.2116 | **3 steps = 9 s** | 0.998, 0.854, 0.416, 0.116, **0.051** | **5** (state spans 36 s) |
| L 0⁻2⁺ 24.5 Hz | 0.1043, **0.0948**, 0.0952, 0.0963, 0.0931, 0.0937 | **2 steps = 6 s** | 0.999, 0.873, 0.412, 0.109, **0.019** | **5** (state spans 24 s) |

### 2b. Is it nonlinear? No — and this is the single most important finding in this entry

39 artificial copies per band (iterative amplitude-adjusted Fourier transform: same values, same
rhythm content, everything else scrambled). Two statistics. One-sided p-values; with 39 copies the
smallest p-value obtainable is 1/40 = 0.025.

| Band | Prediction error, real | Prediction error, copies (mean, sd, best) | p | Time-reversal asymmetry, real | copies (mean, sd) | p |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 120.528 | 120.956, 1.301, 117.672 | **0.350** | −0.0261 | −0.0131, 0.0564 | 0.700 |
| L 0⁻2⁺ 24.5 Hz | 88.165 | 88.582, 0.751, 86.952 | **0.325** | −0.0268 | +0.0122, 0.0323 | 0.425 |

**The real recording is no more predictable than a linear-stochastic copy of itself, on either
band.** There is no evidence of a low-dimensional nonlinear system here. The false-neighbour test
above settling at 5 readings therefore should NOT be read as "the brain signal is a 5-dimensional
attractor": a spiky linear-stochastic process produces the same settling. I am reporting that
plainly rather than presenting the embedding as if it had found structure.

### 2c. Fast and slow

For each averaging window, the share of a reading's variance carried by the window average (the
slow part), minus the same share computed on the identical readings shuffled into random time
order (which keeps the spiky value distribution and destroys every time scale). Twenty shuffles;
the ± is the standard error of their mean. TRAINING, 70/30 split.

| Averaging window | L 1⁻3⁺ genuinely slow share | L 0⁻2⁺ genuinely slow share |
|---|---|---|
| 6 s | +0.0139 ± 0.0082 | −0.0248 ± 0.0128 |
| 9 s | −0.0143 ± 0.0139 | −0.0345 ± 0.0170 |
| **15 s** | **+0.1221 ± 0.0153** | **+0.1074 ± 0.0218** |
| 30 s | +0.0922 ± 0.0113 | +0.0588 ± 0.0161 |

**The genuinely slow part of this signal is about 12 % (L 1⁻3⁺) and 11 % (L 0⁻2⁺) of a reading's
variance, and it is best seen with a 15-second average.** Averaging longer than 15 s does not
recover more of it. The raw "slow share" without the shuffle control is about 0.55 and 0.43 — the
shuffled copies give 0.47 and 0.39 of that by themselves, purely from the spiky value distribution,
so a slow-share number quoted without this control is mostly an artefact. That is why the shuffle
control is here.

### 2d. The closed loop as a switching system, and its two critical values

**Critical value 1 — the onset below which the fast part alone drives the switching. There is
none.** I ran the device's own classification logic over the real readings and over the same
readings shuffled into random time order, at averaging windows of 3, 15 and 30 s and onsets from
3 s to 300 s (TRAINING, 70/30). The switching rates are the same to within 10–30 % at every single
setting:

| Averaging | Onset | L 1⁻3⁺ real / shuffled (switches per hour) | L 0⁻2⁺ real / shuffled |
|---|---|---|---|
| 3 s | 3 s | 434.2 / 473.4 | 434.5 / 457.8 |
| 3 s | 15 s | 6.48 / 4.62 | 10.47 / 7.55 |
| 3 s | 30 s | 2.50 / 2.31 | 2.51 / 2.06 |
| 3 s | 120 s | 0.80 / 0.45 | 0.30 / 0.28 |
| 15 s | 30 s | 13.30 / 11.85 | 11.69 / 12.11 |
| 30 s | 30 s | 22.48 / 21.28 | 22.05 / 22.59 |

**So the loop's switching on this participant is driven by the value distribution, not by the
signal's history.** No onset duration buys you "the loop is now tracking a real slow excursion
rather than noise", because there is almost no history to track. What the onset does buy is fewer
switches and fewer switches undone, monotonically. This kills the idea of a chattering-death
bifurcation on this record, and I report it as a negative result rather than manufacturing a knee.

**Critical value 2 — the ramp duration at which the current stops reaching its limits.** Between
two switches the current ramps at (upper limit − lower limit) ÷ (transition duration), so after a
stretch of length T it has moved (span ÷ transition) × T. It reaches the limit exactly when
transition ≤ T. The border is therefore **transition\* = the time the loop spends in one state**,
and that is measurable. At the chosen settings (below), the lower quartile of those times is 180 s
on both bands at the 70/30 split, so a ramp of 180 s lets three excursions in four reach a limit.

**A third finding, which I did not expect and which matters for reading the Phase 10 baseline.**
The onset's filtering power is not set by the onset in seconds; it is set by **onset ÷ averaging**,
because the controller re-classifies once per averaging window. With a 30-second average, a
30-second onset is one window — no filtering at all. This is why the same nominal onset of 30 s
gives 2.50 switches per hour at a 3-second average and 22.48 at a 30-second average.

### 2e. The one-step predictor

Chosen by 5-fold blocked cross-validation inside TRAINING only (contiguous, time-ordered folds of
stretches — a random fold would put a stretch's own neighbours in the library and flatter the
score). Candidates: average of the k nearest matches, and a local straight-line fit through them,
k from 10 to 2560.

| Band (70/30) | Chosen | k | Cross-validation error | Linear autoregression on the same state, cross-validation error |
|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | local straight line | 2560 | 141.890 | 143.516 |
| L 0⁻2⁺ 24.5 Hz | average of neighbours | 160 | 165.218 | 166.165 |

---

## 3. The scoring rule's numbers

### 3.0 The split

Sorted by start time; the first 70 % of stretches by count are TRAINING. Stretches shorter than
three readings are dropped before splitting (they carry no dynamics).

| Band | Stretches | TRAIN stretches | TRAIN readings | TRAIN hours | TEST stretches | TEST readings | TEST hours |
|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 325 | 227 | 33,133 | 27.611 | 98 | 4,773 | 3.978 |
| L 0⁻2⁺ 24.5 Hz | 294 | 206 | 31,512 | 26.260 | 88 | 1,394 | 1.162 |

**The TEST sets are small, and one of them is very small.** L 0⁻2⁺ has 1.16 hours of TEST, and its
stretches average 47 seconds. Every number in section 3.2 for that band rests on 6 usable
stretches. That is a limit of the record, not of the method, and it is the reason several
confidences in section 4 are Medium rather than High.

### 3.1 Prediction score — one step ahead on TEST, in the device's own units

"Variance explained" is 1 − error² ÷ TEST variance; 0 means no better than knowing the TEST
average, negative means worse than that. The linear autoregression row is not required by the
brief; I include it because the surrogate test in 2b says the nonlinearity is not established, and
this is the control that shows what that costs.

**L 1⁻3⁺ 24.5 Hz**

| Split | TEST spread | n | My model | Linear autoregression | Persistence (next = last) | TEST mean | TRAIN mean |
|---|---|---|---|---|---|---|---|
| 70/30 | 165.006 | 3,484 | **153.898 (+0.1301)** | 153.367 (+0.1361) | 191.851 (−0.3519) | 165.006 (0.0000) | 165.150 (−0.0017) |
| 60/40 | 165.084 | 4,179 | **149.565 (+0.1792)** | 149.266 (+0.1825) | 186.319 (−0.2738) | 165.084 (0.0000) | 165.350 (−0.0032) |
| 80/20 | 169.820 | 3,048 | **158.123 (+0.1330)** | 157.817 (+0.1364) | 198.072 (−0.3604) | 169.820 (0.0000) | 170.127 (−0.0036) |

**L 0⁻2⁺ 24.5 Hz**

| Split | TEST spread | n | My model | Linear autoregression | Persistence | TEST mean | TRAIN mean |
|---|---|---|---|---|---|---|---|
| 70/30 | 105.934 | 666 | **101.864 (+0.0754)** | 103.288 (+0.0493) | 130.067 (−0.5075) | 105.934 (0.0000) | 112.012 (−0.1181) |
| 60/40 | 97.519 | 1,469 | **91.116 (+0.1270)** | 91.715 (+0.1155) | 117.245 (−0.4455) | 97.519 (0.0000) | 98.143 (−0.0128) |
| 80/20 | 105.841 | 355 | **104.976 (+0.0163)** | 107.089 (−0.0237) | 134.851 (−0.6233) | 105.841 (0.0000) | 115.060 (−0.1818) |

**What this says, plainly.** The model beats guessing the last reading by a wide margin on every
band and every split — and guessing the last reading is *worse than useless* here, at −0.27 to
−0.62, because one reading barely predicts the next and repeating it doubles the error's variance.
The model beats the TEST average by 13–18 % of the variance on L 1⁻3⁺ and 2–13 % on L 0⁻2⁺. But it
does **not** beat a plain linear autoregression on the same rebuilt state: the two are within 0.006
of each other on L 1⁻3⁺ (linear very slightly ahead on all three splits) and the nonlinear one is
ahead by 0.012–0.040 on L 0⁻2⁺. That is exactly what the surrogate test predicted. **The honest
summary is that this signal has real, modest, short-range predictability, and none of it needs a
nonlinear model.**

### 3.2 Controller score — the device's Dual Threshold controller replayed on TEST

Every arm was run twice: over all TEST stretches, and over the stretches long enough for every arm
(60 s or more), because a 30-second averaging window needs 60 seconds of stretch before the
controller has two windows and would otherwise silently score the arms on different data. **The
"same data for every arm" rows are the comparable ones and are what I report here**; the all-
stretches rows are in the CSV and differ by less than 0.5 switches per hour on my arm.

The adaptive startup delay is not a parameter of `simulation.py`. It is emulated the way the device
behaves — the readings of the first whole averaging windows of every stretch are set missing, and
the controller's documented handling of a missing estimate is to hold and decide nothing. The
number of held steps is in the CSV.

**L 1⁻3⁺ 24.5 Hz, 70/30, 20 TEST stretches, 3.4 hours**

| Arm | Switches / h | Undone within one onset | Time at upper limit | at lower limit | between | Mean current | TEST readings between the thresholds |
|---|---|---|---|---|---|---|---|
| **nonlin_dyn** (avg 15 s, onset 60 s, ramps 180 s, blank 60 s, startup 15 s, 280.0 / 201.3) | **7.30** | **0** | 46.4 % | 14.1 % | 39.5 % | **3.658 mA** | 33.4 % |
| Device today GROUP_D timing, this band's stored thresholds | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 21.8 % |
| Device today GROUP_D timing and its own 167 / 166 | 17.44 | 16 | 93.8 % | 6.2 % | 0.0 % | 4.591 mA | 0.3 % |
| Phase 10 recommendation, averaging 30 s honoured | 38.72 | 51 | 86.5 % | 7.6 % | 5.9 % | 4.440 mA | 21.8 % |
| Phase 10 as its own sweep ran it (averaging left at the replay's 1.2 s default, so no averaging) | 2.60 | 0 | 75.8 % | 0.0 % | 24.2 % | 4.396 mA | 18.2 % |

**L 0⁻2⁺ 24.5 Hz, 70/30, 6 TEST stretches, 0.61 hours**

| Arm | Switches / h | Undone within one onset | at upper | at lower | between | Mean current | readings between thresholds |
|---|---|---|---|---|---|---|---|
| **nonlin_dyn** (avg 15 s, onset 75 s, ramps 180 s, blank 75 s, startup 15 s, 213.8 / 173.3) | **6.58** | **0** | 29.5 % | 0.0 % | 70.5 % | **3.686 mA** | 22.4 % |
| Device today GROUP_D timing, stored thresholds | 35.49 | 5 | 81.7 % | 18.3 % | 0.0 % | 4.177 mA | 1.4 % |
| Device today GROUP_D timing and its own 167 / 166 | 25.35 | 6 | 91.5 % | 8.5 % | 0.0 % | 4.513 mA | 0.0 % |
| Phase 10 recommendation, averaging 30 s honoured | 35.49 | 5 | 73.2 % | 18.3 % | 8.5 % | 4.034 mA | 1.4 % |
| Phase 10 as its own sweep ran it (no averaging) | 6.49 | 0 | 51.4 % | 0.0 % | 48.6 % | 3.989 mA | 3.1 % |

**Three things to read off these tables.**

1. **The device's setting today pins the current at the top.** With GROUP_D's own 167 / 166 the
   current sits at the upper limit 93.8 % of the time on L 1⁻3⁺ and 91.5 % on L 0⁻2⁺, the
   dead band holds 0.3 % and 0.0 % of readings, and the loop still switches 17 and 25 times an hour
   with 16 and 6 of those switches undone within one onset. That is a single threshold being
   crossed back and forth at the top of the range, not a loop.
2. **My arm is the only one that is not pinned and undoes nothing.** 46 % / 14 % / 40 % of the time
   split between upper, lower and mid-range on L 1⁻3⁺, at 7.3 switches an hour with zero undone,
   and a mean current of 3.66 mA against 4.48–4.59 mA for the device's settings. On L 0⁻2⁺ the
   current never reaches the lower limit in 0.61 hours of TEST, which I flag rather than smooth
   over — six stretches is too few to say it never would.
3. **The Phase 10 recommendation does not behave the way its own table says, because its sweep and
   its recommendation used different averaging.** Its onset sweep ran with the replay's default
   averaging of 1.2 s, which on a 3-second grid means no averaging at all, and at that setting its
   30-second onset gives 2.60 switches an hour with none undone — which reproduces its published
   row. Pair that same 30-second onset with the 30-second averaging it recommends, as the device
   would actually run it, and it gives **38.72 switches an hour with 51 undone**. This is a real
   and checkable discrepancy in the baseline, and it follows directly from finding 2d: the onset's
   filtering power is onset ÷ averaging, and 30 ÷ 30 is one window. I am not claiming the Phase 10
   measurements are wrong — they are right for the averaging they were run at. I am claiming the
   recommendation pairs an onset with an averaging that were never replayed together.

### 3.3 Robustness — how much each recommendation moves when the split moves

The whole derivation was re-run unchanged at 60/40 and 80/20. The brief's bar is one device grid
step: 3 s for a timing, 1 unit for a threshold.

| Parameter | L 1⁻3⁺ at 70/30, 60/40, 80/20 | Moves | Robust? | L 0⁻2⁺ at 70/30, 60/40, 80/20 | Moves | Robust? |
|---|---|---|---|---|---|---|
| Averaging | 15, 15, 15 s | 0 s | **yes** | 15, 15, 15 s | 0 s | **yes** |
| Onset (both) | 60, 60, 60 s | 0 s | **yes** | 75, 75, 75 s | 0 s | **yes** |
| Detection blanking | 60, 60, 60 s | 0 s | **yes** | 75, 75, 75 s | 0 s | **yes** |
| Adaptive startup delay | 15, 15, 15 s | 0 s | **yes** | 15, 15, 15 s | 0 s | **yes** |
| Upper threshold | 280.00, 282.45, 279.83 | 2.62 units | **no** (bar is 1 unit) | 213.75, 214.63, 214.13 | 0.88 units | **yes** |
| Lower threshold | 201.27, 203.42, 202.37 | 2.15 units | **no** | 173.27, 173.16, 173.72 | 0.56 units | **yes** |
| Transition up and down | 180, 139, 180 s | 41 s | **no** | 180, 150, 165 s | 30 s | **no** |

**Stated plainly: the two ramp durations are not robust on either band, and the two thresholds are
not robust on L 1⁻3⁺.** The ramp comes from the lower quartile of how long the loop stays in one
state, and that quartile is estimated from 36 to 110 excursions depending on the split. The
timings that come from a rule with a whole record behind it — averaging, onset, blanking, startup —
do not move at all.

Two earlier versions of two of these rules were **not** robust and were replaced before the final
run, which is recorded here rather than hidden: picking the averaging window by the plain largest
slow-excess flipped between 15 s and 30 s on the noise of a single shuffle (fixed with twenty
shuffles and a one-standard-error rule, which takes the shortest window within one standard error
of the best); and picking the onset as the shortest with exactly zero undone switches moved by two
grid steps on one event (fixed by asking for at most 2 % of that onset's own switches to be undone).

### 3.4 Cost

Wall clock, from the scripts' own timers, in the container.

| Step | L 1⁻3⁺ | L 0⁻2⁺ |
|---|---|---|
| Fit the predictor on TRAINING (5-fold blocked cross-validation, 70/30) | 17.2 s | 18.4 s |
| Derive the nine parameters on TRAINING (70/30) | 4.3 s | 4.0 s |
| **Total fit on TRAINING, 70/30** | **21.5 s** | **22.4 s** |
| Diagnostics not part of the fit: spacing, state size, fast/slow | 11.8 s | 12.8 s |
| Diagnostics not part of the fit: 39 surrogate copies | 7.8 s | 7.5 s |

---

## 4. The recommended value for each of the nine parameters, per band

Amplitude limits held at the record's 1.4–4.8 mA throughout. Every value sits inside the documented
selection range where one exists (FDA SSED P960009/S478 Table 2: onset 0–6 min Dual, transitions
250 ms–30 min, thresholds 0.55–400 µVrms; BrainSense tip cards: averaging 0–30 s). No range is
documented for detection blanking or the adaptive startup delay; for those I say what the device has
demonstrably accepted on this participant.

### L 1⁻3⁺ at 24.5 Hz

| # | Parameter | Recommend | One-sentence reason | Confidence |
|---|---|---|---|---|
| 1 | Averaging duration | **15 s** | Fifteen seconds is where the window average carries the most of this signal's genuinely slow content (12.2 % ± 1.5 % of a reading's variance above the time-shuffled control, against 9.2 % ± 1.1 % at 30 s), and averaging longer recovers nothing more while making the loop slower and weakening the onset's filtering. | **High** — same window at all three splits, 27.6 h of her own signal, with the shuffle control that separates real slow content from the spiky value distribution |
| 2 | Onset duration, upper | **60 s** (4 averaging windows) | Sixty seconds is the shortest onset at which the loop undoes at most 2 % of its own switches (1–2 of about 100 on TRAINING), and on TEST it undid none. | **High** — 60 s at all three splits |
| 3 | Onset duration, lower | **60 s** | Same rule; the replay applies one onset to both directions, so the record as replayed cannot separate them and equal values are the honest choice. | **Medium** — the value is robust, but "upper and lower should be equal" is untested here |
| 4 | Transition up | **180 s** | The current reaches a limit only when the ramp is shorter than the time the loop stays in one state, and 180 s is the lower quartile of those times, so three excursions in four reach a limit. | **Low** — moved 41 s between splits, far more than one grid step; 139–180 s is the defensible band |
| 5 | Transition down | **180 s** | Same evidence; nothing in the record argues for down differing from up, and the replay applies the two symmetrically. | **Low** — same reason |
| 6 | Detection blanking | **60 s**, equal to the onset | A decision should not be re-classified before a fresh onset could have confirmed a new one; equal to the onset is the shortest value with that property. | **Medium** — derived by construction, not measured; the device has accepted 550 ms to 30 s on this participant, and 60 s is outside what it has been seen to run |
| 7 | Adaptive startup delay | **15 s**, one averaging window | My measure of the start of a stretch found no settling to wait out — the first three readings sit 0.03, 0.01 and 0.00 of the spread from their own stretch's middle value, none of them more than 1.5 standard errors from zero — so the only thing a delay needs to cover is the first averaging window not being complete. | **Medium** — this disagrees with the Phase 10 finding of a 12-second dip; the two use different baselines and I cannot say which is right |
| 8 | Upper threshold | **280.0** (60th percentile of the 15 s-averaged TRAINING readings) | Equal occupancy above and below is the only placement for which the loop's switching map is symmetric, so the current is not biased toward one limit; the stored 210.6 sits at the 41st percentile and pushes the loop to the top. | **Medium** — the placement rule is sound and the effect is large, but the value moved 2.6 units between splits, above the 1-unit bar |
| 9 | Lower threshold | **201.3** (40th percentile) | Same rule; the gap of 78.7 units leaves 33 % of TEST readings in the dead band, against 0.3 % for the device's own 167 / 166, which is a single threshold in all but name. | **Medium** — same reason, moved 2.2 units |

### L 0⁻2⁺ at 24.5 Hz

| # | Parameter | Recommend | One-sentence reason | Confidence |
|---|---|---|---|---|
| 1 | Averaging duration | **15 s** | Same rule and same answer: 10.7 % ± 2.2 % genuinely slow content at 15 s against 5.9 % ± 1.6 % at 30 s. | **High** — same window at all three splits |
| 2 | Onset duration, upper | **75 s** (5 averaging windows) | Seventy-five seconds is the shortest onset undoing at most 2 % of its own switches on this band (1 of 68); 60 s left 2 of 99, just over the line. | **High** — 75 s at all three splits |
| 3 | Onset duration, lower | **75 s** | Same rule; the replay cannot separate the two directions. | **Medium** — same caveat as the other band |
| 4 | Transition up | **180 s** | Lower quartile of the time the loop stays in one state at these settings. | **Low** — moved 30 s between splits (150–180 s) |
| 5 | Transition down | **180 s** | Same evidence. | **Low** |
| 6 | Detection blanking | **75 s**, equal to the onset | Same construction. | **Medium** — outside the 550 ms–30 s the device has been seen to run on this participant |
| 7 | Adaptive startup delay | **15 s** | Same measurement: the first readings of a stretch show no bias worth waiting out (largest of the first five is 0.8 standard errors). | **Medium** |
| 8 | Upper threshold | **213.8** (60th percentile) | Same placement rule; the stored pair 196.13 / 190.89 sits at the 50th and 47th percentiles with only 1.4 % of TEST readings between them. | **High** on the rule and on this band's value — moved 0.88 units, inside the 1-unit bar |
| 9 | Lower threshold | **173.3** (40th percentile) | Same rule; the gap of 40.5 units puts 22 % of TEST readings in the dead band. | **High** — moved 0.56 units |

**One cross-cutting caveat on every row above.** These parameters were chosen to make the loop
behave well as a controller — switch a few times an hour, never undo itself, use the whole current
range rather than sitting at the top. **Nothing here says any of it reduces her pain.** No pain
rating entered any of this.

---

## 5. What my method cannot tell from this record

1. **Whether any of this helps.** The pain ratings are not in this analysis at all. Every number in
   sections 3 and 4 is about how the loop behaves, not about whether the patient is better.
2. **What the stimulation does to the band power.** The replay I was told to use runs the
   controller over the recorded power with a zero response curve — the current changes, the power
   does not respond. On this record there is no established response curve to put in its place
   (decision 126: the pooled slope is −3.62 ± 9.97 device units per mA, an interval spanning zero).
   So the dwell times my ramp recommendation rests on are the dwell times of an **open** loop. If
   raising the current really does lower the power, a closed loop would cut its own excursions
   short and the right ramp would be shorter than 180 s. This is the largest single unknown in this
   entry.
3. **Anything faster than 3 seconds.** The record is on the device's 3-second clock. The documented
   1.2-second default onset cannot be expressed here at all.
4. **The upper and lower onsets separately**, and the two ramp durations separately. The replay
   applies one onset to both directions and I have no way to test an asymmetric pair.
5. **The ramp durations within about ±40 seconds.** They are the one family of values that moved
   more than a grid step between splits, and they are the values that would be settled by the
   titration session already on the books as open item 30.
6. **Whether the signal is truly linear.** A p-value of 0.35 with 39 surrogate copies is a failure
   to detect nonlinearity, not a proof of its absence; a weak nonlinearity would look exactly like
   this. What I can say is that no nonlinear model is *needed* to predict this record one step
   ahead.
7. **The right side.** The right sensing channel is ganged to the left (`GangedToHemisphere = Left`),
   so both recommendations above are left-signal recommendations and neither contact was pooled
   with the other.
8. **Whether the start of a stretch carries a device artefact.** My measure found none; the Phase 10
   measure found a 12-second dip. The two use different baselines (mine compares each reading to its
   own stretch's middle value) and this record cannot say which is the right comparison.
9. **How well the L 0⁻2⁺ controller numbers generalise.** They rest on 6 usable TEST stretches and
   0.61 hours. The current never reaching the lower limit in that window is not evidence that it
   would not.

---

## 6. The files I wrote

All under `BRAVO/_agent_bridge/_probe_tl/_contest/nonlin_dyn/` on the host
(`/usr/src/BRAVO/_agent_bridge/_probe_tl/_contest/nonlin_dyn/` in the container). Nothing outside
this directory was written, and no production file was edited or committed.

**Scripts**

| File | What it does |
|---|---|
| `s1_embed.py` | Prints every loaded array's name, shape, type and first values; makes the split; the mutual-information spacing; the false-nearest-neighbour state size; the fast/slow split; a first pass at the predictor |
| `s2_surrogates.py` | The 39 surrogate copies per band and the two statistics, with the p-value resolution floor stated |
| `s3_returnmap.py` | The loop as a switching system: real against time-shuffled switching rates across averaging and onset; the fast/slow table with its shuffle control; the threshold-quantile sweep; the start-of-stretch transient |
| `s4_predict.py` | The prediction score at all three splits, with the predictor chosen by 5-fold blocked cross-validation inside TRAINING and the linear-autoregression control |
| `s5_controller.py` | Derives the nine parameters from TRAINING by the fixed rules, then replays the controller on TEST for my arm and the four reference arms, at all three splits |

**Tables**

| File | What is in it |
|---|---|
| `e1_mutual_information.csv` | Information carried at lags 1 to 20, per band |
| `e1_false_nearest_neighbours.csv` | False-neighbour fraction for state sizes 1 to 10 |
| `e1_slow_fast_variance.csv` | First-pass fast/slow variance split |
| `e1_split_and_embedding.csv`, `e1_embedding_choice.json` | The split's counts and the chosen spacing and state size |
| `e1_prediction_7030.csv` | The first-pass prediction score |
| `e2_surrogate_test.csv`, `e2_surrogate_distribution.csv` | The surrogate p-values and every individual copy's statistic |
| `e3_chattering_onset.csv` | Real against time-shuffled switching rate at every averaging and onset |
| `e3_slow_fast_train.csv` | The fast/slow table with its shuffle control |
| `e3_threshold_quantiles.csv` | The threshold-separation sweep |
| `e3_startup_transient.csv` | The start-of-stretch bias and the state's distance to its nearest matches by position |
| `e4_prediction_scores.csv`, `e4_cv_curves.csv` | The prediction score at all three splits, and the cross-validation curve behind the choice of k |
| `e5_derivation.csv` | The nine derived parameters at each split, with the tables they were derived from |
| `e5_controller_scores.csv` | Every controller arm's numbers, at both TEST subsets and all three splits |
