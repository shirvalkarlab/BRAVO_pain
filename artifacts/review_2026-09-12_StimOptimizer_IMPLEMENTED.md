# The Stim Optimizer review of 2026-09-12, implemented

**What this is.** The code review `artifacts/review_2026-09-12_StimOptimizer.md` listed thirteen
findings (S1 to S13) and one dead-code item (S14). This document says, for each finding, what was
changed, where on the Stim Optimizer page it shows, the test that pins it, and the numbers measured
on RCS08 before and after. **Two findings change what the page recommends on RCS08 and are in their
own marked sections so the PI can reverse either one: S1 (the Right side's pulse width) and S8 (the
safety model's anchors).** S14 was not done; it is the PI's call.

**Words used below.** "Epoch": one stretch of time during which every stimulation setting the
patient could feel was held fixed. "Matched table": the epochs with the pain reports averaged onto
them; the table the optimizer fits. "Stratum": one group of epochs that share a pulse width, fitted
as its own surface by the two-stage search's first stage. "Setting in force": the rate, pulse width
and current the device is programmed to now. "The gate": the four checks that decide whether closed
loop may start. "The readiness screen": the check of every sensing contact, side and rate for a
band whose power moves with current. "Safe set": the grid cells (one stimulation rate at one
current) the safety model allows the search to propose; "reachable ceiling": the highest current a
ramp from zero can reach on every rate without crossing a cell the safety model rejects.

**How the numbers were measured.** The whole page response for RCS08 was captured through the
bridge four times, each a genuinely fresh build (the module's own store pointed at a scratch copy
of its inputs, nothing written to the production store except where a finding says so): BEFORE
(commit `8882c92c`), AFTER-1 (every finding except S8), AFTER-2 (with S8), and a CONTROL (S8's
switch off). Each pair was compared field for field, never within a tolerance; timing fields are
excluded BY NAME (`seconds`, `_utc`, `last_built`, `elapsed`, `computed`, `timing`, `duration`,
`stored_utc`, `written_utc`) and every other differing field was assigned to the finding that
explains it, with none left over (`_agent_bridge/_probe_tl/probe_so_review_compare.py`). Every
number below comes from those captures or from a test run named beside it.

---

## The suites

Run once, after every edit, through `_agent_bridge/run_both_suites.sh` (both runners at once):

- host: **1157 passed, 43 skipped, 0 failed, 0 errors** (parallel pass 1156 passed, 43 skipped;
  store pass 1 passed)
- container: **PASS=630 FAIL=0 LIVE_SKIPPED=6**

(The baseline handed to this builder was host 1084 / 42 / 0 and container 598 + 6 skipped; the
other two builders' landings added tests between that baseline and this run, and this module
added 51.)

The Stim Optimizer tests alone, on the container's host runner: **534 passed, 42 skipped** (483
before this work; 51 new tests in four new files, `tests/test_review_2026_09_12_*.py`, and two
existing tests updated to pin the new behaviour rather than deleted).

---

## S1 — THE RIGHT SIDE'S OWN PULSE WIDTH (changes the Right recommendation; his to reverse)

**What was wrong.** The first stage of the two-stage search grouped the Right side's epochs by the
LEFT side's pulse width, reported the Left's pulse width as the Right's "in force", and asked the
"has this pair been accepted in a BrainSense group" question about the Left's pulse width. On RCS08
the two sides' pulse widths differ on 67 of 92 epochs.

**What changed.** `stage1_openloop.run_stage1` now reads each side's own column (`pw_us_Left`,
`pw_us_Right`); the default `pw_col` is `None`, meaning "each side's own". When a side's own column
is absent the Left column is used and the report says so on that side (`pw_col_fallback`, a
"PULSE-WIDTH COLUMN FALLBACK" sentence in the reasons). A caller that names a column explicitly gets
that column for every side, absent or not. `FrozenConfiguration.incumbent_pw_us` keeps the Left
column's value under its old name and a new `incumbent_pw_us_by_side` carries each side's own; the
response carries it as `two_stage.stage1.frozen_configuration.incumbent_pulse_width_us_by_side`.

**On the page.** Stim Optimizer page: the decision strip at the top ("search prefers", Right row),
the "Two-stage plan" card (frozen configuration, strata table, the BrainSense-pair note), and the
"What adaptive mode ruled out" chart.

**Tests** (`tests/test_review_2026_09_12_stage1_sides.py`): on a matrix where the Left runs 60 and
140 µs and the Right 150 µs throughout, the Right setting's pulse width is 150.0, its strata are
`{("Right", 150.0)}`, its audit names `pw_us_Right`, and `incumbent_pw_us_by_side` is
`{"Left": 140.0, "Right": 150.0}`; the Left setting and summary are identical field for field with
and without a Right column; a missing Right column falls back to the Left and is named; an
explicitly named absent column is NOT OBSERVED, not substituted.

### The Right recommendation on RCS08, before and after S1 (and S2)

