# Code review, 2026-09-12: the Stim Optimizer module

**Scope.** `BRAVO/modules/StimOptimizer/` at commit `8882c92c` (the speed-up landed today), read in
full: `bravo_service.py`, `adapter.py`, `pipeline.py`, `stage1_openloop.py`, `stage2_closedloop.py`,
and under `routines/` `acquisition.py`, `adaptive_envelope.py`, `lfp_evidence.py`, `lfp_response.py`,
`objective.py`, `percept_adaptive.py`, `stage_gate.py`, `surrogate.py`, `within_visit.py`, and the
parts of `plots.py` that fit models (`build_context`, the forward simulation) rather than draw. The
page that shows the module's answers (`Client/src/views/Reports/StimOptimizer/*.js`) was read to say
where each finding is visible. Read-only: nothing was edited, no suite was run, the container was not
used. Every number below that comes from real data was read on this Mac from a scratch copy of the
store (`BRAVO/_agent_bridge/_probe_tl/_so_store/`, written 2026-09-12 11:38, RCS08's matched
therapy-and-pain table, 92 rows) with the module's own code in the `bravo_app` environment; each such
check is named where it is used.

**Words used below.** "Epoch": one stretch of time during which every stimulation setting the patient
could feel was held fixed. "Matched table": the epochs with the pain reports averaged onto them, the
table the optimizer fits (`therapy_pain_matched` in the store). "Stratum": one group of epochs that
share a pulse width, fitted as its own surface by the two-stage search's first stage. "Setting in
force": the rate, pulse width and current the device is programmed to now. "The gate": the four
checks that decide whether closed loop may start (`routines/stage_gate.py`). "The readiness screen":
the check of every sensing contact, side and rate for a band whose power moves with current
(`lfp_evidence.screen_cells`), shown on the page as "Does any sensed band respond to current".

---

## Summary

- **Critical 0 · High 3 · Medium 5 · Low 6.** Of the four known hazards, all four are CONFIRMED.
- **The most important finding:** the two-stage search's first stage groups the RIGHT side's epochs
  by the LEFT side's pulse width (`stage1_openloop.py:644`, `pw_col="pw_us_Left"` for both sides),
  and on RCS08's own matched table that turns the Right recommendation from "55 Hz, 160 µs, 4.30 mA,
  pulse width resolved" into "55 Hz, 100 µs, 4.90 mA" — a pulse width the Right side is not at and
  a stratum built from the wrong column (S1, live numbers below).
- Fixing S1 alone exposes S2: when the pulse width in force has too few epochs to fit, the "pulse
  width contrast" silently becomes best-stratum-versus-second-best and is reported as RESOLVED,
  which is one of the two halves the gate's resolution check needs.
- The gate's "a sensed band responds to current" check never looks at which side the evidence came
  from, so one side's sensing contact can license closed loop on both sides (S3); masked today only
  because the resolution check refuses first.
- Everything in the store path (writer and chain on every write, refused-entry replacement, the
  served response, the code digest in the key) and the speed-up code (thread cap restored, shared
  inputs with a real fallback, cached design matrix, integer epoch lookup) checked out; see the
  closing list.

---

## S1 — HIGH, CONFIRMED. Stage 1 stratifies and labels the Right side by the Left side's pulse width

**Where it lives.** `stage1_openloop.py:644` (the default), `:708` (`inc_pw = float(inc_row[pw_col])`),
`:746-768` (`groups = [(float(pw), sub) for pw, sub in fit.groupby(fit[pw_col].astype(float))]`, run
once per hemisphere with the SAME `pw_col`), `:757-761` (the design audit and regression on the same
column), `:1121` (`ENV.brainsense_pair_demonstrated(chosen_rate, pw_us, hemi)`). Nothing on the live
path overrides the default: `pipeline.run_two_stage` (`pipeline.py:477-482`) passes no `pw_col` and
`bravo_service.two_stage_block` (`bravo_service.py:820-830`) passes no `stage1_kwargs`.

**What it does today.** For `hemi="Right"` the epochs are split into strata by the value of
`pw_us_Left`, the incumbent pulse width reported for the Right is the Left's, and the "has this
rate and pulse width been accepted in a BrainSense group on the Right" note is asked about the
Left's pulse width. The docstring at `:665-668` still says "This record carries `pw_us_Left` only,
so the right hemisphere's pulse width is NOT OBSERVED", which stopped being true when
`adapter.exposure_epochs` began emitting `pw_us_Right` (`adapter.py:346-348`).

**What is wrong, with the numbers.** On the scratch copy of RCS08's matched table (92 epochs):
`pw_us_Right` differs from `pw_us_Left` on **67 of 92** epochs; the Right side has run 7 distinct
pulse widths (60, 80, 100, 140, 150, 160, 180 µs) against the Left's 5; the newest epoch (123,
2026-09-03) reads Left 100 µs / 3.0 mA, **Right 150 µs / 2.5 mA**. Running `run_stage1` for the Right
side alone on that table, everything else at defaults:

