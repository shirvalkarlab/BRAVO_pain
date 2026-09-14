# Method contest, contestant D: a two-state model of where the signal sits relative to the thresholds

**Written 2026-09-13.** Method slug `dwell_markov`. Skills used: `state-dwell-time-estimation`
(its `kernel.py` copied into the contest folder and used unmodified for the misclassification
bounds, the reproducible seeds and the diagnostics) and `attractor`.

**Where this lives, and whether anyone can see it.** **Nowhere — nothing here is on any page.**
These are numbers you would type into the clinician tablet. On the platform the same settings appear
on the **Closed-Loop Deployment page**, in the "Full parameter recommendation" card and in the
"CL-DBS simulations" card at the foot of that page, which replays the controller with an onset and
two ramp durations. Nothing on the platform writes to the device, and nothing in this report has
been wired to anything. Every table below is a file in the contest folder (section 6).

---

## 1. The method, in five sentences

A three-second reading is either above the upper threshold or it is not, so I treat the signal as a
light that is on or off, and I ask how long it really stays on and how long it stays off. The catch
is that a single three-second reading is a poor witness — it can say "on" when the underlying state
is off — so I fit a model that estimates the chance of a misread reading at the same time as it
estimates the true on and off durations, instead of taking the readings at face value. Taken at face
value the readings say the state flips every two or three seconds, which is just the reading interval
and is nonsense; corrected, the same data say the state lasts ten to fifteen minutes and that between
one reading in eight and one in three is misread. From that I get every timing setting directly: the
onset duration is how long the light must stay on before you can believe it, the averaging duration
is how much you can improve the witness before comparing, and the ramp and hold durations follow from
how long the state lasts. The thresholds are placed where the on/off split carries the most real
signal, which I measure by refitting the whole model at each candidate value.

---

## 2. The model, and its fitted numbers

### What is fitted

Two states — "the band power is truly above the upper threshold" and "truly below it" — with a
constant chance per unit time of switching each way, observed through a per-reading chance of being
misread. Four numbers per band per threshold:

- **q(low→high)** and **q(high→low)**, switching rates per hour. Their reciprocals are the mean true
  dwell in each state.
- **e0** = the chance a reading says "above" when the state is truly below.
- **e1** = the chance a reading says "below" when the state is truly above.

The likelihood is the skill's, re-expressed for a regular three-second grid so it runs on 32,000
readings at once: a three-second cell with no reading in it is an observation that tells you nothing,
which is exactly the skill's handling of an unobserved moment, and the recursion is run across all
stretches together. Every fit is on TRAINING only.

### Fitted values, 70/30 split, TRAINING

| Band | Threshold | Mean true dwell BELOW | Mean true dwell ABOVE | Switching half-life | e0 (below reads above) | e1 (above reads below) | Occupancy above |
|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | upper 210.58 | 617 s | 613 s | 213 s | 0.134 | 0.215 | 0.498 |
| L 1⁻3⁺ 24.5 Hz | lower 161.90 | 899 s | 795 s | 292 s | 0.111 | 0.264 | 0.469 |
| L 0⁻2⁺ 24.5 Hz | upper 196.13 | 794 s | 701 s | 258 s | 0.164 | 0.330 | 0.469 |
| L 0⁻2⁺ 24.5 Hz | lower 190.89 | 761 s | 837 s | 276 s | 0.314 | 0.179 | 0.524 |

**Read that as: the state lasts ten to fifteen minutes, and one reading in eight to one in three is
wrong about it.**

### The four checks the skill requires, and what each said

**(i) Is there misclassification at all? YES, and it dominates.** For a process that simply switches
back and forth, the chance that two readings disagree must fall to zero as the gap between them
shrinks. Measured on TRAINING it does not fall at all: on L 1⁻3⁺ the chance that two readings 3 s
apart disagree is 0.2612, at 30 s apart 0.2797, at 120 s 0.2799, at 720 s 0.2999. A flat curve like
that cannot be produced by any switching process; it is the reading being wrong.

**(ii) The correction changes the answer by a factor of about a hundred.** Fitting the same data
with the misclassification forced to zero — the standard fit — gives a switching half-life of
**1.8 to 2.8 seconds**, which is the reading interval and not a fact about the brain. The likelihood
ratio between the two fits is 4,505 to 5,647 on 2 degrees of freedom. No fit ran into the
identifiability limit (`error_at_bound` false on all four).

