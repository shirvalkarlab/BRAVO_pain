# Method contest, entry A: a linear state-space model of RCS08's band power, used to set the closed-loop timing and thresholds

**Slug `lti_ss`. Written 2026-09-13.** Answers the contest brief at
`BRAVO/_agent_bridge/_probe_tl/_contest/BRIEF.md` with the method assigned to this entry: fit a
linear, time-invariant model of the band power on the device's 3-second clock, with the stimulation
current as the input, and turn the fitted model into a recommended value for each device setting.

**Where this lives and whether anyone can see it.** These nine numbers are settings a clinician types
into the Medtronic tablet. On this platform they appear on the **Closed-Loop Deployment page**, in
the "Full parameter recommendation" card and in the "CL-DBS simulations" card at the foot of the
page, which replays the controller with an onset and two ramp durations. **Nothing in this report is
on any page today**: it is an analysis written to a file, and the platform does not write to the
device.

---

## 1. The method in five sentences

I treated the band power as the output of a simple linear machine driven by random shocks, and fitted
that machine to the training part of the record: today's reading is a weighted sum of the last few
readings, plus the stimulation current, plus a random shock. I chose how many past readings to use —
one to four — by an information score computed on the training part only, and I report the input
gain, the model's own time constants and the size of the random shock. From the fitted machine I
computed how many 3-second readings should be averaged before the device compares them (the point
where averaging has removed as much noise as it can without smearing the slow movement the loop is
meant to follow), and how long the device should hold a crossing before acting (the shortest hold at
which the fitted noise, simulated for 200 hours, produces no more than one undone switch a day). I
also designed a textbook optimal linear controller on the same fitted machine, using the Riccati
solver `sb02md` from the `ctrlsys` library, and read its closed-loop time constant off as the ramp
duration; where that optimal controller wants something the Percept cannot do, I say so rather than
pretending it can. Everything was then replayed through the platform's own controller simulation on
the held-out part of the record, beside the device's current settings and the Phase 10
recommendation.

---

## 2. The model I fitted, with its numbers

One model per sensing contact — never pooled across contacts. Fitted on the training stretches only,
at the 70/30 split.

### 2a. How many past readings, and how well the model describes the signal

The information score kept falling as I added past readings, and the assignment caps the model at
four states, so **four** was chosen at the cap on both contacts and at all three splits. This is a
cap, not a minimum, and I say so rather than presenting four as the model's own preference. The four
candidates were fitted on the identical rows so their scores are comparable (an earlier pass compared
scores computed on different numbers of rows, which is not a comparison; that pass was discarded).

| Contact, 24.5 Hz | 1 past reading | 2 | 3 | 4 |
|---|---|---|---|---|
| L 1⁻3⁺ information score | 356,171.4 | 352,564.3 | 350,896.8 | **349,706.0** |
| L 0⁻2⁺ information score | 329,255.3 | 328,141.3 | 327,491.9 | **327,013.6** |

### 2b. The fitted numbers

| Quantity | L 1⁻3⁺ 24.5 Hz | L 0⁻2⁺ 24.5 Hz |
|---|---|---|
| Weights on the last four readings | 0.11712, 0.22755, 0.19267, 0.21855 | 0.04557, 0.19662, 0.18657, 0.18991 |
| Constant term | 68.460 | 79.718 |
| Long-run average level of the band power | 280.46 device units | 209.05 device units |
| The model's four time constants | **29.31 s**, 6.51 s, 6.27 s, 6.27 s | **18.21 s**, 5.98 s, 5.98 s, 6.08 s |
| All four modes decay (the model is stable) | yes (largest 0.9027 per 3 s step) | yes (largest 0.8481) |
| Size of the random shock, standard deviation | 247.37 device units | 217.78 |
| The same, computed robustly (spikes set aside) | 95.89 | 72.42 |
| Current term, per mA | **−2.126 ± 1.114** (t = −1.91) | **−2.672 ± 1.079** (t = −2.48) |
| Long-run change in band power per mA | **−8.71 ± 4.55 units/mA** | **−7.01 ± 2.81 units/mA** |
| Information score with the current in / out | 349,712.8 / **349,706.0** | 327,017.8 / **327,013.6** |

