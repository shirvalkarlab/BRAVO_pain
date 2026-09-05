# 2026-09-05 — the clinic sheets are the finest stimulation record, and the ramp is the artifact

## What changed

`BRAVO/modules/ClosedLoopDeployment/clinic_steps.py` (new) and a docstring amendment to
`Biomarkers/routines/analytics.harmonic_landings_hz`. Eight tests in
`ClosedLoopDeployment/tests/test_clinic_steps.py`. Suite 198 -> 206.

## Why: the chronic settings stream is blind inside a session

6,605 settings rows for RCS08 collapse to 1,189 distinct timestamps and 123 exposure epochs with a
median duration of **27.5 hours**; 75 run over a day, the longest 89 days. Inside them the stream
shows zero amplitude variation — but the epochs are built by detecting changes in that same stream,
so that flatness is circular. A 27-hour epoch can sit on a clinic visit in which amplitude was
stepped thirty times and the export records none of it.

## The sheets, parsed properly

29 testing workbooks in Drive, every one with a Stim Testing tab. **820 timestamped steps** over 29
visit dates (2025-07-30 to 2026-09-02), 624 in clinic and 196 at home, 40 left and 42 right
amplitude levels over 0.0-6.0 mA, ten rates. Five traps are documented in the module docstring; the
two that cost the most were `read_file_content` silently omitting the Stim Testing tab (an early
parse reported 746 steps of unprovable provenance) and July 2025 keeping its step times in the
**Notes** tab as free text (`1.5mA c+2-`), not in Stim Testing at all.

Four rates appear in the sheets that the device export never recorded — 25, 85, 100 and 180 Hz.
UNRESOLVED: delivered-and-missed, or planned-and-not-delivered.

## The exposure window, and why 45 s is not enough at the harmonics

Nominal `Duration (s)` is not what happened: median 60 s nominal against 98 s observed, with the
observed interval SHORTER in 23% of steps and more than twice as long in 24%. Taking
`min(nominal, observed)` minus a 45 s ramp leaves **563 of 820 steps (69%)** with settled time,
loses **every 30 s step (all 169)**, leaves 60 s steps with a median of 15 s, and totals
**16.2 hours / 19,325 tiles**.

**Measured artifact time course.** Aligning 13,102 tiles to step onset across 370 steps: at the
stimulation frequency power tracks amplitude with the right sign (up on increase, −0.26 log10 within
9-18 s on decrease, flat to 0.016 when unchanged) and the rise is a spike confined to the landings —
peak **0.81 log10 per 100 s at 57.5 Hz** against **−0.003** away. It is still climbing at 150 s
(+1.16 log10, 14-fold), and that survives the composition check (same six steps in every bin).
Cause not established. Policy: exclude the affected BANDS per rate, not extend the time window.

**The join was validated, not asserted.** Coverage against a deliberate clock offset: 22.8% of steps
contain a tile at zero shift, 4.8% at +1 h, 3.7% at −1 h, **0.0% at ±7 h** — a test that could fail,
unlike the same check against chronic epochs which returns 1.0000 at every shift.

## The within-visit amplitude result, and its three limits

Step as the unit, amplitude and power de-meaned within visit, clustered on visit, stratified by
channel x rate x source, harmonic bands dropped per rate. Yield is thin: 446 step-level
observations over 20 visits, median 5 tiles each, only 4 strata clearing the minimum.

Inside 7.8-30 Hz away from landings: 54 cells, 20 resolved, **6 resolved NEGATIVE** after removing
degenerate intervals, 12 positive. The negatives include **ONE_THREE_LEFT at 24.5 Hz, beta −0.0527,
CI [−0.0724, −0.0330]** — the direction Dual Threshold requires, and the reverse of what the
between-epoch screen found for the same channel and band. The design difference did it, not new data.

Limits, all bounding rather than decorating: (1) every stratum produced at least one zero-width
interval and 6 of 116 resolved cells have widths under 0.005 log10, the same collapse the inference
lane documented at low cluster counts — the point estimates are the finding, the intervals are not,
and a visit-level wild cluster bootstrap has not been run; (2) every negative cell is at **110 Hz**
while the candidate is programmed at **165 Hz**, which appears in no fitted stratum, so nothing here
licenses the candidate; (3) multiplicity uncorrected and bands overlap 80%, so six cells are nearer
two or three relationships.