**(iii) Recovery against known truth: PASSES.** Drawing a path from the fitted numbers at the real
recording structure, corrupting it with the fitted misread rates and refitting: the corrected fit
recovers 565/567 s against a truth of 617/613 s and recovers the misread rates to three decimals
(0.135/0.211 against 0.134/0.215), while the uncorrected fit returns 7.5/6.6 s — wrong by a factor
of eighty. That contrast is what licenses the whole approach.

**(iv) The independent cross-check FAILS at long gaps, and the sampling-density gate FAILS.**
The fitted model says the state should have forgotten itself after twelve minutes; the data say it
has barely forgotten anything. Model against measured agreement of two readings, L 1⁻3⁺ upper:

| Gap | 3 s | 30 s | 120 s | 240 s | 480 s | 720 s |
|---|---|---|---|---|---|---|
| model says | 0.4226 | 0.3871 | 0.2888 | 0.1955 | 0.0896 | 0.0410 |
| measured | 0.4775 | 0.4402 | 0.4395 | 0.4245 | 0.4171 | 0.3994 |

And refitting on every second, fifth, tenth and twentieth reading, the fitted dwell grows with the
gap — 617 s at a 3 s gap, 2,090 s at 6 s, 3,747 s at 15 s, 5,837 s at 30 s, 8,558 s at 60 s — while
the misread rates barely move (e0 0.134, 0.138, 0.131, 0.108, 0.130). One fit at a 60 s gap
(L 0⁻2⁺ below) returned a dwell of 1.5 × 10¹⁶ s, which is a failed fit and is reported as one.

**What that means, stated plainly: the dwell time is not one number. It depends on the time scale
you look at, from about ten minutes at a three-second grid to about two and a half hours at a
sixty-second grid.** The record holds slow movement as well as fast, and a single two-state model
cannot hold both. The misread rate, by contrast, is stable across every scale, and it is what the
timing settings actually depend on. Comparing readings from different recording sessions confirms
the slow movement: agreement is 0.55 for sessions less than an hour apart, 0.28 at 12–48 h, 0.05 at
one to four weeks, and **−0.18 beyond a month** — the level itself drifts across the record, so a
fixed threshold does not mean the same thing in the first month as in the last.

### The averaging sweep: the one lever that improves the witness

Averaging several three-second readings before comparing them, which is what the device's averaging
duration does, cuts the misread rate sharply. Separation below is the standard deviation of the real
on/off signal as it survives into the reading — it falls to zero both when the reading is noise and
when the threshold is so extreme the state never changes.

| Band, threshold | Averaging | e0 | e1 | Separation |
|---|---|---|---|---|
| L 1⁻3⁺ upper | 3 s | 0.134 | 0.215 | 0.3255 |
| | 6 s | 0.113 | 0.147 | 0.3701 |
| | 15 s | 0.077 | 0.072 | 0.4255 |
| | **30 s** | **0.042** | **0.042** | **0.4551** |
| L 0⁻2⁺ upper | 3 s | 0.164 | 0.330 | 0.2521 |
| | 6 s | 0.122 | 0.258 | 0.3069 |
| | 15 s | 0.083 | 0.165 | 0.3732 |
| | **30 s** | **0.057** | **0.099** | **0.4218** |

**One reading in five is misread at three seconds; one in twenty at thirty seconds.** The
improvement is monotone on both bands, on both thresholds and on all three splits, and 30 s is the
documented maximum.

### The threshold sweep

The state "above x" and the state "below x" are the same model with its labels swapped, so one fit
per candidate value gives both. On the 30 s averaged series, TRAINING, 70/30 split:

| L 1⁻3⁺ value | 136.77 | 161.90 (stored lower) | 181.48 | 202.97 | **210.58 (stored upper)** | 226.49 | 247.50 | 266.11 | 286.25 | 331.14 |
|---|---|---|---|---|---|---|---|---|---|---|
| separation | 0.3213 | 0.4046 | 0.4287 | 0.4545 | **0.4551** | 0.4483 | 0.4348 | 0.4167 | 0.4022 | 0.3467 |

| L 0⁻2⁺ value | 139.02 | 155.29 | 165.94 | **186.39** | 190.89 (stored lower) | 196.13 (stored upper) | 207.18 | 217.47 | 239.46 | 265.35 |
|---|---|---|---|---|---|---|---|---|---|---|
| separation | 0.2962 | 0.3733 | 0.4039 | **0.4266** | 0.4265 | 0.4218 | 0.4078 | 0.3919 | 0.3322 | 0.2884 |

