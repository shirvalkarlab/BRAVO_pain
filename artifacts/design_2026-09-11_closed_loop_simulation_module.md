# Closed-loop simulation module: design, put to the PI before any code

**Written 2026-09-11**, Phase 8 of the Closed-Loop page redesign plan
(`.planning/2026-09-11-closed-loop-page-redesign/`), the item the PI asked to be done last. It is a
design, not a build: CLAUDE.md §10 rule 8 — plan approval is not execution authority. Nothing below
exists in code until he says go.

---

## 1. The question the module answers, and the one it must not pretend to

**Answers:** if this participant's stimulator were switched to Adaptive Therapy on this band with
these thresholds and limits, what would the amplitude do over a day, a week, a month — how often
would it sit pinned at a limit, how often would it switch, how long would a single excursion last —
**taking into account that the amplitude it delivers changes the band power it is watching**.

**Must not pretend to:** predict pain. The chain current → band power → pain has three links and the
module models the first one only. The second (band power → pain) and third (current → pain) are
evidence on the page's triangle and stay there.

**Why the existing replay is not this.** `ClosedLoopDeployment/replay.py` (decision 5's era) runs the
device's control law over a *recorded* power series and says so in every result: it assumes the same
power would have occurred under closed-loop control, which is false whenever the band responds to
amplitude — and a band that does not respond is not a control signal at all (design ledger §2: "if
the biomarker tracks pain state but is stim-unresponsive, the loop can stick on"). The replay tells a
reader what the controller's arithmetic does to a fixed input. The simulation closes the loop: the
controller moves the amplitude, the amplitude moves the power, the controller sees the moved power.

---

## 2. Inputs, every one of which already exists on this branch

| Input | Where it lives today | What the module reads |
|---|---|---|
| The candidate | `BandCandidate` (design ledger §6): hemisphere, contact, centre, width, `threshold_lsb`, `adaptive_valid`, `polarity`, `timeseries_ref` | identity + thresholds |
| The recorded band power in device units, per sample, with the amplitude in force | the joined table `adapter.joined_table_cached` (E1's `T`): `power_linear`, `amp_mA_<side>`, `setting_epoch`, `t` | the baseline power series and its noise |
| How power responds to amplitude, per run | stored `three_source_run_points` (decision 125) | per-run settled points at the centre |
| The pooled response across runs | stored `within_visit_pooled_shape` (decision 103): `pooled_slope_per_mA`, its error, `curves`, `peaks_inside`, `peak_mA`, `p_curvature` | the plant's slope; the bend when established |
| How fast power settles after a step | `percept_adaptive.estimate_response_latency` and the settled window `within_visit.PRE_CHANGE_WINDOW_S` (30 s) | the plant's time constant |
| The device's control law and timing | `percept_adaptive.py` (quoted from UC202012929dEN): Dual/Single modes, `ONSET_RANGE_DUAL_MS`, transition durations, `ADAPTIVE_LFP_BAND_HZ`, amplitude limits from the plan | the controller, unchanged from `replay.dual_threshold` |
| The prescription (thresholds, limits, onset, transitions) | `prescription.prescribe_all_modes` | the programmable parameters, per mode |
| The patient's own rating noise | `reliable_change` (decision 111) | NOT used — pain is out of scope (§1); listed so nobody adds it silently |

Nothing new is measured. Every number the module uses is one the page already shows.

---

## 3. The plant: three models, chosen by the evidence in hand

The "plant" is the part the replay lacks: the rule for what band power does when the amplitude
changes. Three models, from the weakest assumption to the strongest, and the module runs the
strongest one the stored evidence supports — and says which.

**M0 — no response (the replay as it is).** Power follows the recording; amplitude changes nothing.
Kept as the reference, because the difference between M0 and M1 IS the closed-loop effect.

**M1 — straight-line response with settling.** At each controller step the target power is the
recorded power at that moment plus `pooled_slope_per_mA × (amplitude − amplitude in force during the
recording)`, in device units; the delivered power approaches the target with a first-order settling
time τ (default: the settled window, 30 s; overridden by `estimate_response_latency` when a run
supports it). Used when the stored pooled row has a slope and no established bend. This is decision
9's edge, made dynamic.

**M2 — peaked response (decision 11's pivot).** When the pooled model has established a bend
(`curves`, `peaks_inside`, `peak_mA`), the response is the fitted quadratic up to the peak and the
second, post-peak straight line (decision 55's own second fit) beyond it. The module reports the
amplitude range in which the controller operates on the WRONG side of the peak — where raising
amplitude raises power, turning negative feedback positive — and how much time it spends there.
**This is the case the PI expects to need** ("high likelihood we must model or identify the response
peak and model the post-peak descent"). Today no bend is established on RCS08 (findings §6), so M2
would report "not assessable" and the module would run M1; the code path exists so the pivot costs
nothing when the titration of open item 30 lands.

**M3 — run-resampled uncertainty.** Every model above is re-run with the slope (and peak) drawn from
the runs by resampling runs with replacement (the pooled model's own grouping), giving an interval on
every output. Runs, never points: resampling points would pretend six settings on one visit were six
visits.

**What the plant deliberately leaves out, and why:** (a) hysteresis between ramp-up and ramp-down — no
human study has measured it (synthesis §2) and this record has no ramp-downs; (b) artifact and
saturation at high amplitude (synthesis §4) — the amplitude limits the prescription sets keep the
controller inside the range that was characterised; the module refuses limits outside
`plan.capture_amp_low/high` unless the caller says so, as the replay already does; (c) drift of the
baseline between visits — handled by resampling runs (M3), not modelled.

---

## 4. Outputs, and the sentence that travels with each

Per mode (Dual, Single), per plant model run:

- time fractions below / between / above the thresholds, and at the lower / upper amplitude limit;
- the longest single excursion at each limit, in seconds (the replay's own reasoning: a clinician
  consents to a two-hour block differently from a hundred blips);
- number of controller transitions per hour;
- **the closed-loop difference**: each of the above for M1 (or M2) against M0, so a reader sees what
  closing the loop changes, not only where it ends up;
- for M2: time on the wrong side of the peak, and the amplitude at which the sign flips;
- the interval from M3 on every number;
- the caveat, verbatim, on every result: the model of how power responds to amplitude is a straight
  line (or a peaked curve) fitted to N settled points across V runs of rising current on this contact;
  it has not been observed under closed-loop control; the amplitude trajectory is what the control
  law does to this model, not a prediction of what the device would deliver.

Nothing here is a verdict. The module gates nothing; whether any of it should is the PI's call, as it
is for every other informative panel on the page.

---

## 5. Where it goes on the page, and where its answers are stored

- **Closed-Loop Deployment page**, inside the existing dashed card "If the same band power occurred
  under closed-loop control, how would the time divide?" — which becomes "…and what would closing the
  loop change?": the three state bars it shows today (M0) gain a second row (M1/M2) with the
  interval, and a one-line difference. The wrong-side-of-the-peak time appears only when M2 ran.
  Everything else behind the card's existing folds.
- **Stored** as a derived kind `closed_loop_simulation`, one entry per participant, keyed on the
  candidate, the prescription, the plant model version, the pooled-table key and the recording set;
  written with `writer="closed_loop"` and the tile entry in its provenance, refused to
  `stim_optimizer` (the self-derived rule, decision 31 — Stim Optimizer chooses which recordings
  exist, and a simulation built on them must not feed its policy). Read by the page's background
  fetch after the report, the same way the pooled view is (decision 13).
- **Sign-off card**: the M0/M1 state bars, captured like the other figures (decision 113).

---

## 6. Tests the build would carry

1. With a zero slope, M1 reproduces M0 exactly (0 differing fields) — the closed-loop effect is
   exactly the slope.
2. With a negative slope and thresholds inside the recorded range, M1's time at the upper limit is
   less than or equal to M0's (the replay's own docstring predicts this: real feedback retreats sooner).
3. With a positive slope, the controller pins at a limit and stays: the module names the positive-
   feedback case rather than reporting a duty cycle as though it were regulation.
4. M2 with a peak inside the limits reports the wrong-side time > 0 and the flip amplitude equal to
   the peak.
5. Resampling runs, never points: a fixture where one run has six settings and another two gives
   each run equal weight in the interval.
6. A stored entry is refused to `stim_optimizer` (constructed cycle, as `test_provenance_cycle`).
7. Every result carries the caveat and no field named like a verdict (the same guard the
   three-source payload has).

---

## 7. What the PI decides before code

1. **Time constant τ for M1**: the 30 s settled window, the measured response latency where a run
   supports it, or a value he gives? (Default proposed: measured where available, else 30 s.)
2. **Amplitude limits**: hold the module to the capture range as the replay does, or allow the
   prescription's wider limits with the extrapolation flagged? (Proposed: hold, flag on request.)
3. **The wrong-side-of-the-peak report** — a number on the card, or a blocking caveat once a bend is
   established? (Proposed: a number and a warning; blocking is his call, as for `band_stability`.)
4. Whether to run M3 on every page load (11 runs → cheap) or only on demand.
5. Placement: extend the duty-cycle card (proposed) or a new card.

The build is roughly: one module (`simulation.py`, plant models + a wrapper around
`replay.dual_threshold` that feeds the moved power back), one store kind, one adapter block, one
panel edit, seven tests, and the live proof on RCS08 with M0 = replay (0 differing fields) as the
control.

---

## 8. What was built, where it departs from the design above, and why (added 2026-09-11)

The PI answered the five questions of §7 the same day (redesign plan decisions 15-21) and the module
was built. Four things differ from the text above; the text is kept and this section corrects it.

1. **The plant is a response CURVE, not a slope** (`StimOptimizer/routines/amplitude_response.py`).
   `p_sim = p_obs + delta`, with `delta` relaxing toward `g(a_sim) - g(a_obs)`; the per-run baseline
   cancels in that difference, which is what makes M0 (the zero curve) reproduce the replay bit for
   bit. M1 is the straight line, M2 the fitted quadratic with decision 55's post-peak line, one code
   path. The stored pooled table now carries the quadratic's coefficients (v2) so M2 switches on
   without a schema change when a bend is established -- the PI's instruction ("flexible so we can
   later incorporate the bend").
2. **The series is the 3 s voltage-trace pieces, not the joined table §2 names.** The joined table
   holds one spectrum per recording -- chronic snapshots minutes apart -- and the replay refuses it
   (samples 230 s apart cannot resolve a 150 s ramp: the old duty-cycle card's "not answerable at
   this sampling cadence"). The pieces resolve the ramp fifty times over and are the same
   calibrated quantity the thresholds were placed on. Inside a recording they jitter, so each
   stretch is put on the device's own 3 s clock first (`simulation.regrid_stretches`); a cell with
   no piece is a missing estimate the controller holds across.
3. **The stored kind is released to Stim Optimizer, not refused** (§5 was wrong). The refusal fires
   when a product's chain contains the CONSUMER's own output; the simulation, like the pooled table
   it reads, cites its raw roots (the tiles), so nothing of Stim Optimizer's is in it. The control
   test pins the case that IS refused: a chain naming the exploration ladder.
4. **Placement: a new card, "CL-DBS simulations", after the sign-off card**, and the duty-cycle
   card is gone (M0 replicates it) -- the PI's choice over extending that card. Visual-first:
   three figures and one derived headline; the method is folded.

Measured on RCS08 (ONE_THREE_LEFT, 20.5 Hz): see decision 128 in `DECISIONS_and_open_items.md`.
