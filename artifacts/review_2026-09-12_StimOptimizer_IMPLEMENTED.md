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