**The stored upper threshold on L 1⁻3⁺ sits exactly at the best value of the fifteen swept, and the
stored pair on L 0⁻2⁺ sits within 1.5 % of it.** That is an independent confirmation of the stored
thresholds, arrived at from a different direction. The peak is broad and flat, which is what makes
room for a deadband.

**A mistake found and corrected, disclosed rather than fixed quietly.** The first threshold sweep
started each fit from the previous value's answer; one bad fit propagated down the whole chain, and
at the stored upper threshold of L 1⁻3⁺ it reported misread rates of exactly 0.3000 and 0.3000 —
the identifiability limit — where an independent fit at the same value gives 0.134 and 0.215. It was
caught only by reading the table against a number already known from a separate fit. The sweep was
redone with several independent starts per value; four of the 42 fits end on the limit, all at
extreme values, and each is marked as a failed fit rather than reported as a number.

### The onset, derived two ways, and why the two disagree

**The posterior rule** asked for — how many same readings before the chance that the state really
changed passes 0.95 — gives **3 readings (9 s)** on three of the four chains and 5 readings (15 s)
on the fourth. **That rule is too generous and I do not use it.** It starts from one reading's worth
of evidence for the old state, whereas in the record the loop has usually been sitting in the old
state for many readings and is far more certain of it than that.

**The operating rule** runs the device's own onset counter over a path drawn from the fitted model
and counts what share of the loop's decisions were about a state that had really changed. This is
the rule I use: **the shortest hold at which no more than 5 % of the decisions are wrong.** On the
raw 3 s grid, L 1⁻3⁺ upper:

| Onset | decisions/h | of them wrong | true changes caught | median delay |
|---|---|---|---|---|
| 3 s | 345.5 | 49.4 % | 84.3 % | 0 s |
| 9 s | 16.5 | 33.1 % | 96.3 % | 6 s |
| **15 s** | **6.07** | **4.0 %** | **96.1 %** | **18 s** |
| 21 s | 5.35 | 0.3 % | 93.8 % | 36 s |
| 30 s | 4.49 | 0.0 % | 86.1 % | 72 s |
| 45 s | 2.71 | 0.2 % | 62.8 % | 228 s |
| 60 s | 1.34 | 0.0 % | 36.0 % | 450 s |

**Past about thirty seconds on this grid the loop stops making mistakes by ceasing to notice
anything**, which is the point the switching-rate tables in the Phase 10 synthesis cannot show,
because they count switches and not whether a switch was real.

At the recommended 30 s averaging the same table, L 1⁻3⁺ upper, reads: onset 30 s → 18.2 decisions/h,
**45.8 % of them wrong**; 60 s → 3.0/h, 21.3 % wrong; **90 s → 1.79/h, 2.5 % wrong, 95.7 % of true
changes caught**; 120 s → 1.66/h, 0.3 % wrong, 93.4 % caught.

### The attractor reading

Treating the two amplitude limits as the two states the loop settles into: the loop settles rather
than chatters only when the hold is long enough that a misread reading cannot move it, and only when
the ramp finishes before the state turns over. The second condition is not binding here — at 30 s
averaging the state outlasts a 30 s ramp in 98.3–99.0 % of episodes and a 150 s ramp in 91.8–95.3 %
— so the ramp duration is free within the range the device offers. The first condition is binding
and is what the onset table above measures. With the device's settings today the loop **chatters**:
49 decisions undone within one onset in 3.4 hours of test recording. With the settings recommended
here it **alternates**, at about 1.8 changes an hour, which is the rate the fitted model says the
state itself changes.

---

## 3. The scoring rule

### The split

Stretches sorted by start time, the first 70 % by count is TRAINING. **The last 30 % of stretches
are the short ones**, which matters for every number below:

| Band | Split | TRAIN stretches | TRAIN hours | TEST stretches | TEST hours | TEST readings |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 70/30 | 231 | 27.39 | 99 | 3.79 | 4,546 |
| | 60/40 | 198 | 26.58 | 132 | 4.61 | 5,527 |
| | 80/20 | 264 | 27.99 | 66 | 3.20 | 3,835 |
| L 0⁻2⁺ 24.5 Hz | 70/30 | 207 | 26.17 | 89 | **1.00** | 1,205 |
| | 60/40 | 178 | 25.48 | 118 | 1.69 | 2,027 |
| | 80/20 | 237 | 26.53 | 59 | 0.64 | 767 |