**The most important number in this table is the one the model rejects.** On both contacts the
information score is *worse* with the stimulation current in the model than without it, so on this
record **the current does not measurably move the band power on the 3-second clock**. The fitted
direction is negative on both contacts — more current, less band power — and the size, about 7 to 9
device units per mA, agrees in sign and order with the stored pooled titration estimate for this
participant (−3.62 device units per mA on L 1⁻3⁺ at 20.5 Hz, decision 128, whose own interval also
spans zero). But its uncertainty is large enough that zero is not excluded on L 1⁻3⁺, and on the
60/40 split the same fit gives −1.20 ± 1.23, nearly half the 70/30 value. **Every ramp-duration
number below rests on a gain the record does not establish.**

### 2c. What the model says about time scales (frequency check, `tb05ad`)

The identified machine passes slow movement much more strongly than fast movement. Evaluating the
fitted response at a range of periods:

| Period | 6 s | 12 s | 30 s | 60 s | 5 min | 30 min |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ gain | 1.158 | 0.988 | 0.815 | 1.337 | 3.498 | 4.076 |
| L 0⁻2⁺ gain | 1.183 | 0.984 | 0.818 | 1.282 | 2.455 | 2.617 |

Movement slower than five minutes comes through about four times (L 1⁻3⁺) and two and a half times
(L 0⁻2⁺) as strongly as movement at 30 seconds. That is the same conclusion the model's slowest time
constant gives — 29.3 s and 18.2 s — and it is the reason the averaging answer below is short rather
than long: there is a real slow component to follow, and over-averaging hides it.

### 2d. How the model became each device setting

| Setting | The rule, stated once | L 1⁻3⁺ | L 0⁻2⁺ |
|---|---|---|---|
| Averaging | the window that minimises the squared error between the average of the last N readings and the model's slow component now, computed from the model's own covariances | 9 s (3 readings) | 9 s (3 readings) |
| Residual scatter of a 9 s average about the slow component | — | 48.12 units | 45.12 units |
| Thresholds | the fitted long-run level ± 1 × that residual scatter | 328.58 / 232.34 | 254.17 / 163.92 |
| Onset | shortest hold, on the 9 s controller clock, giving ≤ 1 undone switch a day over 200 simulated hours of the fitted noise | 72 s (8 steps) | 63 s (7 steps) |
| Ramp up and down | the closed-loop time constant of the optimal controller at the input weight that makes its own current use equal the device's half-span (1.70 mA) | 27 s (weight 562.3; current use 1.485 mA; closed-loop 27.54 s) | 18 s (weight 316.2; current use 1.328 mA; closed-loop 16.98 s) |
| Detection blanking | one ramp plus one slow time constant, rounded to the controller clock | 54 s | 36 s |
| Adaptive startup delay | three slow time constants (when the model has forgotten its starting state to within 5 %) | 87 s | 54 s |

The averaging answer is a sharp minimum, not a flat valley:

| Averaging window | 3 s | 6 s | **9 s** | 12 s | 15 s | 30 s | 60 s | 300 s |
|---|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ error against the slow component | 169.09 | 75.24 | **48.12** | 51.21 | 66.81 | 115.91 | 160.49 | 202.62 |
| L 0⁻2⁺ | 155.38 | 69.69 | **45.12** | 46.25 | 57.46 | 92.07 | 118.82 | 136.30 |

**The 30 s averaging the device runs today is 2.4 times worse at tracking the slow movement than 9 s
is, on both contacts.** That is this method's clearest disagreement with the current settings and
with the Phase 10 recommendation.

The onset search, on the fitted noise (200 simulated hours, shocks resampled from the training
residuals so the heavy tail is kept):

