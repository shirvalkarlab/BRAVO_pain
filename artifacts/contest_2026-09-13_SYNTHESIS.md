# Method contest, the judgement: six ways of modelling RCS08's band-power dynamics, one scoring rule, and the approach the Closed-Loop module should use

Written 2026-09-13 by the orchestrator after all six reports landed. The brief every contestant
followed is `BRAVO/_agent_bridge/_probe_tl/_contest/BRIEF.md`; the six reports are beside this
file (`contest_2026-09-13_<slug>.md`). Every number below is copied from a report's section 3 or
4 and says which; nothing was re-run for this judgement. Plain language throughout; "threshold"
means the device setting.

The six, and the skill each was given:

| Entry | Method | Skill |
|---|---|---|
| A `lti_ss` | linear state-space model with an optimal (LQR) controller | control-theory |
| B `kalman_est` | a slow hidden level watched through noisy readings (Kalman filter), thirteen model variants compared by likelihood | ctrlsys-control |
| C `fopdt_lambda` | first-order-plus-dead-time plant, lambda tuning | pid-loop-tuning |
| D `dwell_markov` | two-state chain on the averaged readings, dwell times | state-dwell-time-estimation + attractor |
| E `nonlin_dyn` | state-space reconstruction, surrogate test for nonlinearity, time-scale split | dynamical-systems-theorist |
| F `ml_stats` | penalised regression and gradient-boosted trees, grid search over controller settings, block bootstrap | none (the control) |

---

## 1. What all six found, before any ranking

These are the findings every entry reached on its own. They matter more than which entry won.

**1. The device's programmed onset gives the controller one look, not thirty seconds of confirmation.** The device forms one averaged reading per averaging window and counts the onset in those readings. RCS08's GROUP_D runs a 30 s averaging window and a 30 s onset, so the onset is one comparison. Replayed with the averaging honoured, that pair switches the current 34 to 40 times an hour and undoes about 49 of those switches within one onset in 3.4 hours of held-out recording, and sits at a current limit 98 to 100 % of the time (A §3.2, B §3.2, C §3.2, D §3, E §3.2, F §3.5).

**2. Decision 148's recommendation, as it would be programmed, replays identically to today's settings.** The Phase 10 onset sweep (`_probe_tl/probe_t3_t4c_sweeps.py`) passed the replay only the onset and left the averaging at the replay's default, so on the 3 s grid its "30 s onset" meant ten confirmations; paired with the 30 s averaging it recommended, the same onset is one (found first by A, confirmed by B, C, D, E, F). B reproduced Phase 10's 2.5 switches an hour exactly when it asked the same question the same way (3 s averaging, 30 s onset: 2.53/h). So the Phase 10 measurement was right and its recommendation paired two values that were never replayed together. **The table wired in this evening (decision 149) carries those values and is corrected below.**

**3. The signal is nearly memoryless from one 3 s reading to the next, and nothing nonlinear is established.** Guessing that the next reading equals the last is worse than guessing the average on every band and split (persistence explains −27 to −62 % of the variance). The best model of any kind explains 13 to 21 % on L 1⁻3⁺ and 2 to 13 % on L 0⁻2⁺ (all six §3.1). E's surrogate test finds no nonlinearity (p = 0.35 / 0.33) and a linear autoregression does as well as its reconstructed-state model; B's nonlinear variants win the likelihood by a huge margin and then predict worse than doing nothing out of sample; F's trees buy nothing over a straight line. The slow part of a reading is about 11 to 12 % of its variance (E) and peaks near a 15 s window.

**4. The stimulation current has no measurable effect on the next reading in this record.** C: removing the current term from the model changes the prediction error by nothing on L 1⁻3⁺ and improves it on L 0⁻2⁺; the record's step tests are 20 to 34 times too blunt to have seen an effect of the plausible size. A: the current gain is the one part of its model that moves between splits. Every replay in the contest therefore runs the controller over the recorded power with a zero response curve, which is the open-loop assumption the replay's own documentation states. **Every timing value below is tuned for a loop whose gain is unknown.** The titration session (open item 30) is what would supply it.