## Corrections to my own prose, recorded because both reached the user

- "314 of 631 steps asymmetric" was wrong: an inequality over the raw columns counts NaN != NaN as
  True. Correct figure on the final table is **199 of 673 (29.6%)**.
- "Pooling every rate leaves 1 usable band" was a different statistic quoted as a band count. The
  measured value is **8 of 98** surviving the union of nine rates, against 65 for 55 Hz alone. A
  test now pins it.

---

## Later the same day — the bootstrap wipes out the within-visit result

Re-running the within-visit slopes through `edges._small_sample_inference` (the wild cluster
bootstrap-t already in the module, Rademacher weights enumerated at or below 12 clusters) leaves
**zero resolved cells out of 88** — none negative, none positive. The p-value floors explain it:
5 visits gives 0.0625, 6 gives 0.0312, 7 gives 0.0156, 12 gives 0.00049, and 66 of the 88 intervals
come back unbounded. Only the ZERO_THREE_RIGHT 55 Hz stratum (12 visits) had the cluster count to
reject anything, and it rejected nothing.

**So the six "resolved negative" cells reported earlier were the CR0 variance collapse, not a
finding.** The within-visit design does not resolve the amplitude-power sign in either direction.
D19 is unchanged, and the honest statement is that no design available on this record resolves it.

## The 55 Hz correction

Cross-thread handoff records the PI's decision that the deployment rate is **55 Hz**. Every negative
cell in the earlier CR0 table was at 110 Hz, so it described a configuration that will not be
programmed. At 55 Hz the harmonics fold to 25, 30, 55, 60, 80 and 85 Hz, and the 24.5 Hz candidate
band spans 22.0-27.0 Hz — **it contains the 25 Hz landing and cannot be assessed for amplitude
response at all**. The usable window at 55 Hz is 8.5-21.5 Hz, which intersects the capturable range
(8.8-11.7 Hz, the only bins clearing the 1.2 uVp floor) at roughly 8.5-11.5 Hz.

## No time limiter exists in closed loop

Cycling is not available with Adaptive Therapy (A610 p. 35, D32) and no duration or dwell limit
appears in the corpus. `DutyCycle.max_time_at_upper_limit_s` now reports the longest continuous
excursion instead, and fixing its plumbing exposed a `ValueError` crash in `duty_cycle` that had
been reading the control-state list as an amplitude array.

## The three-week burn-in exclusion on the validation mixed model

`analytics.VALIDATION_EXCLUDE_FIRST_WEEKS = 3`, applied in `band_mixedmodel_inference` only, before
binarization and before the z-score, anchored on the first sample of the whole record.

Measured effect on RCS08: **none, today.** 22 samples fall in weeks 0-2 with finite band power and
none carries a finite tertile label, so all 36 channel-by-band cells scanned fit identically either
way. Reported in the payload as `n_excluded_burn_in` / `n_weeks_before_exclusion` rather than
silently, because a reader comparing this odds ratio to the sweep must see which window it used.

Frontend follow-up: the panel does not yet state the exclusion. The keys are in the payload.

## The response test now blocks on the 5 most recent eras

`lfp_evidence.RECENT_ERAS_FOR_RESPONSE = 5`, `recent_eras=` on `build_evidence` / `build_all` /
`live_evidence`. Ordered by each era's latest timestamp, not by label. Audit carries
`n_dropped_old_eras`, `recent_eras_kept`, `recent_eras_requested`, `era_order_source`.

Slope unchanged (-0.1222 at 8, 5 and 4 eras) because the dropped eras had one amplitude each and
contribute nothing within-era. Capture direction flips False -> True on 15 of 18 bands because the
low arm moves 1.6 -> 3.5 mA. Separation becomes the binding constraint at 0.41-0.52 vs a 0.5 floor.
Verdict unchanged: 0 of 12 deployable at 55 Hz.

Open: separation is now doing the refusing, and it is doing so at a threshold the 1 mA contrast makes
almost unreachable. Whether MIN_CAPTURE_SEPARATION_D = 0.5 is the right floor for a 1 mA capture is a
question I have not put to the PI.