**One hour of test recording on L 0⁻2⁺ is not much, and every test number for that band should be
read as provisional.**

### Prediction: one-step-ahead, next 3 s reading, TEST

The prediction is the chance the state is above the threshold at the next reading, times the average
reading in that state, plus the same for below. Both state averages are estimated on TRAINING.

| Band | Split | test pairs | two-state RMSE | variance explained | persistence RMSE | variance explained | test-mean RMSE | variance explained |
|---|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 70/30 | 4,446 | **161.55** | −0.014 | 186.47 | −0.351 | 160.40 | 0.000 |
| L 1⁻3⁺ | 60/40 | 5,394 | **157.98** | +0.044 | 182.44 | −0.275 | 161.55 | 0.000 |
| L 1⁻3⁺ | 80/20 | 3,768 | **165.35** | −0.001 | 192.46 | −0.355 | 165.31 | 0.000 |
| L 0⁻2⁺ | 70/30 | 1,116 | **99.13** | +0.119 | 122.14 | −0.338 | 105.58 | 0.000 |
| L 0⁻2⁺ | 60/40 | 1,909 | **95.13** | +0.100 | 117.31 | −0.369 | 100.26 | 0.000 |
| L 0⁻2⁺ | 80/20 | 708 | **95.74** | +0.112 | 119.31 | −0.379 | 101.60 | 0.000 |

Units are the device's own linear units throughout.

**Read honestly:** the two-state model beats persistence on all six, by 13–22 % of the error, on
every split and both bands. **That is not a compliment to the model — it is a fact about the
signal: the next three-second reading is close to independent of the last one, so guessing that
nothing changes is worse than guessing the average.** Against the average, the model wins clearly on
L 0⁻2⁺ (10–12 % of the variance) and is a tie on L 1⁻3⁺ (between −1.4 % and +4.4 % depending on the
split). A model with two levels cannot do much about a signal whose scatter (265 units) is as large
as its average (274 units) and which carries large one-off excursions. **A two-state model is not
built for one-step prediction and this is what that looks like.**

### Controller: the replay over the TEST stretches

The settings replayed. "Mine" is the recommendation of section 4 for that band and split. The two
references are replayed exactly as they are written, which means the 30 s averaging is applied —
and applying it is the single most consequential thing in this table.

| Band | Split | Setting | controller step | onset in steps | trans/h | after removing each stretch's first adoption | reversals within one onset | at upper limit | at lower limit | between | mean current | TEST readings between thresholds | stretches used / hours |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 70/30 | **dwell_markov** | 30 s | 3 | **7.68** | **1.77** | **0** | 62.1 % | 15.8 % | 22.2 % | 3.887 mA | 22.4 % | 20 / 3.38 h |
| | | device GROUP_D today | 30 s | **1** | 39.61 | 33.69 | **49** | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 18.5 % | 20 / 3.38 h |
| | | Phase 10 recommendation | 30 s | **1** | 39.61 | 33.69 | **49** | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 18.5 % | 20 / 3.38 h |
| | | GROUP_D, averaging left at the replay default (3 s step) | 3 s | 10 | 2.26 | — | 0 | 67.2 % | 0.0 % | 32.8 % | 4.243 mA | 18.5 % | 99 / 3.97 h |
| | | Phase 10, same | 3 s | 10 | 2.26 | — | 0 | 66.5 % | 0.0 % | 33.5 % | 4.236 mA | 18.5 % | 99 / 3.97 h |
| | | mine on the 3 s step, onset 15 s | 3 s | 5 | 13.84 | — | 0 | 41.7 % | 24.1 % | 34.2 % | 3.406 mA | 22.4 % | 99 / 3.97 h |
| L 0⁻2⁺ | 70/30 | **dwell_markov** | 30 s | 5 | **5.81** | — | **0** | 50.0 % | 0.0 % | 50.0 % | 3.950 mA | 26.7 % | 5 / 0.52 h |
| | | device GROUP_D today | 30 s | **1** | 34.84 | 25.16 | **5** | 82.3 % | 17.7 % | 0.0 % | 4.197 mA | 3.1 % | 5 / 0.52 h |
| | | Phase 10 recommendation | 30 s | **1** | 34.84 | 25.16 | **5** | 82.3 % | 17.7 % | 0.0 % | 4.197 mA | 3.1 % | 5 / 0.52 h |
| | | GROUP_D, averaging left at the replay default | 3 s | 10 | 3.70 | — | 0 | 32.8 % | 0.5 % | 66.6 % | 3.649 mA | 3.1 % | 88 / 1.08 h |
| | | mine on the 3 s step, onset 15 s | 3 s | 5 | 14.80 | — | 0 | 34.1 % | 3.2 % | 62.8 % | 3.633 mA | 26.7 % | 88 / 1.08 h |