**5. The threshold pairs in use are single thresholds in all but name.** The device's own 167 / 166 leaves 0.3 % of readings between the two; the stored pair on L 0⁻2⁺ (196.13 / 190.89, 5.2 units apart on a signal whose 30 s noise alone is 35 units) leaves 2 to 3 %. Separating the two by roughly 0.4 of the signal's scatter halves the switching rate on every band, every split and every bootstrap replicate (F, its one High-confidence recommendation; B's noise simulation puts the minimum at ± 25 units on L 1⁻3⁺ and ± 5 on L 0⁻2⁺ at 3 s averaging; D and E re-place the pair as a dead band of 0.4 to 0.8 of the scatter). C adds that the stored pair on L 1⁻3⁺ is centred 61 units below the level the signal actually sits at, which by itself pins the current at the upper limit.

**6. The record cannot decide the ramp durations, the blanking, or (cleanly) the startup delay.** F showed every blanking value from 3 to 60 s gives the identical switching rate once the onset is long; A, B, D and E each say the ramps are either unidentified, an upper bound, or not robust across splits; C's 6 min ramps and E's 3 min are rules of thumb. The startup delay splits the field: E finds no start-of-stretch dip at all, D and F find one of 0.10 to 0.2 of the scatter gone by the fourth reading (9 to 12 s), Phase 10 found 0.24 to 0.41 over 12 s, and A's 87 s and C's 60 s are model extrapolations, not measurements.

**7. The brief's split flatters every method.** Splitting by stretch count in time order leaves 87 to 96 % of the hours in training and one hour of test on L 0⁻2⁺; a 30 s averaging window can be replayed on only 20 of 99 and 5 of 89 test stretches. F's 200-replicate block bootstrap is the only robustness test that resamples recordings rather than moving a cut: it moves the onset from 36 to 90 s on L 1⁻3⁺ and 27 to 60 s on L 0⁻2⁺ where the split test moved it 0 s. **"Unmoved across splits" is a weak claim on this record, and the ranking below treats it as one.**

---

## 2. The scoring rule's numbers, side by side

Prediction on the 70/30 test set, fraction of the test variance explained (1 − error² / variance); the test mean scores 0, persistence scores −0.34 to −0.51. Each entry scored a slightly different reading count (its own handling of stretch ends), so treat differences under 0.03 as ties.

| Entry | L 1⁻3⁺ | L 0⁻2⁺ | Note |
|---|---|---|---|
| A LTI | 0.140 | 0.097 | |
| **B Kalman (L4, two components)** | **0.162** | **0.128** | best on both bands |
| C FOPDT | 0.108 | 0.039 | the current term contributes nothing |
| D two-state chain | −0.014 | 0.119 | a two-level model; not built for one-step prediction |
| E reconstructed state | 0.130 | 0.075 | a linear AR on the same state does as well |
| F 20-lag regression | 0.176 | 0.080 | trees 0.171 / 0.058 |

Controller replay on the common held-out set (L 1⁻3⁺: the 20 test stretches of at least 60 s, 3.4 h, the set every 30 s configuration can replay; F and B replayed at 3 s averaging over all 93 to 99 stretches, 3.6 to 4.0 h, and say so). Switches per hour; undone = a switch reversed within one onset.

| Configuration (L 1⁻3⁺) | Averaging | Onset | Switches/h | Undone | At upper | At lower | Between | Mean mA | Readings between thresholds |
|---|---|---|---|---|---|---|---|---|---|
| Device today (GROUP_D timing, stored 210.6 / 161.9) | 30 s | 30 s | 39.6 | 49 | 90 % | 9 % | 2 % | 4.48 | 18–21 % |
| Device today with its own 167 / 166 | 30 s | 30 s | 17.4 | 16 | 94 % | 6 % | 0 % | 4.59 | 0.3–0.5 % |
| Decision 148 as programmed | 30 s | 30 s | 35.9–39.6 | 43–51 | 87–91 % | 7–9 % | 2–6 % | 4.44–4.52 | 18–22 % |
| A (avg 9 s, onset 72 s, 328.6 / 232.3) | 9 s | 72 s | 3.20 | 0 | 25 % | 31 % | 45 % | 2.99 | 25 % |
| B (avg 3 s, onset 30 s, stored pair) | 3 s | 30 s | 2.53 | 0 | 74 % | 0 % | 26 % | 4.36 | 19 % |
| B (avg 3 s, onset 60 s, stored pair) | 3 s | 60 s | 1.12 | 0 | 36 % | 0 % | 64 % | 3.71 | 19 % |
| C (avg 30 s, onset 60 s, 477 / 18) | 30 s | 60 s | 0.30 | 0 | 0 % | 0 % | 100 % | 3.10 | 98 % |
| D (avg 30 s, onset 90 s, 258 / 195) | 30 s | 90 s | 7.68 (1.77 after each stretch's first adoption) | 0 | 62 % | 16 % | 22 % | 3.89 | 22 % |
| E (avg 15 s, onset 60 s, 280 / 201) | 15 s | 60 s | 7.30 | 0 | 46 % | 14 % | 40 % | 3.66 | 33 % |
| F (avg 3 s, onset 48 s, 239 / 133) | 3 s | 48 s | 1.01 | 0 | 21 % | 0 % | 79 % | 3.46 | 39 % |

L 0⁻2⁺ rests on 0.5 to 1.1 test hours and no entry claims it; the pattern is the same (references 30 to 35 switches/h with 4 to 7 undone, at a limit 100 % of the time; every entry 0 to 6.6/h with 0 undone).

Robustness by the brief's rule (a timing that moves more than 3 s, or a threshold more than one unit, between the 60/40, 70/30 and 80/20 splits is not robust):

| Entry | Timings | Thresholds | Own extra check |
|---|---|---|---|
| A | all identical | move 2–3.4 units on L 1⁻3⁺: no | the current gain moves 45 % |
| **B** | **all nine identical** | **identical** (it keeps the stored pair; its minimum separation ± 25 / ± 5 identical at all splits) | Riccati cross-checked against `ctrlsys.sb02md` to 10⁻¹² |
| C | all identical | upper moves 4.1 / 1.1 units: no | |
| D | identical or one step | move 3–15 units: no | the fitted chain predicted the replay's rate (1.79 vs 1.77/h) |
| E | averaging / onset / blanking / startup identical; ramps move 30–41 s: no | L 1⁻3⁺ move 2.2–2.6: no; L 0⁻2⁺ under 1: yes | two rule versions replaced for not being robust, recorded |
| F | onset / blanking / thresholds identical across splits; ramps not | | **bootstrap: onset 36–90 s / 27–60 s, threshold gap 53–132 units** |

Cost of the fit on training: A 0.9 s, C 2 s, F 2.5 s (plus 315 s for the bootstrap), E 22 s, D 50 s, B 52–67 s (plus 260–470 s for the thirteen-model comparison). All affordable in a request or a daily pass.

---

## 3. The judgement

**The approach to use is B's: treat the band power as a slow hidden level seen through noisy readings, fit that model on the record, and derive the timing from a noise simulation of the fitted model — "how much separation and how many confirmations keep noise-only crossings at or below one an hour" — rather than from the raw switching sweep.** It is the best out-of-sample predictor on both bands, the only entry whose nine values are identical at all three splits, it reproduced Phase 10's measurement exactly when asked the same question, and its design table (B §3.3) is the one result in the contest that reads as a rule the module can compute for any participant: at 3 s averaging a 30 s onset needs ± 25 units on L 1⁻3⁺; at 30 s averaging no onset under 120 s reaches one false crossing an hour. F's bootstrap is adopted as the robustness test the module should report, because it is the only one that moved when the split test did not.

**With two corrections taken from the other entries.**

- **Threshold placement is not B's.** B keeps the stored pair and its replay sits at the upper limit 74 % of the time; A, D and E re-centre the pair on the participant's own level of the averaged signal (A: level ± residual scatter; E: the 40th and 60th percentiles) and get a balanced loop (25 / 31 / 45 % for A, 46 / 14 / 40 % for E). C's finding that the stored pair is centred 61 units below the signal's level is the reason. So: B's separation rule for the width, and an occupancy rule for the centre. Placement itself stays decision 139's (a capture question); the module's job is to say when the stored pair is too narrow or off-centre, and by how much.
- **Averaging is 3 s, not 30 s, and it is the validated feature.** B and F (High), A (9 s) and E (15 s) all put the averaging well under the 30 s the device runs; only C and D keep 30 s, and D's own arithmetic then needs 90 to 150 s onsets. The project's own biomarker was validated on a 4.096 s window (`percept_adaptive.BIOMARKER_INTEGRATION_S`), and the parameter card has said since 2026-09-03 that the device's averaging is the feature definition. 3 s is the nearest the device grid offers to that window; the device's own Dual default of 1.2 s is indistinguishable on this record (B §5). D's point survives as a rule: whatever the averaging, the onset must give at least ten looks at 3 s, or three to five at 30 s.

**The recommendation, per participant (RCS08, both left bands; every value inside a documented range where one exists):**

| Parameter | Value | Why, one sentence | Confidence |
|---|---|---|---|
| Averaging | **3 s** | The validated feature's window is 4.1 s; at 3 s a 30 s onset is ten confirmations, and every entry that shortened the averaging cut the switching rate to under 8/h with nothing undone. | High (B, F; A and E within a factor of five) |
| Onset, upper and lower | **30 s** (ten confirmations at 3 s) | B's noise simulation: the shortest onset holding noise-only crossings at or below one an hour at the stored separation; replays 2.5/h with 0 undone on L 1⁻3⁺ and reproduces Phase 10's own number; 60 s leaves the current mid-ramp 64 % of the time. F's bootstrap says 36–90 s at 3 s averaging is one recommendation, so 30–60 s are the same answer. | High on the direction, Medium on the value (bootstrap) |
| Detection blanking | **30 s** (= onset) | Undetermined by the record (F: identical results from 3 to 60 s); equal to the onset stops a decision being re-classified while its ramp runs, and is what the device runs today. | Low |
| Transition up / down | **30 s** each | Undetermined (A, B, D, E: unidentified, an upper bound, or not robust); inside every entry's acceptable set except C's 6 min and E's 3 min; indistinguishable from today's 4 s at every onset that filters. | Low |
| Adaptive startup delay | **15 s** | The measured dips (Phase 10, D, F) are gone by 12 s; E finds none; 15 s is the shortest value the device has been seen to accept above 12 s. The model-derived 60–87 s (A, C) are settling times of the estimator, not of the device, and B says so. | Medium |
| Thresholds | **separate the pair: at least ± 25 units about its centre on L 1⁻3⁺, ± 40 on L 0⁻2⁺, and centre it on the participant's own median averaged reading** | The device's 167 / 166 and the stored 196 / 191 are single thresholds; the stored 210.6 / 161.9 on L 1⁻3⁺ is at the edge of sufficient (± 24.3) and centred 61 units low. | High that they must be separated; Medium on the width; the centre is decision 139's |

**What this changes on the page today.** The decision-148 row of the timing table (`ClosedLoopDeployment/timing_recommendation.py`) is replaced by the values above; averaging 30000 → 3000 ms is the one change that flips the card's onset-averaging coupling from "inoperative" to ten confirmations, and it changes the card's duty-cycle replay. Everything else in decision 149's wiring stands.

---

## 3a. A correction to the averaging judgement above, made the same evening

Asked directly why every entry seemed to assume the averaging duration rather than tuning it, and
whether it was in fact tuned from the data: it was, by all six, but the comparison in §2 above that
this synthesis leaned on -- switching rate at each averaging duration -- carries the same confound
several entries warned about in the Phase 10 recommendation: **it compared different averaging
windows at one onset held fixed in seconds**, and a fixed onset in seconds is a different number of
controller confirmations at every averaging duration. F's own table said this in words; the mistake
was not catching that the same shape of comparison, once folded into one ranking table across six
entries with six different onset choices, was no longer controlled for it either.

**Re-measured directly**, holding the threshold pair FIXED and re-tuning the onset PROPERLY at each
averaging duration (the shortest number of controller confirmations that reaches zero switches
undone across the whole 31-hour record, at that averaging window): the switching rate is **nearly
flat, 3.3 to 3.9 an hour, from 3 s all the way to 30 s** on L 1-3+ with the calibrated grid's own
stored pair (210.58 / 161.90), and 3.1 to 4.4 an hour with the device's actual programmed pair
(167 / 166); L 0-2+ runs 3.0 to 3.9 an hour across the same range. **The switching-rate argument for
short averaging does not hold up once the onset is compared fairly.**

**What does differ, and by a lot, is how long a confirmed decision takes.** At 3 s averaging the
shortest onset reaching zero undone switches is 21-24 s; at 30 s averaging the same stability needs
90-180 s -- four to six times longer -- because each controller confirmation costs a whole
averaging window regardless of how short it is. That is the real, defensible reason to keep the
averaging short: not fewer switches, but a confirmed answer several times faster at an equal
switching rate.

**This also reconciles A and E, who never claimed the switching-rate framing.** A's 9 s and E's
15 s are answers to different questions -- how well a short window tracks a fitted slow signal (A),
and how much of a reading's variance is genuinely slow rather than noise dressed as slow (E) -- and
neither number was ever compared against the controller's own switching behaviour at a properly
re-tuned onset. Both remain correct answers to their own questions; neither is a counter-example to
the response-time argument above, because that argument does not depend on switching rate at all.

**The table's value is unchanged (3 s); the stated reason is corrected** in
`ClosedLoopDeployment/timing_recommendation.py`. Measured with a throwaway script against the same
series the contest used (`_agent_bridge/_probe_tl/_ranges/averaging_sweep.py`, gitignored, not
committed); the numbers above are quoted from its output.

## 4. Implementation plan for the Closed-Loop module

Each task is independently mergeable; the order is the dependency order. Acceptance criteria are what the test or the live proof must show.

**T1. Correct the timing table (this session).** `timing_recommendation.py`: averaging 3000, onset 30000 / 30000, blanking 30000, transitions 30000 / 30000, startup 15000, with the contest as the provenance and the reasons above. Acceptance: the parameter card on L 1⁻3⁺ shows averaging 3 s with confirmations = 10 and no onset coupling; the duty replay's transitions per hour lands near B's 2.5/h; both suites green; field count and difference count reported.

**T2. The simulation card replays the programmed group's timing, averaging included.** `simulation.py` and the page's CL-DBS card take `averaging_ms`, `onset_ms`, `detection_blanking_ms`, `transition_*_ms` from `device_facts.active_sensing_group_timing` (available since decision 149) instead of the white-paper defaults, and draw a second run at the recommended timing. Acceptance: at GROUP_D's settings the card reproduces 39.6 switches/h with 49 undone on the 20-stretch set (B, D, E agree on those numbers); at the recommended settings, 2.5/h with 0.

**T3. A confirmations-and-separation design rule in the module.** Port B's noise simulation: fit the two-component local-level model on the participant's stretches (state-space, `ctrlsys.sb02md` for the settled weight, cross-checked by iteration), then for each averaging × onset on the device grid compute the minimum separation that holds noise-only crossings at ≤ 1/h. Report it on the parameter card beside the thresholds ("the stored pair is ± 24.3; the rule needs ± 25 at this timing"). Acceptance: reproduces B's table (± 25 at 3 s / 30 s on L 1⁻3⁺; "never" at 30 s / 30 s); a constructed white-noise series gives the analytic answer.

**T4. Threshold occupancy check.** For the stored pair, the fraction of averaged readings above, between and below, the pair's centre against the participant's median level, and a warning when between < 10 % or the centre is more than half the pair's width from the median. Acceptance: on RCS08 the device's 167 / 166 reads 0.3 % between and is flagged; the stored L 1⁻3⁺ pair reads 18–21 % between and "centred 61 units below the median".

**T5. Robustness as an interval, not a point.** F's block bootstrap over stretches (200 replicates) for the onset and the separation, reported as an interval on the card and in the ledger. Acceptance: on RCS08 the onset interval covers 36–90 s on L 1⁻3⁺ and the card says "36–90 s are one recommendation".

**T6. The startup dip, measured in the module.** The first-N-readings bias per stretch against the stretch's own later level, with its standard error, feeding the startup-delay row (today the row cites the Phase 10 probe). Acceptance: reproduces D's 0.104 of the scatter at the first reading over 82 stretches, and states E's null result when the baseline is the stretch's median.

**T7. The gain.** Nothing in T1–T6 closes the loop: the response of power to current is unmeasured (C, A, B §5). The titration session card (decision 146, open item 30) already describes the session; after it is recorded, `post_ramp.margin_becomes_available` switches the margin on and the pooled slope (decision 126) supplies the gain, at which point T2's replay should switch from the zero response curve to the fitted one (M1) and the ramp durations become measurable. Acceptance: the simulation card's M1 run differs from M0 on the titration run's data.

Not in scope, for the PI: the right sensing channel is ganged to the left signal (every number here is a left-signal number); nothing in the contest touched a pain rating, so none of it says the loop helps.

---

## 5. Files

The six reports and their tables under `BRAVO/_agent_bridge/_probe_tl/_contest/<slug>/` (gitignored scratch); the brief at `_contest/BRIEF.md`; this judgement; the timing table change and its proof in decision 150.