| Onset | 9 s | 18 s | 27 s | 36 s | 45 s | 54 s | **63 s** | **72 s** | 81 s | 90 s |
|---|---|---|---|---|---|---|---|---|---|---|
| L 1⁻3⁺ switches/h | 154.50 | 60.42 | 32.45 | 19.29 | 12.43 | 8.46 | 6.03 | **4.38** | 3.10 | 2.33 |
| L 1⁻3⁺ undone switches/day | 1057.68 | 156.24 | 39.12 | 15.48 | 4.08 | 2.04 | 1.32 | **0.60** | 0.12 | 0.00 |
| L 0⁻2⁺ switches/h | 183.36 | 69.30 | 35.65 | 19.50 | 11.39 | 6.52 | **3.60** | 2.13 | 1.33 | 0.83 |
| L 0⁻2⁺ undone switches/day | 1503.72 | 240.36 | 63.96 | 18.72 | 6.36 | 1.56 | **0.72** | 0.12 | 0.12 | 0.00 |

**Where the device cannot express what the optimal controller wants.** The optimal linear controller
designed on this model sets the current continuously, in proportion to the last four readings; the
gains at the chosen input weight are (−0.0537, −0.0935, −0.0767, −0.0846) on L 1⁻3⁺. The Percept
cannot do that. It has two fixed current limits and a ramp between them, driven by a two-level
comparison. So only one thing survives the translation — the speed at which the optimal controller
would move, 27.5 s and 17.0 s — and that is what I used for the ramp durations. The optimal
controller's proportional action, and its use of more than the newest reading, are both lost. I also
had to pick the input weight rather than derive it; I picked the weight at which the optimal
controller's own current use, 1.485 mA and 1.328 mA of standard deviation, just fits inside the
device's half-span of 1.70 mA, and I state that choice because a different weight gives a different
ramp: at a weight of 1 the optimal controller wants to move in 4.3 s and to use about 30 mA, which
the device does not have.

---

## 3. The scoring rule's numbers

### 3.0 The split, and a warning about it

Sorted by start time, the first 70 % of stretches by count are training and the last 30 % are test.
**Splitting by stretch count does not split the hours**, because the late stretches are shorter:

| Band | Stretches total | TRAIN stretches | TRAIN hours | TEST stretches | TEST hours | TEST share of the hours |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ 24.5 Hz | 325 | 227 | 27.611 | 98 | 3.978 | **12.6 %** |
| L 0⁻2⁺ 24.5 Hz | 294 | 206 | 26.260 | 88 | 1.162 | **4.2 %** |

At 80/20 the L 0⁻2⁺ test slice is 0.698 h — 2.5 % of the record. Every test number for L 0⁻2⁺ below
rests on about one hour of recording, and I do not treat it as settled.

**A second sample-size problem, and how I handled it.** The platform's replay refuses a stretch
shorter than two averaging windows. A 30-second averaging configuration therefore cannot be replayed
on a stretch shorter than 60 s, and most test stretches are shorter than that (the median stretch is
24 s). To keep the comparison like-for-like I report a **common set** — the test stretches every
configuration can replay — and, separately, each configuration on **every test stretch it can
handle**, with the count and hours stated on each row. I also replayed the same training-fitted
configurations over the **whole record**, which is not a test score and is labelled as such, because
on L 0⁻2⁺ the common set is six stretches.

**One convention to be aware of before reading the limit columns.** The platform's replay module
takes high band power to mean *raise* the current (`replay.DEVICE_HIGH_POWER_ACTION = "increase"`),
while the contest brief describes the opposite. Every configuration here was replayed with the
module's own default, so the comparison between configurations is unaffected; if the device's true
convention is the other way round, the "at the upper limit" and "at the lower limit" columns swap for
every row at once and no comparison below changes.

### 3.1 Prediction: one step ahead on the test stretches