Three things to read off it.

1. **"Onset 30 seconds" with "averaging 30 seconds" is ONE comparison.** The controller updates once
   per averaging window, so a 30 s onset on a 30 s window is a single reading with no confirmation at
   all. My model said a single reading at that averaging is wrong about 46 % of the time; the replay
   shows what that costs — about 34 real changes an hour on L 1⁻3⁺, **49 of them undone within one
   onset in 3.4 hours**. Both references have this problem, because both specify the same pair.
2. **My settings produce 1.77 changes an hour after the first adoption in each stretch is removed,
   against the fitted model's own prediction of 1.79 an hour.** The model predicted the replay's
   answer before the replay was run.
3. **A stretch shorter than two averaging windows cannot be replayed at all.** At 30 s averaging,
   20 of 99 test stretches on L 1⁻3⁺ can be replayed — but they carry 3.38 of the 3.79 test hours.
   On L 0⁻2⁺ it is 5 of 89 stretches and 0.52 of 1.00 hours. **Half the test recording on L 0⁻2⁺ is
   in pieces too short for a 30-second averaging window to fit twice.**

### Robustness: how far each recommended value moves between splits

| Value | Band | 70/30 | 60/40 | 80/20 | Moves by | Robust by the brief's rule? |
|---|---|---|---|---|---|---|
| Averaging | both | 30 s | 30 s | 30 s | 0 | yes |
| Onset, upper | L 1⁻3⁺ | 90 s | 120 s | 120 s | one step | borderline |
| Onset, lower | L 1⁻3⁺ | 90 s | 90 s | 90 s | 0 | yes |
| Onset, upper | L 0⁻2⁺ | 120 s | 120 s | 120 s | 0 | yes |
| Onset, lower | L 0⁻2⁺ | 150 s | 150 s | 120 s | one step | borderline |
| Transition up and down | both | 30 s | 30 s | 30 s | 0 | yes |
| Blanking | both | 30 s | 30 s | 30 s | 0 | yes |
| Startup delay | both | 45 s | 45 s | 45 s | 0 | yes |
| Upper threshold | L 1⁻3⁺ | 257.90 | 261.19 | 257.78 | 3.4 units | **no** |
| Lower threshold | L 1⁻3⁺ | 195.08 | 198.08 | 195.34 | 3.0 units | **no** |
| Upper threshold | L 0⁻2⁺ | 215.09 | 215.14 | 201.07 | 14.1 units | **no** |
| Lower threshold | L 0⁻2⁺ | 157.68 | 157.34 | 172.31 | 15.0 units | **no** |

**The timings are robust; the thresholds are not.** By the brief's rule — more than one device step,
one unit for a threshold — none of the four threshold values survives. The reason is visible in the
sweep table in section 2: the separation curve is flat near its top, so the best value is weakly
determined even though the *region* is stable. What IS stable across all three splits is the region:
the best single value is 226–230 on L 1⁻3⁺ and 186–187 on L 0⁻2⁺ on every split, and the deadband
width lands on 0.40 of the signal's own scatter on four of the six band-and-split combinations and on 0.80 on the other two — both on L 0⁻2⁺, whose third split drops back to 0.40.

### Cost

Wall-clock on the container, from the scripts' own timers. One chain fitted on 32,872 TRAINING
readings: **9.4–9.9 s**. The whole recommendation — four averaging values, seven candidate
thresholds, five deadband widths, and the decision simulation — per band per split: **48–55 s**.
Every diagnostic and both sweeps together: about 19 minutes of container time in total.

---

## 4. The recommendations

Nine values per band. The pairs come from the 70/30 split, which is the split the brief mandates;
where another split disagrees it is said. The device offers separate upper and lower onset timers
(clinician manual p. 73), which this method needs, because the two thresholds are not equally hard
to read.