| | before (Left column for both sides) | after (Right column for the Right) |
|---|---|---|
| Right frozen setting | **55 Hz, 100 µs, 4.90 mA**, 15 epochs on that stratum | **55 Hz, 160 µs, 4.30 mA**, 31 epochs on that stratum |
| Right strata fitted (µs: epochs) | 60: 22, 100: 15, 140: 22 | 160: 31, 180: 21 |
| Right strata skipped (below the 8-epoch floor) | 120: 3, 180: 7 | 60: 3, 80: 6, 100: 1, 140: 3, 150: 4 |
| Right pulse width resolved | False | **None (not assessed, see S2)** |
| Right "pair accepted in a BrainSense group" | 55 Hz at 100 µs: NOT seen | 55 Hz at 160 µs: has been programmed |
| Left frozen setting | 55 Hz, 100 µs, 4.5 mA | 55 Hz, 100 µs, 4.5 mA (31 fields in common, 0 differing) |
| gate verdict | MUST NOT START (resolution check fails) | MUST NOT START (resolution check fails) |

So the page had been recommending a Right pulse width the Right side has been at on 1 of 92
epochs, fitted on strata that mixed Right pulse widths from 60 to 180 µs. **Note for the PI: with
S8 (below) also on, the Right's preferred current is 3.50 mA rather than 4.30 mA; rate and pulse
width are unchanged by S8.**