| Band | Split | TEST readings | TEST scatter | **This model** | Persistence (next = last) | The TEST mean |
|---|---|---|---|---|---|---|
| L 1⁻3⁺ | 70/30 | 3,953 | 163.44 | **RMSE 151.61, 14.0 % of variance** | RMSE 189.04, −33.8 % | RMSE 163.42, 0 % |
| L 1⁻3⁺ | 60/40 | 4,796 | 164.46 | **149.61, 17.3 %** | 184.97, −26.5 % | 164.45 |
| L 1⁻3⁺ | 80/20 | 3,387 | 168.79 | **156.66, 13.9 %** | 195.68, −34.4 % | 168.77 |
| L 0⁻2⁺ | 70/30 | 932 | 105.47 | **100.25, 9.7 %** | 124.98, −40.4 % | 105.42 |
| L 0⁻2⁺ | 60/40 | 1,827 | 97.58 | **91.93, 11.2 %** | 115.75, −40.7 % | 97.56 |
| L 0⁻2⁺ | 80/20 | 535 | 103.41 | **99.72, 7.0 %** | 124.54, −45.1 % | 103.31 |

**The model beats persistence on every band at every split, by a wide margin** — persistence is
*worse* than simply quoting the average, by 27 % to 45 % of the variance, because two consecutive
3-second readings are almost unrelated. The model also beats the test mean, but only just: it removes
7 % to 17 % of the variance. **So the honest reading is that the band power on this record is mostly
unpredictable noise with a small, real, slow component, and the model has found that component and
nothing more.**

### 3.2 Controller score on the test stretches: the common set (70/30)

Six numbers per configuration, plus the fraction of test readings sitting between the two thresholds.
"Undone switches" counts a switch reversed within one onset duration.

**L 1⁻3⁺ 24.5 Hz — 20 common test stretches, 3.44 h (3.38 h for the 30 s averaging rows)**

| Configuration | Switches / h | Undone | At upper limit | At lower limit | Between | Mean current | Readings between thresholds |
|---|---|---|---|---|---|---|---|
| **lti_ss recommendation** | **3.20** | **0** | 24.7 % | 30.8 % | 44.5 % | **2.994 mA** | 24.6 % |
| lti_ss timing, stored thresholds | 3.20 | 0 | 69.5 % | 0.0 % | 30.5 % | 4.290 mA | 18.2 % |
| Device GROUP_D today | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 18.2 % |
| Phase 10 recommendation | 39.61 | 49 | 89.7 % | 8.6 % | 1.7 % | 4.478 mA | 18.2 % |

**L 0⁻2⁺ 24.5 Hz — 6 common test stretches, 0.615 h (0.592 h for the 30 s averaging rows)**

| Configuration | Switches / h | Undone | At upper limit | At lower limit | Between | Mean current | Readings between thresholds |
|---|---|---|---|---|---|---|---|
| **lti_ss recommendation** | **0.00** | 0 | 0.0 % | 0.0 % | 100.0 % | 3.100 mA | 39.7 % |
| lti_ss timing, stored thresholds | 8.13 | 0 | 50.8 % | 6.5 % | 42.7 % | 3.853 mA | 3.1 % |
| Device GROUP_D today | 35.49 | 5 | 81.7 % | 18.3 % | 0.0 % | 4.177 mA | 3.1 % |
| Phase 10 recommendation | 35.49 | 5 | 81.7 % | 18.3 % | 0.0 % | 4.177 mA | 3.1 % |

**On L 0⁻2⁺ my configuration makes no switch at all on the test slice, and the current never leaves
its starting value of 3.100 mA.** I checked whether that is the design or the slice, and it is the
slice: on the *training* part, the same thresholds put 24.4 % of the 9-second averaged readings above
the upper one and 37.1 % below the lower one, so they are crossed constantly there; and the same
configuration over the whole record switches 2.03 times an hour (table 3.4). The six test stretches,
0.6 h in all, happen to sit inside the band. **A test slice this small cannot score a controller, and
I am not claiming it did.**