| `pw_col` | Right frozen setting | strata fitted (pw µs: epochs) | pw resolved | incumbent pw reported |
|---|---|---|---|---|
| `pw_us_Left` (today) | 55 Hz, **100 µs**, 4.90 mA, 15 epochs | 60: 22, 100: 15, 140: 22 | False | 100 |
| `pw_us_Right` (its own) | 55 Hz, **160 µs**, 4.30 mA, 31 epochs | 160: 31, 180: 21 | True (see S2) | 150 |

So today's page recommends a Right pulse width the Right side has been at on exactly 1 of 92 epochs
(`epochs_per_pw` under its own column: 100 µs → 1), fitted on strata that mix Right pulse widths of
60 through 180 µs. The design document of this morning
(`artifacts/design_2026-09-12_stim_optimizer_page_redesign.md` §2) found the symptom ("100 µs on
the Left and 150 µs on the Right") and marked the −50 µs on the page; this is the cause.

**Where it is visible.** Stim Optimizer page: the decision strip at the top ("search prefers" for
the Right row, `DecisionStrip.js:72-76`, which also matches the strip's stratum row by that wrong
pulse width), the "Two-stage plan" card (frozen configuration, strata table, the BrainSense-pair
note), and the "What adaptive mode ruled out" chart (`ExcludedSettingsChart.js:47-54`, points
tagged with the wrong `pw`). The stored `stim_optimizer_response` carries the same block.

**Fix.** In `run_stage1` (`stage1_openloop.py:643-652`) change the `pw_col` parameter to accept
`None` meaning "each side's own column", and at the top of the per-hemisphere loop (`:727`) resolve
`pw_col_h = pw_col if pw_col is not None else f"pw_us_{hemi}"`, falling back to `pw_us_Left` only
when `f"pw_us_{hemi}"` is absent and saying so in `h_audit["pw_col"]`. Use `pw_col_h` at `:708`
(compute `inc_pw` per hemisphere, inside the loop), `:746`, `:757`, `:759`, `:766`, and pass it to
`_freeze_hemisphere` as `inc_pw`. Make `FrozenConfiguration.incumbent_pw_us` (`:201`) per side or
document it as the Left's (the page already reads `in_force_by_side` for the truth). Make the
default `pw_col=None` and correct the docstring at `:665-668`. Do S2 in the same change.
**This changes the Right recommendation on RCS08 (160 µs for 100 µs) and is a scientific change; the
design document names it as the PI's decision. Put the table above to him before building.**

**Test to add** (`tests/test_stage1.py`): build the `_matrix` fixture with `pw_us_Right` set to a
different constant from `pw_us_Left` (150 against 100) and assert `res.frozen.setting("Right").pw_us
== 150.0`, that the Right strata keys are `{("Right", 150.0)}`, and that
`res.frozen.audit["per_hemisphere"]["Right"]["pw_col"] == "pw_us_Right"`; a second case with
`pw_us_Right` absent asserts the fallback is used and named.

**Live check.** Through the bridge, `run_stage1` on RCS08's matched table before and after, both
sides: the Left side's settings, strata and reasons must be identical field for field (0 differing);
the Right side's must show the table above (frozen pw 160.0, 31 epochs on that stratum). Then the
page response with `TwoStage: true`: count the fields, and confirm every difference sits under
`two_stage.stage1` for the Right side and under `two_stage.gate` / `two_stage.stage2` only as a
consequence.

## S2 — HIGH, CONFIRMED. When the pulse width in force has no fittable stratum, the "pulse-width contrast" compares two other strata and reports it as resolved

**Where it lives.** `stage1_openloop.py:1008-1011`:
```
ref = [s for s in hslices if inc_pw is not None and abs(s.pw_us - inc_pw) < 1e-9]
alt = ref[0] if ref else min((s for s in hslices if s is not best), key=lambda s: s.mu_star)
```
and `:1031-1045`, which then computes `pw_resolved` from `best` against `alt` and writes "the
pulse-width move {alt} -> {best} us IS resolved".

**What is wrong.** The rate half of the same function refuses to compare against an extrapolated
incumbent (`Stage1Slice.resolves_its_optimum`, `:530-531`, returns `None` when the stratum never
delivered the rate in force, with a 30-line explanation of why). The pulse-width half has no such
guard: when the stratum at the pulse width in force is below the 8-epoch floor and therefore
skipped, `ref` is empty and `alt` becomes the best of the OTHER strata, so the contrast never
involves the setting in force at all, yet `pw_resolved=True` feeds `HemisphereSetting.resolved`
(`:176`) and from there the gate's `openloop_choice_resolved` (`stage_gate.py:388-395`).

**Shown on the live table.** With the Right side on its own column (S1's fix), the Right's pulse
width in force is 150 µs with 4 epochs, below the floor; the reasons read "the pulse-width move
**180 -> 160 us IS resolved** at the chosen cell (55 Hz, 4.30 mA): posterior gain +1.4668 NRS points
against difference SD 1.3148" and, two lines later, "reference pulse width 150 us is not among the
fitted levels ['160', '180']" — the module states the contradiction in its own output.
`pw_resolved` is True. Today (Left column for both sides) it happens not to fire because the Left's
100 µs stratum has 15 epochs; it fires the moment S1 is fixed, or on any future epoch whose pulse
width in force is new.

**Where it is visible.** Stim Optimizer page, decision strip verdict symbol for that side and the
gate's second check ("Rate and pulse width resolved against their own uncertainty").

**Fix.** At `:1009`, when `ref` is empty and `inc_pw is not None`, set `pw_resolved = None`,
`detail["pw_reference_us"] = None`, and append a reason of the same shape as the rate half's:
"the pulse-width choice is NOT ASSESSED, not refused: the pulse width in force ({inc_pw} us) has
{n} epochs, below the {floor}-epoch stratum floor, so no surface exists to compare the chosen
{best.pw_us} us against; a contrast between two other strata would not be a comparison with the
setting in force". Keep the best-of-others comparison only as a reported number, never as the
verdict. **Test** (`tests/test_stage1.py`): a matrix whose incumbent epoch's pulse width appears on
fewer than 8 epochs and two other levels on 20 each; assert `pw_resolved is None`, the reason names
the count, and `frozen.resolved is False`. **Live check:** after S1 and S2 together, the Right side
on RCS08 must read `pw_resolved=None` and the gate's resolution check must still refuse; the Left
side unchanged, 0 fields differing.

## S3 — HIGH, CONFIRMED. The gate's band-response check ignores which side the evidence came from

**Where it lives.** `stage_gate.py:575-694` (`check_adaptive_band`): it reads `lfp.power_for`,
`lfp.amplitude_mA`, `lfp.era`, `lfp.cluster`, `lfp.mode_requires` and never `lfp.hemisphere`
(`:239-283`, the field exists on the evidence object). `evaluate_gate` (`:763-818`) evaluates the
check once for the whole frozen configuration, which carries a setting per side (`:197`).

**What is wrong.** Closed loop is configured per side: each side senses on its own contact and moves
its own current. Evidence that band power on the LEFT sensing contact falls as the LEFT current
rises says nothing about the Right side, yet a single passing cell makes the condition True for a
configuration that freezes both sides. Checked by construction: the `_matrix()` fixture of
`tests/test_two_stage_wiring.py` through `run_stage1` for both sides, then `check_adaptive_band`
with `_responding_lfp()` tagged `hemisphere="Left"` → `passed=True`, and neither the evidence block
nor the sentence names a side. On the live path (`pipeline.run_two_stage_live`,
`_select_after_freezing`, `pipeline.py:666-668`) the cell handed to the gate is the screened best at
the frozen rate across BOTH sides, so it is whichever side happened to screen best.

**Masked today.** On RCS08 the gate refuses on the resolution check (decision 138), so
`can_deploy_closed_loop` is False regardless. The defect matters the day the resolution check
passes or is overridden: "Stage 2 MAY START" would then be printed for both sides on one side's
evidence.

**Where it is visible.** Stim Optimizer page, the four-check strip ("A sensed band inside 8–30 Hz
responds to stimulation current") and the "n of 18 bands respond" line with the band strip beneath it.

**Fix.** `check_adaptive_band` should take the evidence per side: accept `lfp` as either one
`LfpEvidence` or a mapping `{hemisphere: LfpEvidence}`, evaluate the response per frozen hemisphere,
report `evidence["per_hemisphere"]`, pass only when every frozen side has a passing band, and mark a
side with no evidence NOT ASSESSED (which blocks, as `lfp=None` does today at `:635-644`). In
`run_two_stage_live._select_after_freezing` (`pipeline.py:624-672`) select one cell per frozen
hemisphere (`live_evidence(..., hemisphere=h, rate_hz=pin)` per side, or the screened best among that
side's cells) and record both in `manifest["lfp_evidence"]`. **Test** (`tests/test_stage_gate.py`):
a two-side frozen configuration with a responding Left evidence and no Right evidence asserts
`passed is None` (not True) and the detail names the Right side; with both sides responding, True.
**Live check:** the RCS08 response's `two_stage.gate.conditions[2]` must gain a `per_hemisphere`
block; the count of passing bands on the Left must equal today's 12 of 18 (decision 138) and the
Right side's must be reported on its own.

## S4 — MEDIUM, CONFIRMED. Two different rules for "this band responds", and the page draws the weaker one

**Where it lives.** The readiness screen (`lfp_evidence.py:1231-1291`) calls a cell deployable only
when a MAJORITY of its 18 bands respond (`:1252`) AND a majority carry a significant NEGATIVE
era-blocked slope (`:1268-1278`), with a long comment on why one band of eighteen overlapping bands
is "the maximum of a correlated family". The gate's check (`stage_gate.py:646-668`) recomputes
`assess_response` on the same cell and passes on **any one** band whose captures point the right way
and are separated by at least 0.5 (`if passing:` at `:665`), without the era-blocked-slope rule at
all. The page's band strip (`ClosedLoopChecks.js:134-145`, `BandResponseStrip.js:72`) draws the
gate's `verdict_rows`, i.e. the weaker rule.

**What is wrong.** The two are consistent only because the cell reaches the gate after passing the
screen; the gate's own number ("12 of 18 bands respond") and the tick per band are then computed by a
rule that would also pass a cell the screen refused. A reader comparing the strip with the readiness
table ("n_responding" per cell, `SensingEvidenceTable.js:68`) can see different counts for the same
cell. It is also the third time the same 18 regressions run in one request (screen over all rates,
screen at the pinned rate, then the gate).

**Fix.** Have `check_adaptive_band` accept the screen's verdict for the selected cell (the
`screen` row `live_evidence` already carries: `n_responding`, `n_era_negative_significant`,
`deployable`, `blocking_reasons`) and report THAT as the condition's numbers, keeping
`verdict_rows` for the strip but adding the era-blocked slope sign and p to each row so the strip can
draw both. Or, minimally, apply `MIN_RESPONDING_BAND_FRACTION` and the negative-slope majority inside
the gate as well, from one shared function in `lfp_evidence.py`. **Test:** a constructed cell where
3 of 18 bands respond by direction and separation and none has a negative era-blocked slope must
fail the gate exactly as it fails the screen. **Live check:** on RCS08 the gate's `n_passing` must
equal the screen's `n_responding` for the selected cell.

## S5 — MEDIUM, CONFIRMED. The stopping rule is handed a one-item history, so it can never stop and its "binding" label is wrong (known hazard a)

**Where it lives.** `pipeline.py:268-269`: `ACQ.check_stopping([m["mu_star"]], ctx.mu, ctx.sd,
ctx.n_reports, incumbent_mu=m["incumbent_mu"])`; the same at `stage1_openloop.py:584-585`. In
`acquisition.py:289-293` the plateau needs `n >= k + 1 = 4` items and the ceiling `n >= 8`
(`:298`).

**What it does, checked by running it:** with `[0.1]` and an empty queue → `stop=False,
binding="plateau", plateau_met=False, coverage_met=True, n_batches=1`; with a non-empty queue →
`binding="coverage"`. So `stop`, `plateau_met` and `truncated` are constants, and when the queue is
empty the label says the plateau condition is the one not met, when it was never assessable.

**Where it is visible.** On no page. `stop` and `stop_binding` are in `rep.summary`
(`pipeline.py:293`), which goes into the response as `summary` and into the store as
`stim_optimizer_summary`; `Client/src/views/Reports/StimOptimizer/*.js` reads neither.

**Fix.** There is no batch history in this platform (batches are proposed, never run in sequence),
so the honest value is "not assessable". Either drop `stop`/`stop_binding` from the summary row and
keep only `queue_size` and `coverage_met`, or pass `best_history=[]` and make `check_stopping`
return `binding="not assessable: no batch history"` when `n == 0`, with `plateau_met=None`. Add a
test asserting that value for `n == 0`. No live equality proof is needed beyond the summary rows
changing in exactly those two columns.

## S6 — MEDIUM, PLAUSIBLE (PI decision). The flat optimizer's queue and batches are not held to the adaptive envelope, so "What to test at the next visit" can list 10–40 Hz cells

**Where it lives.** `plots.build_context` (`plots.py:55`, `FREQ_GRID = [10, 20, 30, 40, 55, ...]`),
`acquisition.exploration_queue` and `select_batch_within_visit`, `pipeline._queue_frame`
(`pipeline.py:145-200`, columns `within_hard_limit`, `inside_delivered_envelope`,
`schedulable_without_new_clinical_signoff`, no adaptive-capable column). Decision 138 applied the
55 Hz envelope to Stage 1 only (`stage1_openloop.py:570-583`).

**What is wrong.** The queue is the module's list of settings to test next and is written back as
`exploration_ladder` ("Stim Optimizer decides which settings need exploring", CLAUDE.md §10 rule 6).
A 40 Hz cell can sit at rank 1 with a tick under "eligible" (`index.js:615-641`), while two cards
down the two-stage plan says 40 Hz was ruled out. Whether testing below 55 Hz open loop is wanted is
the PI's call; nothing on the row says the cell is one closed loop cannot use.

**Fix (minimal, no scientific change).** In `_queue_frame` add
`adaptive_capable = freq_hz >= ENV.MIN_RATE_HZ` (from `routines/adaptive_envelope.py`) and show it
in the queue table as a column; optionally, at the PI's direction, pass `allowed = safe & grid_mask`
into `exploration_queue` and `select_batch_within_visit` in `build_context` as `_fit_slice` already
does. **Live check:** the queue on RCS08 before and after differs only by the new column (field
count up by 25 per arm, 0 existing values changed).

## S7 — MEDIUM, PLAUSIBLE. "Setting in force" means the newest epoch that has a pain report, not the newest device setting

**Where it lives.** `bravo_service.in_force_by_side` (`bravo_service.py:528-530`,
`row = es.sort_values("t0").iloc[-1]`), `plots.build_context` (`plots.py:209`,
`incumbent_epoch = float(es.sort_values("t0")["epoch"].iloc[-1])`), `stage1_openloop.run_stage1`
(`:698`, the same). `es` is the matched table, which keeps only epochs with at least one usable
report (`adapter.attach_pros`, `adapter.py:429`, `how="inner"`).

**What is wrong.** After a reprogramming, until the first rating filed more than one minute later,
the newest epoch in `es` is the PREVIOUS setting, so "programmed now" on the decision strip, the
incumbent every arm's gain is measured against, and the two-stage incumbent all name a setting the
device is no longer on. The Closed-Loop page reads the newest epoch of the settings stream itself
(decisions 132, 135), so the two pages disagree in that window. On the scratch table today the
newest rated epoch (123, 2026-09-03 20:07 UTC, 55 Hz) is also the epoch the Closed-Loop page names,
so nothing is wrong on screen now.

**Fix.** Build `in_force_by_side` from the full epoch table the request already holds
(`_ev_inputs[1]`, or `adapter.exposure_epochs(_stream)`) and add `has_ratings_yet` to each side;
leave the fitted incumbent as it is (a surface cannot be referenced to an epoch with no rating) but
say on the block when the two differ. **Live check:** through the bridge compare
`exposure_epochs(stream)["epoch"].max()` with `es["epoch"].max()` for RCS08; today they must be
equal (123); the test constructs a stream with one unrated newest epoch and asserts the block names
it with `has_ratings_yet=False`.

## S8 — MEDIUM, PLAUSIBLE. The safety model's "limit" anchors are a hard-coded 2026-08 snapshot for one participant, and some of those limits are the adaptive current limits, not a clinician's ceiling

**Where it lives.** `plots.py:77-79`, `LIMIT_ANCHORS = [[55, 2.0], [55, 1.8], [55, 1.9], [10, 1.9],
[110, 4.0], [110, 3.2], [130, 3.2], [125, 2.5], [165, 2.5], [110, 2.2], [55, 1.6], [10, 2.0]]`,
"Programmed UpperLimitInMilliAmps anchors from the device JSONs"; used by `build_context`
(`:240-243`) and `run_stage1` (`stage1_openloop.py:740-744`) as severity-3 seeds of the safety
model, whose safe set decides the reachable ceiling, the queue's `safe` column, the batches and the
in-envelope optimum. The settings stream already carries each row's `UpperLimitInMilliAmps` as
`upper` (`adapter.py:151`, `:161`), and **nothing reads that column** (grep of `modules/` and
`Server/`: zero readers).

**What is wrong.** Decision 136 (2026-09-12) established that on a sensing channel with adaptive
therapy RUNNING, `UpperLimitInMilliAmps` is the adaptive amplitude limit (GROUP_D: 2.0–3.0 mA at
55 Hz), not a patient limit. Five of the twelve anchors sit at 55 Hz between 1.6 and 2.0 mA, which is
that range; if they are adaptive limits, the safety model has been told "severity 3 at 55 Hz,
2.0 mA" while the same record shows 4.8 mA tolerated at 55 Hz for weeks. The two-anchor seed's
large variances soften this (today the Right's preferred current is 4.3–4.9 mA at 55 Hz, so the
safe set clearly extends past 2 mA), but the input is wrong in kind, is a per-participant constant
in a module called for any participant, and is invisible on the page ("the two-anchor safety
seed ... has no prospective side-effect data" is the only sentence about it).

**Fix.** Replace the constant with anchors built from the stream: rows of `schema == "hemisphere"`
(legacy program limits) keep their `upper`; rows of `schema == "sensing"` are excluded when the
group's adaptive therapy is running (decision 136's rule lives in
`ClosedLoopDeployment/session_report_facts.py`; import it with the double spelling, do not retype
it). Report the anchor count and source in `meta`. **Check first, before building:** through the
bridge, list `stream[["t","hemi","rate","upper","schema"]].drop_duplicates()` for RCS08 and compare
against the twelve anchors — say how many of the twelve match a sensing-schema row. **Live proof:**
safe-set size per arm and `safe_contiguous_ceiling` before and after, per arm, stated as numbers.

## S9 — LOW, PLAUSIBLE. An epoch opens on the Left rate only

**Where it lives.** `adapter.py:339-345`: `freq_hz = rate_Left.fillna(rate_Right)`; `_EPOCH_KEYS`
(`:114-115`) carries `freq_hz` and not `rate_Right`. Comment: "the device runs both sides at the same
rate." In the sensing schema the rate is read per channel (`:160`), so the record can carry two.

**What is wrong if the two ever differ.** A change of the Right rate alone would not open a new
epoch, and every Right-side surface (`amp_mA_Right` against `freq_hz`) would be fitted at the Left's
rate. Decision 124 says "the right side mixes three stimulation rates (55, 110, 145 Hz)".

**Check (bridge, read-only):** on RCS08's stream, count timestamps where the Left and Right rows
carry different `rate`. If zero, add that as an assertion in the stream's own audit and close this;
if not, add `rate_Right` to `_EPOCH_KEYS` and carry `rate_hz_Left`/`rate_hz_Right` on the epochs,
bumping `_THERAPY_SETTINGS_RULE_VERSION`.

## S10 — LOW, CONFIRMED. An incumbent epoch with no rating for the chosen pain item makes every epoch infeasible, and the arm is skipped for the wrong stated reason

**Where it lives.** `objective.build_objective` (`objective.py:342-344`, `ref = d.loc[epoch ==
incumbent, item].iloc[0]; J_pain = item - ref`), then `feasible = isfinite(J)` (`:361`);
`plots.build_context` (`:227-229`) then raises "only 0 feasible epochs ... too few to fit a surface",
which `pipeline.run` records as the arm's skip reason and `_blockers` prints.

**Numbers.** On the scratch table `left_leg_vas` and `back_vas` are present on 75 of 92 epochs; the
newest epoch has both, so no arm is skipped today. Any future newest epoch rated only on the overall
score would skip all four arms with a reason that says the record has no feasible epochs.

**Fix.** In `build_objective`, if `ref` is not finite raise `ValueError(f"the incumbent epoch
{incumbent_epoch} carries no {item} rating, so J cannot be referenced to it")`; `pipeline.run`
already records the message. Test: a matrix whose last epoch has NaN for the item asserts that
message in `manifest["skipped"]`.

## S11 — LOW, CONFIRMED. Three things the response key does not name

**Where it lives.** `bravo_service._response_signature` (`bravo_service.py:335-348`).

1. `TwoStageOverrideBy` and `TwoStageExploreOutsideAdaptiveBy` (the names) are not in the key; the
   reasons are. A second request with the same reason and a different name is served the first
   name (`two_stage.stage1.frozen_configuration.override.by`).
2. The band centres the evidence carries come from Biomarkers constants
   (`adapter._deployable_band_span`, `LSB_VALIDATED_HZ_LO`/`LSB_DEPLOYABLE_HZ_HI`); the code digest
   covers this module only (`_code_digest`, `:140-158`), and the tile key covers the tile rule, not
   those two constants.
3. `_products_signature` (`:351-359`) keeps `bool(rd.get("ClosedLoop"))` in the four tables' key
   although the tables do not depend on it, so two requests differing only in that flag sweep each
   other's tables — the docstring's own reason for dropping the tail.

**Fix.** Add the two names to the key tail (raise `_RESPONSE_ONLY_KEY_TAIL` to 6); move
`ClosedLoop` into the tail; put the two Biomarkers constants into the key as values. Test:
`test_service_store.py` gains a case per item asserting a different key.

## S12 — LOW, CONFIRMED (import spelling). Three single-spelling imports in `adapter.py`, one of which silently widens the evidence

`adapter.py:491` (`from modules.Biomarkers.routines import analytics`), `:539` and `:618`
(`from modules.Biomarkers import bravo_service`). Every other cross-module import in this module is
spelled twice. In the container all three resolve; under the host runner `:491` falls into
`except Exception: return None`, which `evidence_inputs` (`:557-562`) reads as "carry every centre
the cache holds" — 98 centres instead of 22, a different frame with no message. Fix: the double
spelling at all three sites, and make `_deployable_band_span` raise rather than return `None` when
the constants cannot be read.

## S13 — LOW, CONFIRMED (duplicated definitions). The 8–30 Hz range and the 18-band list are defined more than once

- `lfp_evidence.py:1065`: `GATE.ADAPTIVE_BAND_HZ if hasattr(GATE, "ADAPTIVE_BAND_HZ") else (8.0,
  30.0)` — `stage_gate.py` defines no `ADAPTIVE_BAND_HZ` (grep: only this reference exists), so the
  literal is what runs; `percept_adaptive.ADAPTIVE_LFP_BAND_HZ` (`:377`) is the definition the rest
  of the module reads.
- `bravo_service.closed_loop_readiness` (`:1200`) builds the 18 bands by hand
  (`arange(lo + 2.5, hi - 2.5 + 0.01, 1.0)`, width 5.0) while `build_evidence` derives the same list
  from the cache's own centres and half width (`lfp_evidence.py:1075-1082`); a change of the cache's
  band width breaks the readiness panel with "a band 5 Hz wide was asked for" while the two-stage
  path keeps working.
- The 55 Hz floor is one definition inside this module (`percept_adaptive.py:396`, read by
  `adaptive_envelope.py:53` and `stage_gate.py:346`); see hazard (b) for the Closed-Loop side.

Fix: read `PA.ADAPTIVE_LFP_BAND_HZ` at `lfp_evidence.py:1065`; pass `bands=None` from
`closed_loop_readiness` and let `build_evidence` derive them.

## S14 — LOW, CONFIRMED (dead code; the PI's call, CLAUDE.md §2 principle 4)

Zero production callers, confirmed by grep over `modules/` and `Server/` excluding tests and the
scratch area: `routines/schedule.py` and `routines/session_analysis.py` (their tests were deleted
under decision 137; that decision says the production functions are "NOT deleted", so this is
recorded, not proposed); `routines/safety_ordinal.py` and `routines/surrogate_torch.py` (kept by
decision 137 with their 40 PyTorch tests); `lfp_response.device_band_power`,
`span_needed_for_separation`, `expected_separation_d`, `within_arm_sd_from_result`;
`acquisition.lower_confidence_bound`, `select_batch_between_visit`;
`percept_adaptive.validate_policy` and `derive_single_threshold` (reached only from the unreached
Stage 2 and tests); `within_visit.ramp_windows_from_amplitude` and `band_cluster_permutation`. One
cost of keeping them is concrete: `_code_digest` (`bravo_service.py:151-152`) hashes every file
under `routines/`, so an edit to any of these invalidates every stored Stim Optimizer response.

---

## The four known hazards

**(a) `pipeline.py:268` hands `check_stopping` a one-item history — CONFIRMED.** Also
`stage1_openloop.py:584`. Run today: `stop=False` in every case, `binding` "plateau" or "coverage"
only, `truncated=False`. Fix and test in S5. On no page.

**(b) Two rate floors — CONFIRMED at HEAD, fix in progress on the other side.** In this module the
55 Hz floor has one definition (`percept_adaptive.py:396`) read by the envelope and the gate. At
`HEAD`, `ClosedLoopDeployment/device_facts.py` does not import it and `constraints.py:128` carries
the published 30 Hz advisory (D44) while D31's `brainsense_min_rate_hz` is "usually None"
(`constraints.py:396`). The Closed-Loop builder's uncommitted `device_facts.py` (review C3) imports
`MIN_ADAPTIVE_RATE_HZ` from here with the double spelling; that is the right fix and nothing in this
module needs to change for it. Verify after it lands: the Closed-Loop ledger's D31 row on a 40 Hz
candidate must name 55 Hz.

**(c) Stage 1 reads `pw_us_Left` for both sides — CONFIRMED with live numbers.** S1 and S2.

**(d) The ramp clip has no production caller — CONFIRMED.** `within_visit.ramp_windows_from_amplitude`
(`within_visit.py:122`): zero callers outside tests. `mean_power_before_next_change`'s `ramp_end_t`
(`:1027`, the clip at `:1143-1146`) is passed by nobody: the one live caller,
`ClosedLoopDeployment/three_source_response.py:844-847`, passes `block`, `step_end_t`, `window_s`,
`min_chunks` only. The code's own comment (`:1136-1141`) says without the clip "the window silently
reaches back into the stretch where the current was still moving on any setting held for less than
window_s -- 188 of 600 plateaus across RCS08's record". The fix is the caller's (the Closed-Loop
module, out of this review's scope): compute `ramp_end_t` per step with
`ramp_windows_from_amplitude` from the device's own current trace and pass it; the live check is the
count of steps whose window start moved and the field-count/difference-count of the three-source
panel before and after. Where it is visible: the Closed-Loop Deployment page, "Stimulation amplitude
effects on band power, measured three ways", time-domain column.

---

## Checked and NOT flagged

- **Every store write carries `writer=` and `provenance=`**: `adapter.py:227-231` (`therapy_settings`,
  raw, `provenance=[]`), `:651-660` (`therapy_pain_matched`, both input chains flattened),
  `bravo_service.py:364` and `:402-407` (the four tables and the response, `prov` built at
  `:986-998` from the entries this request used, not the newest of each kind). Decisions 37, 39, 41.
- **A refused entry is replaced, not skipped** (`bravo_service.py:369-370`, `:403-406`); a response
  computed without the settings census is not stored (`:944-949`). Decision 41.
- **The served response is sanctioned** (open item 17, approved 2026-09-10); the store block, the
  amplitude and ground-truth blocks and `cache_status` are rebuilt for the serving request
  (`:965-982`).
- **The code digest** covers `*.py` and `routines/*.py` (`:150-152`), so every constant in
  `plots.py`, `objective.py`, `percept_adaptive.py` is in the key. Decision 26's reasoning.
- **The thread cap is restored**: `threadpool_limits(limits=n, user_api="blas")` is used as a
  context manager (`bravo_service.py:86`, `:847-848`) and its `__exit__` restores the original
  limits, also on an exception; `"0"` and a missing `threadpoolctl` give a no-op.
- **The shared inputs really fall back**: a failure at `bravo_service.py:1109-1117` leaves
  `_ev_inputs=None`; `closed_loop_readiness(inputs=None)` and `run_two_stage_live(evidence_inputs=None)`
  each reach `adapter.evidence_for_participant(inputs=None)` (`adapter.py:592-596`), which builds as
  before.
- **The cached design matrix** (`lfp_response.py:83-104`) keys on the right-hand side, the current
  bytes and the era labels — the only things the design depends on; the cluster labels only enter
  the covariance; the fit sees the same arrays (`test_request_speed_equalities.py`).
- **The integer epoch lookup** (`lfp_evidence.py:713-738`) is a strict improvement (the old object
  comparison mis-placed a tile after a missing time, as the commit says).
- **Tiles after the last device export are not dropped**: `_epoch_for_times` is half-open
  `[start, end)` and the last epoch's `end` is the last settings observation, but a tile is inside a
  session report whose date is at or after the tile, so no tile postdates the stream's last row.
  (Pain reports do postdate it, and `attach_pros` extends the open epoch for them, `adapter.py:404-415`.)
- **The pain objective's sign** is consistent everywhere read: `J` lower is better
  (`objective.py:7`), `gain = incumbent - candidate > 0` favours the candidate (`pipeline.py:112`,
  `stage1_openloop.py:500-502`, `bravo_service.py:1259`), expected improvement for minimisation
  (`acquisition.py:37-42`), the optimistic bound `mu - kappa*sd`, the pulse-width regression's
  "estimate > 0 is WORSE" (`stage1_openloop.py:1068-1073`), and the page's chart caption ("lower is
  better, 0 = the setting in force").
- **0 mA is a different state, not a low dose**: excluded from each side's surface
  (`plots.py:225`, `stage1_openloop.py:735`) and classified in `_stim_state`. On the scratch table 24
  epochs have the Left off and 14 the Right off; the incumbent has both on, so no arm is referenced
  to a 0 mA cell today (a guard analogous to `incumbent_rate_supported` for the amplitude axis would
  be the fix if that ever changes).
- **The 5 mA hard limit** is one constant (`objective.AMP_HARD_LIMIT_MA`) aliased, not retyped, in
  `stage1_openloop.py:132`, `stage_gate.py:95`, and the grid top (`plots.py:65`).
- **The amplitude-limits gate check** measures the delivered envelope over the whole record at any
  rate; that is the PI's flat-limit ruling (the TEED retraction of 2026-09-02, `objective.py:219-226`).
- **Era-blocked slopes with 4–5 clusters** (`RECENT_ERAS_FOR_RESPONSE = 5`, `lfp_evidence.py:813`;
  cluster = era, `:1137`): the module's own note (`:786-812`) records the cluster count as in the
  anti-conservative regime and five as "the smallest defensible window of the two the PI named".
  Deliberate; not re-flagged.
- **The rate half of the resolution check** refuses an extrapolated incumbent
  (`stage1_openloop.py:507-535`) — the same discipline S2 asks for on the pulse-width half.
- **Epoch construction is not duplicated**: `ClosedLoopDeployment/adapter.py` calls
  `StimOptimizer.adapter.exposure_epochs` (`:780`, `:2355`) rather than re-deriving it.
- **The `rank` column** the first live run lacked is handled (`bravo_service.py:379-384`) and pinned
  by `test_service_store.py`.
- **The tests' store discipline** (decision 129): every store test in this module sets
  `_SHARED_CACHE_DIR_OVERRIDE` on both `bravo_service` and `adapter` and never calls `store.clear()`
  with the override off.
- **The stored-response sweep** (decision 107) does not apply here: `KEEP_NEWEST_BY_KIND` is not
  needed because one response key per request shape is what the module wants.
- **`pivot_table` drops a pulse-width column that is all missing** (checked by running
  `exposure_epochs` on a four-row stream: `pw_us_Right` absent when every Right `pw` is NaN); this
  is how the "Left only" record of the docstring arose and is harmless once S1 resolves the column
  per side with a named fallback.
- **The audit's item 3** (`StimOptimizer/__init__.py` names a `routines/design.py` that does not
  exist) stands; a docstring, not a defect.