**Equality proof (BEFORE to AFTER-1, `TwoStage: true`).** 9,344 fields before, 10,122 after, 9,265
in common, 119 differing of which 2 are timing, 117 non-timing; 79 present only before, 857 only
after. Every one is assigned: S1 235 fields (the Right setting, the Right strata, the Right audit,
the Right side's adaptive-envelope exclusion record for the old 100 µs stratum, and the describe
text); S2 (inside S1's count); S3 639 fields (the per-side gate block, below); S5 4; S6 148; S7 20;
S11 1; the Left side's new `pw_col` fields 6. **Zero unexplained.** The Left setting: 31 fields in
common, 0 differing.

---

## S2 — a pulse width in force with no surface is "not assessed", never "resolved"

**What was wrong.** When the pulse width in force had too few epochs for a surface, the "pulse-width
contrast" quietly compared the best stratum against the second-best OTHER stratum and reported
that as resolved — one of the two halves the gate's resolution check needs. On RCS08's Right side,
once S1 is fixed, the pulse width in force is 150 µs with 4 epochs, and the old code read "the
pulse-width move 180 -> 160 us IS resolved" two lines above "reference pulse width 150 us is not
among the fitted levels".

**What changed.** `stage1_openloop._freeze_hemisphere`: when no fitted stratum sits at the pulse
width in force, `pw_resolved` is `None` with a reason naming the count and the floor ("the pulse
width in force (150 us) has 4 epochs, below the 8-epoch stratum floor, so no surface exists to
compare the chosen 160 us against; a contrast between two other strata would not be a comparison
with the setting in force"). The best-of-the-others contrast is kept as a number under
`detail.pw_contrast_between_other_strata`, marked "never the verdict".

**On the page.** Stim Optimizer page: the decision strip's verdict symbol for the Right row and the
gate's second check ("Rate and pulse width resolved against their own uncertainty").

**Tests** (same file): a matrix whose incumbent sits on a 4-epoch level with two 20-epoch levels
elsewhere gives `pw_resolved is None`, `resolved False`, `pw_reference_us None`,
`pw_in_force_n_epochs 4`, the sentence above, and a recorded other-strata contrast; the control
with the incumbent on a fitted level has the reference equal to the pulse width in force.

**Live.** Right `pulse_width_resolved` False -> None; the gate's resolution check still refuses
(verdict unchanged); Left 0 fields differing.

---

## S3 — the gate judges each side on its own sensing evidence

**What was wrong.** The band-response check ran once, on one evidence cell, for a configuration
that freezes a setting per side: one sensing contact's response licensed closed loop on both sides.
On the live path the cell handed to the gate was the screened best across BOTH sides.

**What changed.** `stage_gate.check_adaptive_band` takes `lfp` as one evidence object (attributed
to the side its `hemisphere` names, or to the only frozen side when it names none) or a mapping
`{side: evidence}`; it evaluates each frozen side, passes only when every side passes, marks a side
with no evidence NOT ASSESSED (which blocks), and reports `evidence.per_hemisphere` with each
side's own counts, band rows, sensing contact and laterality. `pipeline.run_two_stage_live` now
selects ONE CELL PER FROZEN SIDE from one build (`select_for_side`, using the screen's own ranking
restricted to that side and rate, `lfp_evidence.best_deployable`), pins each side to its own frozen
rate, and records `selected_by_side` in the manifest. Two sides freezing different rates no longer
refuse. Stage 2 reads per-side evidence the same way (`stage_gate.evidence_for_side`).

**On the page.** Stim Optimizer page, the four-check strip: "A sensed band inside 8–30 Hz responds
to stimulation current" now shows one block per side, each with its own "n of 18 bands respond ·
n fall once time is removed", its own band strip, and the contact it was read on
(`ClosedLoopChecks.js`). Source-only; the orchestrator rebuilds the bundle.

**Tests** (`tests/test_review_2026_09_12_gate_sides.py`): Left-only evidence with two frozen sides
gives `passed None`, Left PASS and Right NOT ASSESSED in the sentence, `per_hemisphere.Right.reason
== "no evidence for this side"`; evidence per side for both sides passes; one side failing fails
the condition; untagged evidence is attributed to the only frozen side, and to neither of two;
tagged evidence never licenses the other side; `select_for_side` picks that side's best deployable
cell and returns nothing with a reason for a side with none.

**Live (RCS08, `TwoStage: true`).** Before: one cell, ZERO_TWO_LEFT / Left at 55 Hz, "12 of 18
tested bands respond", no side named. After: Left — ZERO_TWO_LEFT at 55 Hz, 12 of 18 respond, 18 of
18 negative once time is removed, PASS; Right — **ZERO_THREE_LEFT** at 55 Hz, 15 of 18 respond, 12
of 18 negative, PASS. **The Right side's check read a sensing contact on the LEFT lead (L 0⁻3⁺)
against the Right side's current**: the screen ranks a same-side contact first and takes a
contralateral one only when no same-side contact passes at that rate, which is what happened here.
The note now says so ("a CONTRALATERAL sensing contact: no contact on this side passed the screen
at this rate") and the page prints "a contact on the other side (none on this side passed)". The
condition passes on both sides; the gate still refuses on the resolution check, so nothing on
screen changes verdict.

---

## S4 — one rule for "this band responds"

**What was wrong.** The readiness screen called a cell deployable only when a MAJORITY of its 18
bands respond AND a majority carry a significant negative era-blocked slope; the gate passed a cell
on ANY ONE responding band and never looked at the era-blocked slope; the page drew the gate's
weaker count.

**What changed.** `lfp_evidence.cell_response_verdict` is the one rule; `screen_cells` and the
gate both call it (the gate imports it lazily because `lfp_evidence` imports the gate at its top).
Each band row the page draws now carries `era_negative_significant` beside `responds`, and the
band strip (`BandResponseStrip.js`) colours a bar green only when both hold, amber when the band
responds by direction alone.

**Tests** (same file): a constructed cell where 3 of 18 bands respond by direction and none has a
negative era-blocked slope is refused by the screen AND by the gate with the same sentences word
for word; the gate's own fixture gives 19 of 35 bands responding and 19 negative-significant, and
passes; the rows' flag equals the responding set on that fixture.

**Live.** On RCS08's Left band strip (ZERO_TWO_LEFT at 55 Hz): **18 rows before, 18 after; 234
fields in common, 0 differing, 18 added (the flag); 0 of 18 bands change state** — the 12 that
responded before are the 12 that respond now, all 18 carry a negative era-blocked slope, so 12
bars are green and 0 amber. The gate's `n_passing` (12) equals the screen's `n_responding` (12) for
that cell.

---

## S5 — the stopping rule is told it has no batch history

**What changed.** `acquisition.check_stopping` with an empty history returns `binding =
"not assessable: no batch history"`, `plateau_met = None`, `stop = False`; both callers
(`pipeline.run`, `stage1_openloop._fit_slice`) now pass an empty history instead of a one-item
one. **On the page: nowhere** (`stop` and `stop_binding` are in the summary rows and the stored
`stim_optimizer_summary` only).

**Test** (`tests/test_review_2026_09_12_small_findings.py`): the label and `plateau_met None` with
no history, "coverage"/"plateau" still with a real history, and both fitters' summary rows carry
the new label. **Live:** `summary[0..3].stop_binding` "coverage" -> "not assessable: no batch
history" (4 fields), and the five Stage 1 strata rows likewise; nothing else in those rows moved.

---

## S6 — the queue says which cells closed loop cannot use (minimal; nothing removed)

**What changed.** `pipeline._queue_frame` and `_batch_frame` add `adaptive_capable` (rate at or
above `adaptive_envelope.MIN_RATE_HZ`, imported, 55 Hz). The queue table on the page ("What to test
at the next visit") gains a "closed loop" column reading "usable" or "adaptive cannot use"
(`index.js`, source-only). The list is not held to the envelope; that is the PI's call.

**Test:** every row's flag equals `freq_hz >= 55`; dropping the column leaves every existing queue
value identical to the context's own arrays. **Live (AFTER-1 against BEFORE):** 148 fields added
(25 queue and 12 batch rows on each of 4 arms), 0 existing queue values changed; rows marked
"adaptive cannot use": left_leg__Left 16 of 25, left_leg__Right 8 of 25, back__Left 16 of 25,
back__Right 25 of 25.

---

## S7 — "setting in force" is the newest device setting, rated or not

**What changed.** `bravo_service.in_force_by_side(es, epochs=)` reads the newest epoch of the full
epoch table (every epoch, rated or not) when handed one — the service hands it the epochs the
evidence inputs already carry, else the stream collapsed to epochs (0.02 s) — and each side's block
carries `has_ratings_yet`, `fitted_incumbent_epoch` (the newest RATED epoch, which every surface's
gain is still referenced to, unchanged), `differs_from_fitted_incumbent` and a `note` when they
differ. The decision strip prints a line under "programmed now" when no rating has been filed under
the setting in force yet (`DecisionStrip.js`, source-only).

**Test:** a stream whose newest epoch (3) has no rating and a matched table holding epochs 1 and 2:
the block names epoch 3 (Right 160 µs, Left 3.5 mA), `has_ratings_yet False`,
`fitted_incumbent_epoch 2.0`, and the note reads "epoch 3 since … against epoch 2". **Live:**
`exposure_epochs` max epoch 123 (123 epochs) and the matched table's max epoch 123 (92 rated), as
the review expected; both sides `has_ratings_yet True`, `differs_from_fitted_incumbent False`. 10
fields added per response, 0 existing values changed.

---

## S9 — the epochs open on the Left rate; the stream now checks the two sides agree

**Measured first (bridge, read-only):** on RCS08's stream 1,207 timestamps, 1,172 with both sides,
**0 with different rates**; both sides ran 10, 55, 110, 125, 130, 145 and 165 Hz. So the epoch keys
are left as they are, and `adapter.exposure_epochs` now counts the disagreeing timestamps into the
epoch table's `attrs["n_timestamps_rates_differ"]` and `attrs["rates_agree_across_sides"]`, logging
a warning when the count is not zero. **Test:** 0 on the fixture; 1 and `False` after one Right
rate is changed, with `freq_hz` still the Left's.

## S10 — an unrated incumbent is refused by name

`objective.build_objective` raises "the incumbent epoch N carries no <item> rating, so J cannot be
referenced to it" instead of letting every epoch read infeasible and the arm be skipped as "only 0
feasible epochs … too few to fit a surface". **Test:** the message, and `pipeline.run` records it
as the arm's skip reason. No live change (RCS08's newest epoch carries both items).

## S11 — the response key names what it did not (the key changes by design)

`bravo_service._response_signature`'s response-only tail is now 9 elements: the deployable band
range (the two Biomarkers constants the evidence centres depend on, read through
`adapter.deployable_band_span`), the `ClosedLoop` flag (moved out of the four tables' key), the
two-stage flag, the override reason AND its name, the explore-outside override AND its name, and the
backend. **This changes every stored response's key by design**; the four tables' key is unchanged
in content. **Tests:** the two names change the response key and not the tables' key; the
`ClosedLoop` flag likewise; a different band range is a different key. The existing tail-count test
was updated from 4 to 9. **Live:** `store.response_key` differs (1 field).

## S12 — the three single-spelling imports

`adapter.py`: the two `modules.Biomarkers.bravo_service` imports try both spellings;
`_deployable_band_span` tries both spellings and RAISES when the constants cannot be read, instead
of returning `None` (which `evidence_inputs` read as "carry every centre the cache holds": 98
centres instead of 22 under the host runner, with no message). **Test:** `deployable_band_span()`
reads (7.8, 30.0); the source carries both spellings; no `return None` in the span function.

## S13 — one definition each for the 8–30 Hz range and the 18 bands

`lfp_evidence.build_evidence` reads `percept_adaptive.ADAPTIVE_LFP_BAND_HZ` (it looked for a
`GATE.ADAPTIVE_BAND_HZ` no module defines and fell through to a literal); `closed_loop_readiness`
passes `bands=None` so the cache's own centres and width are used, as the two-stage path does.
**Live:** the readiness block (`closed_loop.*`, 3,203 fields) is identical before and after, 0
differing — the hand-built list equalled the derived one, which is the proof that nothing moved
and the reason the duplication could go.

## The loading line

`index.js`: "Fitting one Gaussian-process surrogate per arm…" replaced with a sentence saying most
of the ~10 s is loading the recordings and running the readiness screen and that the four surface
fits take about a second (measured this morning: the four arm fits 0.97 s of 9.2–10.2 s; the
readiness screen 3.2–3.6 s; loading the tile cache 2.6–2.9 s). Source-only.

---

## S8 — THE SAFETY MODEL'S ANCHORS FROM THE STREAM (changes the safe set; his to reverse)

**The check the review asked for, done first (bridge, read-only).** RCS08's settings stream: 6,689
rows; `upper` present on 1,006 (5,683 missing). Of the twelve hard-coded anchors, **3 match a row of
a sensing-configured group, 8 match a legacy-program row, and 4 match no row at all** (10 Hz/1.9,
110 Hz/3.2, 165 Hz/2.5, 110 Hz/2.2).

**What changed.**
- The stream carries `upper_is_patient_limit` on every row: a legacy program's upper limit is a
  clinician's ceiling (True when present); a sensing channel's is judged by decision 136's rule,
  IMPORTED from `ClosedLoopDeployment/session_report_facts._patient_limits_configured` with the
  double spelling, never retyped (a limit on a channel whose adaptive therapy is RUNNING is the
  controller's own range). The stream's rule version is bumped to `v2_active_groups_limit_kind`,
  so the stored stream and the matched table were rebuilt once (about 35 s; **the rebuilt matched
  table equals the old one: 3,036 fields, 0 differing**).
- `plots.limit_anchors_from_stream(stream, side)` builds each side's anchors: every distinct
  (rate, upper) among legacy rows and sensing rows whose limit is a patient limit; it returns a
  `meta` saying the source and what was excluded; with fewer than one usable anchor, or the switch
  off, it returns the hard-coded snapshot with a source that says so.
- **`plots.USE_STREAM_LIMIT_ANCHORS = True` is the switch.** `pipeline.run` and `run_stage1` take
  `limit_anchors_by_hemisphere`; the service builds it once per request from the stream; each
  arm's response carries `safety_anchors` (source, count, the pairs, how many stream rows had a
  limit, how many were excluded as adaptive limits). **On the page: not drawn yet** — it is in the
  response under `arms.<arm>.safety_anchors` and in `two_stage.stage1.audit.per_hemisphere.<side>
  .limit_anchors`.

**Live on RCS08.** 1,006 rows with an upper limit: 392 legacy (all patient limits), 614 sensing, of
which 450 patient limits and **164 adaptive amplitude limits (excluded)**. Left: **19 anchors** from
493 rows (82 adaptive limits excluded): 10 Hz 1.6, 2.5; 55 Hz 1.6, 1.8, 1.9, 2.0, 2.5, 3.5, 4.0,
4.5; 110 Hz 1.0, 4.0; 125 Hz 2.2, 2.5, 4.0; 130 Hz 3.2; 145 Hz 4.8; 165 Hz 2.0, 4.8. Right: **21
anchors** from 513 rows (82 excluded): 10 Hz 1.2, 2.0; 55 Hz 1.2, 1.4, 1.5, 1.6, 1.8, 2.0, 3.0,
3.5, 4.0, 4.5; 110 Hz 2.0, 3.0, 4.0; 125 Hz 3.0; 130 Hz 3.4; 145 Hz 2.4, 3.0; 165 Hz 1.8, 3.0.

### Per arm, before (hard-coded twelve) and after (the stream's anchors)

| arm | safe cells before → after (of 612) | reachable ceiling before → after | optimum before → after |
|---|---|---|---|
| left_leg__Left | 612 → **228** | 5.0 mA → **0.1 mA** | 55 Hz 4.70 mA → 55 Hz 3.80 mA |
| back__Left | 612 → **228** | 5.0 mA → **0.1 mA** | 55 Hz 4.80 mA → 55 Hz 3.80 mA |
| left_leg__Right | 564 → **216** | 1.9 mA → 1.7 mA | 55 Hz 4.00 mA → **55 Hz 1.00 mA** |
| back__Right | 564 → **216** | 1.9 mA → 1.7 mA | 40 Hz 4.90 mA → **40 Hz 1.70 mA** |

Stage 1 (two-stage plan): Left strata safe cells 612 → 540, **Left preferred setting unchanged**
(55 Hz, 100 µs, 4.5 mA); Right strata 576 → 432, **Right preferred 55 Hz, 160 µs, 4.30 mA →
3.50 mA**. The gate's verdict is unchanged (refuses on the resolution check). The blockers on the
page change from "the safe set is not contiguous" on the two Right arms to the two Left arms, and
"proposed optimum lies ABOVE the contiguous safe ceiling" now names the Left arms (3.8 mA against a
reachable ceiling of 0.1 mA). The queue's `safe` column now reads False on 21, 23, 21 and 25 of 25
rows.

**Read this before deciding.** The stream's anchors are more numerous and several are LOWER than the
hard-coded ones (a 1.0 mA upper limit at 110 Hz on the Left; 1.2–1.6 mA limits at 55 Hz on both
sides, from sensing-configured groups that were NOT running adaptive therapy, so decision 136's rule
calls them patient limits). The safety model treats every anchor as "severity at the threshold",
so the safe set shrinks and the Left reachable ceiling collapses to 0.1 mA — while the same record
shows 4.5–4.8 mA tolerated at 55 Hz for weeks. Whether a programmed upper limit on a sensing-only
group is a clinician's ceiling in the sense the safety model wants is a judgement the review did
not settle and this change does not settle either; it is the reason the switch exists. **Switching
it off (`plots.USE_STREAM_LIMIT_ANCHORS = False`) restores the previous numbers exactly**: the
CONTROL capture against AFTER-1 has 10,122 fields in common and 8 non-timing differences, every one
a store key (the rebuilt stream and matched table have new keys) or the S3 laterality note; every
surface, safe set, optimum and Stage 1 number is identical.

**Equality proof (AFTER-1 to AFTER-2, `TwoStage: true`).** 10,122 fields before, 10,397 after,
10,121 in common, 503 differing of which 2 timing, 501 non-timing; 1 only-before, 276 only-after.
S8 owns 673 fields (the four arms' surfaces, optima, comparisons, queue and batch rows, the summary
rows, the Stage 1 strata, the blockers, the anchors meta, and the input store keys); 14 queue-row
`adaptive_capable` values differ because the queue holds different cells now (S8, caught by the S6
rule); S1 84 and S3 5 fields are the laterality note and the Right strata's safe counts; S11 2 (the
response key and cache status). **Zero unexplained.** Without the flag: 8,600 → 8,779 fields, 461
non-timing differing, all S8 (445) or the keys.

**Tests** (`tests/test_review_2026_09_12_limit_anchors.py`, 14): a sensing limit under RUNNING
adaptive therapy is not a patient limit; a legacy limit is; the rule is imported not copied; the
rule version is bumped; the builder keeps legacy and patient-limit sensing rows and drops the
adaptive one, per side, excludes an unknown kind, keeps a legacy row whatever the kind column says,
returns the hard-coded snapshot exactly when the switch is off or nothing is usable (and says why),
and survives nulls read back from Parquet; each arm and each Stage 1 side read their own anchors
and record them; the safe count is 57 under an anchor at every grid rate at 1.0 mA against 247
under the hard-coded twelve (measured, on the test design); and handing every side the hard-coded
set through the new argument gives the same fit, field for field, as handing nothing.

---

## Not done, and why

- **S14 (dead code)**: not touched; the PI's call, as the review says.
- **The frontend bundle**: not rebuilt by this builder (the orchestrator rebuilds once; another
  builder was building concurrently). The five source files changed under
  `Client/src/views/Reports/StimOptimizer/` are `index.js` (loading line, queue column),
  `ClosedLoopChecks.js` (per-side band-response blocks), `BandResponseStrip.js` (both halves of the
  rule, legend), `DecisionStrip.js` (the unrated-setting line). Nothing in them was watched in a
  browser.
- **`safety_anchors` on the page**: in the response only; drawing it is a page change beyond the
  review's "report the anchor count and source in meta".
- **A pre-existing difference between the two fitters, seen while measuring S8, not changed**: the
  flat fit's safe set and Stage 1's differ for the same side under the same anchors (flat Left 228,
  Stage 1 Left 540) because the flat fit seeds the safety model from epochs with that side's current
  above zero and Stage 1 from every epoch. Recorded here for the PI; it predates this work.

## Suites (both runners, one run, after every edit, job 20260912-143636-46262b0a)

- host: `1157 passed, 43 skipped, 0 failed, 0 errors  [parallel: 1156 passed, 43 skipped in 10.17s | store, serial: 1 passed, 1199 deselected in 0.42s]`
- container: `PASS=630 FAIL=0 LIVE_SKIPPED=6`

The gunicorn workers were reloaded (`kill -HUP 1`) after the last edit, so the live server runs
this code; the first page load rebuilt the settings stream under its new rule version.

---

## S14 and item 3, done on the PI's decision of 2026-09-12

**What was decided.** On the evening of 2026-09-12 the PI said to delete the Stim Optimizer code
that nothing reaches (review S14, "delete item 7 as listed"), and, for item 3 of the "Make
Closed-Loop Work" session, that the safety model's ceiling is a current HE STATES per side, not a
number read out of the device's programmed limits. Both are built, proven on RCS08, and the
suites are green. Nothing here is on the Closed-Loop Deployment page; everything is on the **Stim
Optimizer page**, and the sections are named below.

**Words used.** "Safety model": the model of side-effect severity whose "safe set" is the grid
cells (one stimulation rate at one current) the search may propose. "Reachable ceiling" (printed
"safe ceiling" on the arm cards): the highest current a ramp from zero reaches on every rate
without crossing a cell the safety model rejects. "Stated ceiling": the current above which the PI
says a side is not acceptable; new today. "Tolerated setting": a rate-and-current the patient
held for at least 72 hours with that side's current above zero.

### A. The unused code is deleted (S14)

Each name on the review's list was searched for again across `modules/` and `Server/` (tests and
the scratch area excluded) before anything was removed, because today's other work added
callers in several places. **Two names on the list now HAVE a caller and were kept:**
`lfp_response.device_band_power` (called by `stage_gate.py`, the gate's band-power check) and
`percept_adaptive.validate_policy` (called by `stage2_closedloop.py`, which the two-stage path
reaches since decision 137). `within_visit.ramp_windows_from_amplitude` was kept as instructed
(decision 144's margin is its reason to exist).

Deleted, with line counts from `git diff --stat`:

- **Four whole modules, 3,696 lines:** `routines/schedule.py` (211; the blank clinic sheet),
  `routines/session_analysis.py` (998; the analysis of a filled-in sheet),
  `routines/safety_ordinal.py` (917; the ordinal severity model) and
  `routines/surrogate_torch.py` (1,570; the PyTorch/BoTorch twin of the surrogate). **Their four
  test files, 2,128 lines** (`test_schedule.py` 111, `test_session_analysis.py` 755,
  `test_safety_ordinal.py` 413, `test_surrogate_torch.py` 849).
- **Seven functions inside kept files:** `lfp_response.span_needed_for_separation`,
  `expected_separation_d` and `within_arm_sd_from_result` (121 lines net; the reasoning about why
  the separation floor does not scale with the current span is kept above where they were);
  `acquisition.lower_confidence_bound` and `select_batch_between_visit` (61 lines net);
  `percept_adaptive.derive_single_threshold` with its 0.75 constant (18 lines net; the device
  fact is kept as a comment); `within_visit.band_cluster_permutation` with its two private helpers
  and its threshold constant (247 lines net; a note stands where the block was). None of the
  seven had a test of its own left to delete.
- **Tests split rather than weakened:** `test_safety_and_evidence.py` lost its 6 tests of
  `schedule.safety_filter` and keeps its other 42; the 14-test anchors file of review S8 became
  `test_stream_limit_kind.py`, keeping the 4 tests of the stream's own "is this limit a patient
  limit" column (a fact about the record that stays on the stream) and dropping the 10 that
  tested the deleted builder and plumbing.
- **The PyTorch backend option:** there was no request key that could select it -- the only
  `Backend` key on the request chooses the figure renderer (`plotly` or `none`) -- so nothing had
  to be refused; the response's `two_stage.backend` sentence now says the PyTorch backend was
  deleted on 2026-09-12 and no request can select it. `BOTORCH_REFACTOR.md` carries a note at the
  top saying the code it describes is gone.

**Proof that A changes nothing but the key.** Genuinely fresh builds through the scratch store
override, before any edit and after A alone:

- without `TwoStage`: **8,738 fields before, 8,738 after, 8,738 in common, 0 only-before, 0
  only-after, 1 non-timing difference: `store.response_key`** (the key hashes every file in the
  package, so deleting files changes it; a stored response rebuilds once).
- with `TwoStage: true`: **10,324 / 10,324 / 10,324 in common, 0 / 0, 2 non-timing differences:
  the key and the `two_stage.backend` sentence** reworded above.

### B. The safety model's ceiling is the current the PI states (item 3)

**Where it lives.** `BRAVO/modules/StimOptimizer/safety_ceiling.py`, and the ONE place to change a
number is its table:

```
PI_STATED_CEILING_MA = {"2e3c75c00d7f4f37b53a048d195f11da": {"Left": 5.0, "Right": 5.0}}
```

with the provenance "stated by PI (2026-09-02 hard limit, objective.AMP_HARD_LIMIT_MA; confirmed
as the safety ceiling 2026-09-12)". 5.0 mA is the hard limit he set on 2026-09-02 and the only
ceiling he has stated; whether a lower per-side value is wanted is being put to him, and editing
that table is the whole change. A participant with no row falls back to the module hard limit
with the provenance "module hard limit, no PI-stated ceiling for this participant"; a stated
value above the hard limit is clamped to it and the provenance says so; a non-positive value is
refused. The table's file is inside the package the response key hashes, so a changed number is
never served from a copy computed under the old one.

**What the safety model is now told.** Severity 3 ("not acceptable") at the stated ceiling, once
at every stimulation rate on the search grid (12 anchors, a flat line across the rate axis), and
severity 0 at every tolerated setting. **The twelve typed numbers of 2026-08 (`LIMIT_ANCHORS`),
the stream-derived anchors behind the switch (`limit_anchors_from_stream`,
`USE_STREAM_LIMIT_ANCHORS`) and their tests are deleted** -- the PI chose neither input.

**One seed builder for both fitters.** The flat fit (`plots.build_context`) and the two-stage
search's Stage 1 (`run_stage1`) now call the same function (`safety_ceiling.safety_seed`). Until
today they read different tolerated sets: Stage 1 also counted epochs where THIS side was at 0 mA
as "tolerated at zero current", the flat fit did not, so one side under one set of anchors had
two safe sets (S8's report recorded flat Left 228 against Stage 1 Left 540). The shared rule is
the flat fit's: a side at 0 mA is a different therapeutic state, not the low end of its dose axis
(OBJECTIVE_SPEC amendment 2026-08-29), so it says nothing about what that side tolerates. On
RCS08 the two fitters now agree per side (below).

**The gate reads the same source.** The two-stage plan's "closed-loop current limits inside the
delivered range and under the ceiling" check is handed the same per-side ceilings; each side's
upper limit is judged against its own, and the evidence carries `ceiling_by_side` with the
provenance. A page from before today that carries only the one number still renders.

**On screen (Stim Optimizer page).** The arm cards ("safe ceiling N mA" now carries a hover text
naming the stated ceiling and its provenance -- `ArmGainStrip.js`); the queue table's `safe`
column; the blockers list; and, in the "Two-stage plan" card, the gate's ceiling line, which
reads "ceiling L 5.0 mA · R 5.0 mA" with the provenance on hover (`ClosedLoopChecks.js`). Source
only; the orchestrator rebuilds the bundle, and nothing was watched in a browser.

### Per arm on RCS08, before (the hard-coded twelve, switch off) and after (the stated 5.0 mA)

| arm | safe cells (of 612) | contiguous | reachable ceiling | flat optimum |
|---|---|---|---|---|
| left_leg__Left | 612 → **600** | yes → yes | 5.0 → **4.9 mA** | 55 Hz 4.70 mA → 55 Hz 4.70 mA |
| back__Left | 612 → **600** | yes → yes | 5.0 → **4.9 mA** | 55 Hz 4.80 mA → 55 Hz 4.80 mA |
| left_leg__Right | 564 → **588** | **no → yes** | 1.9 → **4.8 mA** | 55 Hz 4.00 mA → 55 Hz 4.00 mA |
| back__Right | 564 → **588** | **no → yes** | 1.9 → **4.8 mA** | 40 Hz 4.90 mA → **40 Hz 4.80 mA** |

What the numbers mean: with the ceiling at 5.0 mA on every rate, the 5.0 mA row of the grid is
no longer safe on the Left (12 rates × 1 cell = 612 → 600; the Left tolerated 4.8 mA), so the
reachable ceiling is one step below the stated one. On the Right the twelve old anchors (five of
them at 55 Hz between 1.6 and 2.0 mA) had cut the safe set into islands with a reachable ceiling
of 1.9 mA under a record where 4.5 mA was delivered; under the stated ceiling the Right's safe
set is one piece up to 4.8 mA, with the 4.9 and 5.0 mA rows out (24 cells, 612 → 588: nothing on
the Right was tolerated above 4.5 mA, so the model's uncertainty next to the ceiling anchor keeps
one more row out than on the Left). The back__Right optimum moves from the now-unsafe 4.9 mA cell
to 4.8 mA. Tolerated settings: Left 26, Right 30. Queue rows marked unsafe, of 25 (read from the
capture): Left arms 0 → 2 (40 Hz 5.0 mA and 55 Hz 5.0 mA), left_leg__Right 3 → 0, back__Right
1 → 2 (40 Hz 5.0 and 40 Hz 4.9 mA).

**Stage 1 (two-stage plan):** Left strata safe cells 612 → **600**, Right 576 → **588** -- now
equal to the flat fit's on each side, which is the "one seed builder" point above. **The
preferred settings are unchanged:** Left 55 Hz, 100 us, 4.50 mA; Right 55 Hz, 160 us, 4.30 mA.
**The gate's verdict is unchanged** (refuses on the open-loop resolution check; the ceiling check
passes, "Left 1-4.8 mA; Right 1-4.5 mA under the 5 mA ceiling").

**Blockers on the page:** the two "the safe set is not contiguous" blockers on the Right arms and
the "proposed optimum lies ABOVE the contiguous safe ceiling" blocker (Right arms, 4.0 and 4.9 mA
against 1.9) are gone; the "above the highest amplitude ever delivered" note on back__Right now
reads 4.8 mA against 4.5; the two record-wide notes stand. `recommendation_supported` stays False.

**Proof (after A alone, against after A and B).** Timing fields excluded by name; every other
difference assigned; **0 unexplained** in either shape
(`_agent_bridge/_probe_tl/probe_so_s14_compare.py`):

- without `TwoStage`: 8,738 fields before, 8,739 after, 8,623 in common, 115 only-before, 116
  only-after, 120 non-timing differences -- the key (1); the four arms' `safety_anchors` blocks
  (the twelve typed anchors and the stream counts gone, the ceiling, its provenance, the 12
  ceiling anchors and the tolerated count in; 4 differing + 112 + 116); and 118 under the safe
  set, the reachable ceiling, the optimum, the queue's `safe` column, the batches and the
  blockers (115 differing, 3 only-before: the three blocker sentences that no longer apply).
- with `TwoStage: true`: 10,324 / 10,327 / 10,147 in common, 177 / 180, 135 non-timing -- the
  key (1); the anchors blocks on the four arms and the two Stage 1 audits (4 + 174 + 176); the
  gate's `ceiling_by_side` (4 only-after); and 133 under the safe set, queue, batches, blockers
  and Stage 1's strata (130 differing, 3 only-before).

No speed claim is made.

**Live.** The four gunicorn workers were reloaded (`kill -HUP 1`, four new PIDs). Through the
production store, the page's own request rebuilt once under the new key (9.4 s, `served_from_store
False`) and was served on the second call (1.8 s), with `ceiling_mA 5.0` and the PI provenance on
every arm and the Left reachable ceiling 4.9 mA.

**Tests** (`tests/test_safety_ceiling.py`, 18): RCS08 reads 5.0 on both sides with the PI
provenance; an unknown participant, or a missing side, falls back to the hard limit and says so;
a value above the hard limit is clamped and says so; a non-positive or non-numeric value is
refused; the uid appears in no module but the table's; the ceiling anchors are one per grid rate
at the ceiling; tolerated anchors exclude 0 mA and holds under 72 h; the seed's shape and
severities equal what the model's own seeder makes of the same two sets; a seed with nothing
tolerated is refused, never silently empty; each arm records its own side's ceiling and
provenance; **measured on the test design in the container** (`probe_ceiling_test_design.py`),
the Left arm's safe cells and reachable ceiling under a stated 5.0 / 4.0 / 3.0 / 2.0 mA are 612 /
5.0, 468 / 3.8, 324 / 2.6, 240 / 1.9, and under 1.0 mA -- below what the design tolerated -- 57
cells and no contiguous ceiling (pinned: 612/5.0, 240/1.9, 57/NaN); the flat fit and Stage 1
agree on the safe set with 0 mA epochs present; Stage 1 writes each side's ceiling into its
audit; the gate judges each side against its own ceiling and reports both; a plain number still
works. The wiring test hands the direct call the same ceilings the service builds.

### Suites (both runners, one run after every edit, job 20260912-190502-56ce2fdf)

- host: `1038 passed, 2 skipped, 0 failed, 0 errors  [parallel: 1037 passed, 2 skipped in 10.26s | store, serial: 1 passed, 1039 deselected in 0.40s]`
- container: `PASS=630 FAIL=0 LIVE_SKIPPED=6`

**The arithmetic against the baseline (host 1161 / 43 / 0).** Items collected on the host went
from 1,204 to 1,040, −164 exactly: the four deleted files collected 166 (12 + 89 + 32 + 33,
counted by collecting the HEAD versions in the container), 10 anchor-builder tests and 6
`safety_filter` tests went, 18 new ceiling tests came. Skipped 43 → 2: the 41 that went were the
PyTorch tests in `test_surrogate_torch.py` and `test_safety_ordinal.py`, which skipped because the
container has no torch. Passed 1161 → 1038: 141 passing tests removed, 18 added. The container
runner does not run Stim Optimizer, so its count is unaffected by this work; its line is what the
run printed with the other builder's Biomarkers edits in the working tree.