### 3.3 Two findings inside these tables that matter more than my recommendation

1. **The device's current settings and the Phase 10 recommendation give byte-identical replay
   results, on every band and every split.** They differ only in the ramp durations, 4 s against
   30 s. With the averaging at 30 s the controller updates once per 30 seconds, and a ramp of either
   4 s or 30 s completes inside one update, so the replay cannot tell them apart. **Changing the ramp
   from 4 s to 30 s, as Phase 10 recommends, changes nothing that this replay can see.**
2. **With the averaging at 30 s, a 30-second onset is one controller update — that is, no
   confirmation at all.** That is why both reference rows switch 22 to 40 times an hour with dozens
   to hundreds of undone switches, where the Phase 10 onset table reports about 2.5 switches an hour
   for a 30 s onset. The Phase 10 table was computed at the replay's default averaging, which leaves
   the controller on the 3-second clock, so its "onset 30 s" means ten confirmations and the device's
   "onset 30 s" alongside a 30 s average means one. **The two numbers are not the same setting.**
   This rests on the replay module treating the averaging window as the controller's update interval
   (`replay._average_to_device_grid`); whether the real Percept re-evaluates its onset timer on the
   3-second reading clock while comparing a 30-second average is not documented anywhere I can check,
   and it is the single most consequential open question in this report.

### 3.4 The same configurations over the whole record (context, NOT a test score)

**L 1⁻3⁺** (321 stretches / 31.17 h for the 9 s rows; 102 / 29.71 h for the 30 s rows)

| Configuration | Switches / h | Undone | Upper | Lower | Between | Mean current | Readings between |
|---|---|---|---|---|---|---|---|
| lti_ss recommendation | 2.37 | 0 | 22.8 % | 40.4 % | 36.8 % | 2.800 mA | 18.3 % |
| lti_ss timing, stored thresholds | 2.53 | 0 | 48.5 % | 23.7 % | 27.8 % | 3.524 mA | 13.9 % |
| GROUP_D today = Phase 10 | 24.30 | 253 | 66.2 % | 33.4 % | 0.4 % | 3.656 mA | 13.8 % |

**L 0⁻2⁺** (292 / 27.03 h; 76 / 25.68 h)

| Configuration | Switches / h | Undone | Upper | Lower | Between | Mean current | Readings between |
|---|---|---|---|---|---|---|---|
| lti_ss recommendation | 2.03 | 3 | 18.0 % | 33.3 % | 48.7 % | 2.840 mA | 32.5 % |
| lti_ss timing, stored thresholds | 2.85 | 0 | 38.8 % | 39.5 % | 21.7 % | 3.089 mA | 2.0 % |
| GROUP_D today = Phase 10 | 22.24 | 197 | 52.0 % | 47.9 % | 0.1 % | 3.170 mA | 2.0 % |

### 3.5 Robustness: how far each recommendation moves when the split moves

The brief's rule: a value that moves more than one device grid step — 3 s for a timing, one unit for
a threshold — between the 60/40, 70/30 and 80/20 splits is not robust.

| Recommendation | L 1⁻3⁺ at 60/40, 70/30, 80/20 | Movement | Robust? | L 0⁻2⁺ | Movement | Robust? |
|---|---|---|---|---|---|---|
| Averaging | 9, 9, 9 s | 0 s | **yes** | 9, 9, 9 s | 0 s | **yes** |
| Onset (both timers) | 72, 72, 72 s | 0 s | **yes** | 63, 63, 63 s | 0 s | **yes** |
| Ramp up and down | 27, 27, 27 s | 0 s | **yes** | 18, 18, 18 s | 0 s | **yes** |
| Detection blanking | 54, 54, 54 s | 0 s | **yes** | 36, 36, 36 s | 0 s | **yes** |
| Startup delay | 87, 87, 87 s | 0 s | **yes** | 54, 54, 54 s | 0 s | **yes** |
| Upper threshold | 331.16, 328.58, 327.78 | **3.38 units** | **no** | 255.14, 254.17, 254.19 | 0.97 units | yes (just) |
| Lower threshold | 234.14, 232.34, 232.12 | **2.02 units** | **no** | 163.86, 163.92, 164.41 | 0.55 units | yes |