### L 1⁻3⁺ at 24.5 Hz

| Parameter | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **30 s** | Averaging ten readings cuts the chance of a misread reading from one in five to one in twenty (e0 and e1 both 0.134/0.215 → 0.042/0.042) and raises the real signal in the comparison by 40 %, monotonically, on every split — and 30 s is the documented maximum. | **High** — monotone on both bands, both thresholds, all three splits |
| Onset, upper | **90 s** (three comparisons) | At 30 s averaging a single comparison is wrong 45.8 % of the time and two are wrong 21.3 %, while three are wrong 2.5 % and still catch 95.7 % of real changes. | **Medium-High** — moves one step, to 120 s, on the other two splits |
| Onset, lower | **90 s** (three comparisons) | Same rule on the below-threshold state: three comparisons are wrong 0.9 % of the time and catch 97 % of real changes. | **High** — 90 s on all three splits |
| Transition up | **30 s** | The state outlasts a 30 s ramp in 99.0 % of episodes, so the loop reaches the limit it aimed at; the fitted dwell only starts to bind past about 200 s. | **Low-Medium** — this method gives an upper bound, not a value; the settling time that would fix it is not in this record |
| Transition down | **30 s** | Same evidence, and nothing in the fitted model distinguishes the two directions. | **Low-Medium** — same reason |
| Detection blanking | **30 s** | Equal to the ramp, so the loop cannot re-decide while the ramp it ordered is still running; the cost is that it truncates the 1.5 % of true dwells shorter than 30 s. | **Low** — the rule is a construction, not a measurement |
| Adaptive startup delay | **45 s** | One averaging window (30 s) so the first comparison uses a full window, plus 15 s for the start-of-recording dip I measured on this band — the first reading of a stretch sits 0.104 of the scatter low (t = −2.49 over 82 stretches) and the bias is gone by the fourth reading. | **Medium** — the dip is small and whether it is the device or the tissue is unknown |
| Upper threshold | **258** | The widest deadband whose two edges each keep at least 90 % of the best separation, centred on the best single value; the stored 210.58 is itself the best single value of the fifteen swept (separation 0.4551) and keeping it is defensible. | **Medium** — the value moves 3.4 units between splits, so it is **not** robust by the brief's rule; the region 226–261 is |
| Lower threshold | **195** | Same rule, other edge; the deadband is 63 units, 0.40 of the signal's own scatter, against the stored pair's 48.7. | **Medium** — moves 3.0 units between splits, **not** robust by the brief's rule |

### L 0⁻2⁺ at 24.5 Hz

| Parameter | Recommend | Why, in one sentence | Confidence |
|---|---|---|---|
| Averaging duration | **30 s** | Same lever, same direction: one reading in five misread at 3 s becomes one in twenty at 30 s (0.164/0.330 → 0.057/0.099). | **High** |
| Onset, upper | **120 s** (four comparisons) | Three comparisons are wrong 2.5 % of the time but catch only 95.7 %; on this noisier band four is where the wrong-decision share settles under 5 % on all three splits (2.1 %, 88 % caught). | **High** — 120 s on all three splits |
| Onset, lower | **150 s** (five comparisons) | The below-threshold state on this band is the least reliable of the four (0.8 % wrong at five comparisons, 92 % caught). | **Medium** — 150 s on two splits, 120 s on the third |
| Transition up | **30 s** | The state outlasts a 30 s ramp in 98.6 % of episodes; the bound is about 220 s. | **Low-Medium** |
| Transition down | **30 s** | Same evidence; nothing distinguishes the directions. | **Low-Medium** |
| Detection blanking | **30 s** | Equal to the ramp; it truncates 1.4 % of true dwells. | **Low** |
| Adaptive startup delay | **45 s** | One averaging window plus the measured dip — on this band the second reading of a stretch sits 0.098 of the scatter low (t = −2.46 over 71 stretches), gone by the fourth. | **Medium** |
| Upper threshold | **215** | Same deadband rule; the best single value is 186.4 and the stored pair 196.13/190.89 sits within 1.5 % of it but is only 5.2 units wide, so it is one threshold in all but name — 3.1 % of test readings ever fall between them, against 26.7 % with this pair. | **Low-Medium** — moves 14 units between splits, **not** robust; the deadband width itself halves on one split |
| Lower threshold | **158** | Same rule, other edge; deadband 57 units, 0.80 of the scatter. | **Low-Medium** — moves 15 units between splits |