**Every timing is unmoved by the split; both thresholds on L 1⁻3⁺ are not, by the brief's own rule.**
The underlying reason is the current term: on L 1⁻3⁺ it reads −2.126 ± 1.114 at 70/30, −1.197 ± 1.234
at 60/40 and −2.141 ± 1.047 at 80/20 — a factor of nearly two, on a quantity whose own uncertainty
already covers zero. The model's time constants, by contrast, move by less than 1 %: 29.31, 29.44 and
29.14 s on L 1⁻3⁺; 18.21, 18.35 and 18.15 s on L 0⁻2⁺. **The part of this model that describes the
signal is steady; the part that describes what stimulation does to it is not.**

### 3.6 Cost

Wall-clock, from the script's own timer, in the container, at 70/30: the least-squares fit on the
training stretches took **0.279 s** (L 1⁻3⁺) and **0.237 s** (L 0⁻2⁺); the whole design — order
selection, the fit with the current included, the covariance solve, the averaging sweep, a 41-point
optimal-controller sweep and a 200-hour simulated onset search — took **0.89 s** and **0.80 s**. Over
all six band-and-split combinations the least-squares fits ranged 0.238–0.285 s and the full designs
0.79–0.89 s. The four replay passes per band and split are the expensive part at about 2 s each; the
whole contest run, both bands, three splits, four configurations, three replay sets, was 18.1 s.

---

## 4. Recommended value for each of the nine settings

Two tables, one per band, never pooled. Every timing is a multiple of the 9-second controller clock
the averaging recommendation creates. Every value sits inside its documented range where the FDA
approval summary gives one (onset 0–6 min; ramps 250 ms–30 min; averaging 0–30 s; thresholds
0.55–400 µVrms); blanking and startup delay have no documented range at all, and for those I say what
the device has been seen to accept on this participant.

### L 1⁻3⁺ at 24.5 Hz

| Setting | Recommend | Reason, one sentence | Confidence |
|---|---|---|---|
| Onset, upper timer | **72 s** | Under 200 simulated hours of the fitted noise, 72 s is the shortest hold that leaves no more than one switch a day undone (0.60), and on the held-out stretches it produced 3.20 switches an hour with none undone against the device's 39.61 with 49 undone. | **High** — unmoved across all three splits, and the replay on the held-out data agrees with the simulation |
| Onset, lower timer | **72 s** | The fitted model is one process with one noise size, so it gives no reason to treat a rise differently from a fall; equal timers is the model's answer, not a convention. | **High** for the equality, same evidence as above |
| Ramp up | **27 s** | The optimal controller designed on this model, at the input weight where its own current use just fits the device's 1.7 mA half-span, corrects in 27.5 seconds. | **Low** — it rests entirely on a current gain the record does not establish (−2.126 ± 1.114, and −1.197 ± 1.234 at another split) |
| Ramp down | **27 s** | Same calculation; the model is symmetric and gives no reason for down to differ from up. | **Low**, same reason |
| Averaging | **9 s** (3 readings) | Averaging three readings is the point where noise removal stops paying for the smearing it causes: the error against the slow component is 48.12 units at 9 s against 115.91 at the 30 s the device runs today, a factor of 2.4. | **High** — a sharp minimum, identical at all three splits and on both contacts, and it follows from the model's own time constants rather than from a preference |
| Detection blanking | **54 s** | One ramp plus one slow time constant (27 + 29.3 s), so a decision is not re-examined while the current change it ordered is still working through. | **Low** — the ramp half of it inherits the ramp's own weakness, and nothing in this record measures a blanking duration directly |
| Adaptive startup delay | **87 s** | Three slow time constants, the point at which the model has forgotten its starting state to within 5 %; **the device has only been seen to accept 0, 10 and 30 s on this participant, so if the tablet refuses 87 s, use 30 s and record that the model wanted longer.** | **Low** — a model extrapolation, not a measurement; no documented range exists for this setting |
| Upper threshold | **328.58 device units** | The fitted long-run level (280.46) plus one residual scatter of a 9-second average about the slow component (48.12), so a crossing means the slow component genuinely moved rather than the noise. | **Medium** — it moves 3.38 units across splits, more than the brief's one-unit rule allows, and the centre is an arithmetic average pulled upward by rare very large readings |
| Lower threshold | **232.34 device units** | The same level minus the same scatter; the resulting 96-unit gap puts 24.6 % of held-out readings between the two, against 18.2 % for the stored pair, and turns 69.5 % of the time at the upper limit into a balanced 24.7 % upper / 30.8 % lower. | **Medium** — moves 2.02 units across splits; the balance it produces is the strongest argument for it |