**One sentence on what I would change first.** Not a threshold and not a ramp: **the onset, because
at the averaging the device already runs, today's 30-second onset is a single comparison with no
confirmation behind it at all.**

---

## 5. What this method cannot tell from this record

1. **How long the state really lasts.** The fitted dwell moves from about 10 minutes at a
   three-second grid to about 2.4 hours at a sixty-second grid, and the model's own long-gap
   prediction is wrong by a factor of ten against the measurement. The record holds at least two
   time scales and a two-state model holds one. **Every dwell number in this report is a mixing time
   under the fitted model, not an observed duration.** What the model does determine, stably across
   every scale and every split, is the chance a reading is misread — and that is what the onset and
   the averaging depend on.
2. **Anything about the settling time after a current step**, so the ramp durations rest on an upper
   bound only. My criterion says any ramp up to about 200 s leaves the loop reaching its limits; it
   cannot say which value inside that range is better. That needs the titration session already on
   the open-items list.
3. **Anything shorter than three seconds**, and nothing about the detection blanking directly — the
   blanking recommendation is a construction (equal to the ramp) with a measured cost attached, not
   a measurement.
4. **Whether a fixed threshold is the right object at all.** Agreement between readings a month or
   more apart is *negative* (−0.12 to −0.18), which means the level drifts: a value that splits the
   signal in half in the first month does not in the last. This method measures that drift but does
   not correct for it, and a threshold chosen on 27 hours spread over a year inherits it.
5. **Which of the two bands to use, or anything about the right side.** Never pooled, and the right
   sensing channel follows the left signal on this device.
6. **Anything about pain.** No pain rating enters this model anywhere. A loop tuned to track the
   band faithfully is not thereby a loop that helps, and nothing here says the band is worth
   tracking.
7. **The test recording is thin, and thinner than the hours suggest.** One hour on L 0⁻2⁺, in 89
   pieces, of which 5 are long enough to hold two 30-second averaging windows. The controller numbers
   for that band rest on 0.52 hours.

---

## 6. The files

Under `BRAVO/_agent_bridge/_probe_tl/_contest/dwell_markov/` (which is
`/usr/src/BRAVO/_agent_bridge/_probe_tl/_contest/dwell_markov/` in the container). Nothing outside
this folder was written; no production file was touched and nothing was stored.

| File | What is in it |
|---|---|
| `kernel.py` | the dwell-time skill's helpers, copied unmodified and used for the misclassification bounds, the reproducible seeds and the diagnostics |
| `d1_explore.py`, `d1_split.csv`, `d1_change_by_lag.csv`, `d1_moment_fit.csv`, `d1_startup_bias.csv` | the data as it actually is, the three splits, the agreement-against-gap curve that shows the misreading, the start-of-recording dip |
| `d2_fit.py`, `d2_fit.csv`, `d2_cross_stretch_concordance.csv` | the fits with and without the correction, the likelihood-ratio comparison, and the between-session drift check |
| `d3a_gates.py`, `d3a_convergence.csv`, `d3a_crosscheck_concordance.csv`, `d3a_thinning_gate.csv` | the convergence refit, the independent cross-check that fails at long gaps, the thinning gate that fails |
| `d4_sweeps.py`, `d4_averaging_sweep.csv`, `d4_threshold_sweep.csv` | the averaging sweep; the first threshold sweep, kept because its failure is described in section 2 |
| `d5a_recovery_and_onset.py`, `d5a_recovery.csv`, `d5a_onset_operating.csv`, `d5a_posterior_onset.csv` | the recovery check against known truth, and the onset tables on the 3 s grid |
| `d6_threshold_sweep.py`, `d6_threshold_sweep.csv` | the threshold sweep redone with independent starts, at 30 s and at 3 s averaging |
| `d7_mapping.py`, `d7_onset_operating_by_averaging.csv`, `d7_transition_completion.csv`, `d7_blanking_cost.csv` | the onset table at every averaging window, the ramp-completion table, the blanking cost |
| `d8_recommend.py`, `d8_recommendation_by_split.csv`, `d8_recommendation_detail.csv` | the recommendation rule run from scratch on each of the three splits |
| `d9_score.py`, `d9_controller_score.csv`, `d9_prediction_score.csv` | the brief's two scores on TEST, for my settings and both references, on all three splits |