### L 0⁻2⁺ at 24.5 Hz

| Setting | Recommend | Reason, one sentence | Confidence |
|---|---|---|---|
| Onset, upper timer | **63 s** | 63 s is the shortest hold leaving no more than one switch a day undone under the fitted noise (0.72), and over the whole record it gives 2.03 switches an hour with 3 undone in 27 hours against the device's 22.24 an hour with 197 undone. | **Medium** — unmoved across splits, but the held-out slice for this band is 0.6 hours and could not confirm it |
| Onset, lower timer | **63 s** | Same reason; one process, one noise size, no reason for the two timers to differ. | **Medium**, same evidence |
| Ramp up | **18 s** | The optimal controller on this model corrects in 17.0 seconds at the input weight where its current use fits the device's half-span. | **Low** — rests on a current gain of −2.672 ± 1.079, which is steadier than the other contact's but still not established |
| Ramp down | **18 s** | Same calculation, symmetric model. | **Low**, same reason |
| Averaging | **9 s** (3 readings) | Same sharp minimum: error against the slow component 45.12 units at 9 s against 92.07 at 30 s. | **High** — identical at all three splits and on both contacts |
| Detection blanking | **36 s** | One ramp plus one slow time constant (18 + 18.2 s). | **Low** — inherits the ramp's weakness, nothing measures it directly |
| Adaptive startup delay | **54 s** | Three slow time constants; **again beyond the 0, 10 and 30 s this device has been seen to accept on this participant — use 30 s if the tablet refuses, and record that the model wanted longer.** | **Low** — a model extrapolation |
| Upper threshold | **254.17 device units** | The fitted long-run level (209.05) plus the residual scatter of a 9-second average about the slow component (45.12). | **Medium** — it moves under one unit across splits, but on the held-out slice it produced no switch at all, and only the training data and the whole-record replay show it working |
| Lower threshold | **163.92 device units** | The same level minus the same scatter; the stored pair on this contact is 196.13 / 190.89, **5.24 units apart on a signal whose scatter is over 200 units, which is a single threshold in all but name** — only 2.0 % of readings in the whole record sit between them, against 32.5 % for this pair. | **Medium** — same reason; the case against the stored pair is much stronger than the case for this exact pair |

---

## 5. What this method cannot tell from this record

1. **What stimulation does to the band power.** This is the central limit. The information score
   rejects the current term on both contacts, its fitted size halves between two splits on L 1⁻3⁺,
   and its uncertainty covers zero there. The record was collected while the current followed the
   participant's ordinary programming, which barely varies inside a stretch, so there is almost no
   input movement to learn a gain from. **Both ramp durations, and half of each blanking duration,
   therefore rest on a number the record does not establish.** The titration session already written
   up as open item 30 — one rate, 0.5 mA steps, at least 60 s per step, up and down, streaming
   throughout — is what would fix this, and nothing short of it will.
2. **Anything faster than 3 seconds, or slower than about an hour.** The readings arrive every
   3 seconds and the longest stretch is 75 minutes, so the model cannot see the device's own
   1.2-second default onset, and cannot separate a genuine multi-hour drift from the constant term.
3. **The detection blanking duration and the startup delay, directly.** Neither leaves a trace in a
   recording made with adaptive therapy off. My values for both are arithmetic on the model's time
   constants, which is a defensible extrapolation and is not a measurement.
4. **Whether the averaging and the onset are one stage or two on the real device.** The replay
   cascades them — the averaging window becomes the controller's update interval — and section 3.3
   shows that this single modelling choice moves the device's own configuration from about 2.5
   switches an hour to 24.3. I cannot resolve it from the data; the Percept clinician programming
   guide defines the two settings but gives no minimum, maximum or step for either.
5. **Whether a switch helps the patient.** Nothing here uses the pain ratings. The model describes
   the signal, not the symptom, and a configuration that switches sensibly may still do nothing for
   pain. The ratings change over days; the settings here act over seconds.
6. **The right side.** The right sensing channel is ganged to the left, so every number here is a
   left-signal number, and no right-side evidence exists that passed the screen.
7. **The heavy tail.** The largest reading on L 1⁻3⁺ is 32,797 device units against a long-run level
   of 280 — about 120 times. A linear model fitted by least squares treats those as ordinary
   fluctuation, which inflates the shock size from a robust 95.9 to 247.4 on that contact. I used the
   ordinary fit throughout so that the fit and the design are one consistent object, and report the
   robust figure beside it; a reader who prefers the robust scale should expect narrower thresholds
   than the ones recommended above.
8. **Whether 4 s or 30 s is the better ramp.** With averaging at 30 s the replay cannot distinguish
   them at all, and with averaging at 9 s the distinction rests on the unestablished current gain.
   This method has no opinion worth acting on.

---

## 6. The files I wrote

All under `BRAVO/_agent_bridge/_probe_tl/_contest/lti_ss/` (the container path is
`/usr/src/BRAVO/_agent_bridge/_probe_tl/_contest/lti_ss/`). Nothing was written to the production
saved-answers store, no production file was edited, and nothing was committed.

**Scripts**

- `s1_inspect_and_fit.py` — first pass: printed every array in the two data files with its shape and
  first values, built the split, fitted orders 1–4 with and without the current. **Its order
  comparison is superseded**: it scored candidates fitted on different numbers of rows.
- `s2_statespace_lqr_design.py` — the corrected fit on common rows, the state-space form, the
  `ctrlsys` checks (poles, controllability, `tb05ad` frequency response), the `sb02md` optimal
  controller, and the first pass at the mapping.
- `s3_final_design_and_replay.py` — the final mapping, the one-step-ahead prediction score, and the
  first controller replay.
- `s4_scoring_tables.py` — the scoring tables with the sample sizes made explicit: the split in hours
  as well as stretches, the common replay set, each configuration on every test stretch it can
  handle, the whole-record replay, and the robustness table.

**Tables**

- `s1_split.csv`, `s1_arx_fits.csv`, `s1_prediction_scores.csv`, `s1_models.json` — the superseded
  first pass, kept so the correction is traceable.
- `s2_order_selection.csv`, `s2_model.csv`, `s2_averaging_curve.csv`, `s2_onset_false_alarm.csv`,
  `s2_design.csv`, `s2_design_70.json`.
- `s3_design_final.csv`, `s3_controller_score.csv`, `s3_prediction_score.csv`, and
  `s3_onset_<contact>_<split>.csv` (six files, the full onset search from 1 to 30 controller steps).
- `s4_split.csv`, `s4_controller_common_set.csv`, `s4_controller_maximal_test_set.csv`,
  `s4_controller_whole_record.csv`, `s4_robustness.csv`.

**This report**: `artifacts/contest_2026-09-13_lti_ss.md`.
