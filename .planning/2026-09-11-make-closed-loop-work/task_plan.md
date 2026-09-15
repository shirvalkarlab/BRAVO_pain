# Task Plan: Make Closed-Loop Work
## Goal
The Closed-Loop Deployment page's device-rule ledger stops blocking the verdict on rows whose only
problem is that the module never handed the rule the value the device already records; every row
that still blocks does so for a reason the PI has read and agreed with.

## Next Step
Phase 22 is complete: the "Make Google sheet" button on `TitrationSessionCard.js` now works.
`StimOptimizer/sheet_export.py` copies the lab's template (never writing into it -- checked by
re-hashing the template file after every fill), fills the copy with the SAME `sheet_rows` the page
shows, and either writes a real, shared Google Sheet (when this server has Google credentials,
`StimOptimizer/google_sheets_client.py`) or streams a filled `.xlsx` download when it does not; a
re-export for the same visit date overwrites that one file rather than making a second copy. The
new endpoint, `/api/exportTitrationSheet`, rebuilds the plan through the same code path the page's
own request uses, so the exported sheet can never drift from what is on screen. No Google
credentials exist on this server today, so every real run so far has taken the download path;
proven live on RCS08 both as a direct module call and through the real Django view (200, correct
file name, byte-identical to the direct call). All 22 phases of this plan are now done. What
remains open is not code: the threshold re-centring / separation question (decision 139's capture
question) is the PI's call, T7's own acceptance test needs a real titration session recorded on
RCS08 (open item 30, a clinical scheduling matter), and turning the Drive path on needs the PI to
create and share a Google service-account key (`google_sheets_client.SETUP_NOTE`).

## Current Phase
Phase 22 (last phase; plan complete)

phases: 22/22 complete

### Phase 1: Measure what the ledger says today
- [x] Run the live report on RCS08 at the committed band (L 0-2+, 24.5 Hz) and list every non-pass row
- [x] Read what each blocked rule reads, and where that value lives in the record
- [x] Read the impedance recordings' measurement current across the record
- **Status:** complete

### Phase 2: Rate and pulse width reach D27, D31 and D44 (brief items 2, 4, 5)
- [x] Device facts carry the programmed rate and pulse width for the sensing hemisphere, from the newest exposure epoch, with provenance
- [x] D27 reads the capture pulse width when the record has it, falling back to the programmed one
- [x] Tests pin: candidate-supplied values win; hemisphere-specific; absent epochs give None not a fabricated value
- [x] Live on RCS08: D27 and D31 pass, D44 advisory resolves; field-count / difference-count against the Phase 1 capture
- **Status:** complete

### Phase 3: D16 impedance reads the measurement current (brief item 1)
- [x] impedance_facts records the measurement current of each recording and prefers the newest FIXED-current reading over the automatic-increase default
- [x] A reading over the open limit at automatic-increase, with a fixed-current reading in range, is reported as a spurious fail, not a fail
- [x] The measurement current is on the ledger row and in device_facts_provenance
- [x] Live on RCS08: D16's verdict and observed text; both suites
- **Status:** complete

### Phase 4: D19 passes on point signs; D30 derived from the live active sensing group; the stale summary
- [x] C1: the newest session report's ACTIVE sensing group (rate, pulse widths, adaptive status, group, report date) read live from the ingested encrypted file, memoised on that file's identity
- [x] C1: D30 derived -- rate_committed_for_this_attempt = candidate rate equals the active sensing group's rate; provenance names the group, rate and report date
- [x] C1: D19 passes on the point signs of the three edges; observed text names the unresolved edges with their intervals
- [x] C2: the whole session-report summary rebuilt from the ingested files off the request path (daily pass), stored on the file set; the committed 2026-09-05 file kept as a dated fallback
- [x] Live on RCS08: D19 and D30 rows; D32 after C2; field-count / difference-count; both suites
- **Status:** complete

### Phase 6: Stim Optimizer load time (PI: "chunk work, vectorize, parallelize, GPU offload if viable")
- [x] Profile run_for_participant on RCS08 through the bridge; name the top costs
- [x] Implement the optimisations that keep every number identical; alternating-round timings; field-count / difference-count proof
- [x] GPU: state plainly whether one exists in the container (OrbStack Linux VM on a Mac: expected none)
- [x] Both suites; commit; push
- **Status:** complete

### Phase 7: Code review of the three modules, findings implemented
- [x] Three reviewers in parallel (Biomarkers, Closed-Loop, Stim Optimizer), actionable findings with evidence
- [x] Findings implemented by builders, one module at a time, suites after each; equality proofs where a number could move
- [x] Decisions and the review report into the record; commit; push
- **Status:** complete

### Phase 8: The PI's answers to the review's open items
- [x] B8: the analytics no panel reads and the figures nothing draws are dropped from the Biomarkers request; B12: the two unused endpoints removed
- [x] S14: the unused Stim Optimizer code deleted; the code digest no longer hashes files nothing calls
- [x] Item 3: the safety model seeded from a PI-stated amplitude ceiling per side, one place to change, provenance "stated by PI"
- [x] Item 4 + open item 30: the Stim Optimizer page recommends the titration session (rate, steps, hold, sides, contacts, bands to avoid), states that the 20 s post-ramp margin switches on once such a run exists
- [x] Suites, equality proofs, commits, decisions
- **Status:** complete

### Phase 9: "Established" is the point sign, flagged provisional (PI, 2026-09-13)
- [x] An edge is resolved by its point estimate's sign; interval/p kept as caveats; the report counts the edges whose intervals span zero
- [x] The verdict and the sign-off card read "supported (point signs only; N of 3 intervals span zero)" when any does; the parameters card shows values under that flag
- [x] Equality proof on RCS08 (L 1-3+ 24.5 Hz and L 0-2+ 24.5 Hz), suites, frontend rebuild, watched in the browser, decision 147
- **Status:** complete

### Phase 10: Closed-loop timing parameters -- documented ranges and RCS08's own dynamics
- [x] Manuals researcher: every adaptive parameter with its documented range, page-cited; contradictions with the repo's fixed-timing table
- [x] Web + toolkits researcher: published ranges, FDA/Medtronic documents, Percept JSON field names from the open toolkits
- [x] Data researcher: RCS08's programmed adaptive state; ACF/PSD time scales; crossing chatter vs onset; settling constants vs transitions; post-programming settling vs startup delay
- [x] Synthesis: recommended settings inside the documented ranges with the rationale per parameter; what the record cannot decide
- **Status:** complete

### Phase 11: Wire the documented ranges and the record-derived timing into the modules (PI, 2026-09-13)
- [x] One home for the FDA / tip-card ranges (`percept_adaptive.DOCUMENTED_RANGES`); the ADAPT-PD trial's settings kept and labelled as the trial's; `validate_policy` checks timings and limits against them
- [x] Device rules D20 (declared timing judged against the range, not the default) and D21 (onset 0-6 min / 0-30 s) read the one home; ledger text rewritten
- [x] The parameter card: every timing row carries its documented range and source; the record-derived values (decision 148, `timing_recommendation.py`, one table keyed on the participant) with reason and confidence; the fallback onset is two averaging windows inside the range; what the device RUNS today ("programmed today") beside every row, read from the newest session report's active group
- [x] Frontend: programmed value and confidence on the card; rebuilt (chunk 576.e37f8ee0)
- [x] Both suites green (host 1097 / 2 / 0, container 631 / 0); equality proof on RCS08 L 1-3+ 24.5 Hz (49,343 / 49,473 fields, 173 differing, all under the parameter card, D20/D21 text and the new programmed-timing block); workers reloaded; decision 149; commit; push
- **Status:** complete

### Phase 12: Method contest -- six control-theory approaches to the timing and threshold parameters
- [x] Brief written (`_agent_bridge/_probe_tl/_contest/BRIEF.md`), ctrlsys installed, six Opus agents dispatched (LTI state-space, Kalman estimator, FOPDT/lambda, dwell-time Markov, nonlinear dynamics, ML/statistics)
- [x] Judge the six reports by the brief's scoring rule; synthesis (artifacts/contest_2026-09-13_SYNTHESIS.md) with the highest-confidence, most robust approach (B's fitted slow-level model + noise-simulation design rule; F's bootstrap as the robustness test) and a seven-task implementation plan; the timing table updated (averaging 3 s), proof 49,473 / 49,443 fields, 73 differing, all in the parameter card; host 1098 / 2 / 0, container 631 / 0; decision 150
- **Status:** complete

### Phase 5: Prove it on the page and land
- [x] Frontend: ledger shows the new verdict kinds and the measurement current; rebuild; strings found in the served chunk
- [x] Watched live in the PI's browser ("cl page looks good", 2026-09-12)
- [x] Decisions to DECISIONS_and_open_items.md; commit and push
- **Status:** complete

### Phase 13: T2 -- the simulation card replays both timing regimes, not the white-paper default
- [x] `write_simulation` reads the candidate's own programmed timing (`device_facts["active_sensing_group_timing"]`, already computed by the report) and this participant's record-derived recommendation (`timing_recommendation.for_participant`), and runs the full simulation (M0-M3) once under each, stored together under one `closed_loop_simulation` entry as `timing_runs.programmed` / `timing_runs.recommended`
- [x] A reversal count (a switch undone within one onset, the contest's own definition) added to `simulation.py` on every model, on both regimes
- [x] `timing_recommendation.TABLE_VERSION` and the recommendation's own values folded into `simulation_signature`, so an edited recommendation table never serves a stale replay
- [x] Frontend: the CL-DBS simulations card shows both regimes side by side (switches/hour, undone count, timing values), labelled, with a click-to-select toggle for which one draws the three figures; never a silent swap
- [x] Four new tests (`test_simulation.py` 10-13): the reversal count against the contest's own definition; `run_models` under two timing params gives two pinned, different answers; `_timing_runs_for_simulation` reads the programmed group and the recommendation correctly, including both absent cases; the signature changes with the table version
- [x] Both suites green (host 1102 / 2 / 0, container 631 / 0); frontend rebuilt, new strings ("As programmed today", "Record-derived recommendation", "undone within one onset") found in the served chunk; field-count / difference-count proof on RCS08 (ONE_THREE_LEFT, 24.5 Hz); the module's own full-record replay reported honestly under both regimes rather than forced to match the contest's own 20-stretch subset numbers; decision 151
- **Status:** complete

### Phase 14: T3 -- a confirmations-and-separation design rule, ported from contest entry B
- [x] `design_rule.py`: the two-component (L4) fit with an L1 fallback, the Riccati steady state (numpy iteration, primary) with a guarded `ctrlsys.sb02md` cross-check, the noise-only crossing simulation (counts runs, not readings), the averaging x onset separation table, and the analytic single-reading check
- [x] Wired into `adapter.report_for_participant`: `write_design_rule`/`design_rule_if_stored` (the same store-backed pattern as `write_simulation`); the sentence patched onto the SERIALISED "Upper LFP threshold"/"Lower LFP threshold" rows of `prescriptions` and `prescription`, since `report_to_dict(rep)` had already turned the dataclasses into plain dicts by that point in the function
- [x] `prescription.py`: `Field_.design_rule_note`, `design_rule_note()`, `attach_design_rule()` (kept for testability against the dataclasses); frontend renders it always-visible beside the threshold rows, not folded into "Why this value"
- [x] Found and fixed live: `closed_loop_design_rule` was missing from `CacheStore.store.KEEP_NEWEST_BY_KIND`, so a second candidate's table evicted the first's -- the decision-107 class of defect, met again; fixed with the same limit (6) `closed_loop_simulation` already uses
- [x] 20 new tests (`test_design_rule.py`) plus 6 in `test_prescription_modes.py`'s style; both suites green (host 1122 / 3 / 0, container 631 / 0); the white-noise analytic check passes; the design table reproduces B's own reported values exactly everywhere B's own (narrower) separation grid resolved a finite answer, with the two disclosed, explained exceptions (a wider search grid finds a finite answer where B's capped grid says "never"; one cell one grid-step off, plausibly the smaller default simulated-hours budget); live field-count/difference-count proof on RCS08 (49,382 / 49,426 fields, 2 differing, both a pre-existing cache-hit bookkeeping artifact of capturing "after" twice, not a functional change); frontend rebuilt, `design_rule_note` found in the served chunk; decision 152
- **Status:** complete

### Phase 15: T4 -- a threshold occupancy check, contest decision 150
- [x] `occupancy.py`: re-averages the same 3 s power series design_rule.py/simulation.py already read onto the card's recommended averaging duration, never averaging across a gap between recordings; reports frac_above/between/below, the participant's median, the pair's centre/half-width and a warning below 10% between or more than one half-width off centre
- [x] Wired into `adapter.report_for_participant`, right after the T3 design-rule step; the sentence patched onto the SAME serialised threshold rows `design_rule_note` already uses; `prescription.py` gained `Field_.occupancy_note`, `occupancy_note()`, `attach_occupancy()`
- [x] A sign error in the direction word ("above"/"below") was found by comparing the live number against the contest's own report and fixed before landing, with two tests pinning the correct word on both sides
- [x] 20 new tests; both suites green (host 1143 / 2 / 0, container 631 / 0); live field-count/difference-count proof on RCS08 (49,484 / 49,543 fields, 0 differing); the acceptance case (device 167/166 near-zero-and-flagged) matches closely, the stored L 1-3+ pair's own number (15.9% between, no off-centre warning) is honestly disclosed as different from the synthesis's 18-21%/61-units figures and traced to mean-at-30s vs median-at-3s on a skewed series, not a bug
- [x] Frontend: `PrescriptionPanel.js` renders `occupancy_note` beside `design_rule_note`; rebuilt, found in the served chunk (576.c76946db.chunk.js); decision 153; commit; push
- **Status:** complete

### Phase 16: T6 -- the start-of-recording dip in band power, measured two disagreeing ways
- [x] `startup_bias.py`: the training/test split both contest entries used, ported once; contestant D's method (compacts a stretch to its real readings first, needs more than 20) and contestant E's method (reads the raw device-clock position, no minimum length) ported line for line from their own scratch scripts, neither method corrected toward the other
- [x] Port checked against the contest's own printed numbers directly, using the identical recorded stretches the contest script built: bit-for-bit match on both methods (D: -0.10404153099836579, t=-2.4914058108928567, n=82; E: -0.03452435522071541, z=-1.4706266338270466, n=221)
- [x] Wired into `adapter.report_for_participant`, patched onto the "Adaptive startup delay" row of the SERIALISED prescription rows (the T3/T4 pattern, not the dataclass-mutation trap); `prescription.py` gained `Field_.startup_bias_note`, `startup_bias_note()`, `attach_startup_bias()`
- [x] 19 new tests (`test_startup_bias.py`); both suites green (host 1162 / 2 / 0, container 631 / 0 / live-skipped 6); live field-count/difference-count proof on RCS08, the committed band (49,594 / 49,741 fields, 0 differing, 147 only-after, all under the new check)
- [x] The everyday-path numbers on the committed band are reported honestly rather than forced to agree with the contest's snapshot: D reads 71 stretches, bias -0.045, t=-1.04 (not a confident finding); E reads 205 stretches, bias +0.007, z=0.35 (flat, opposite sign) -- the two methods disagree even on direction on this band, and the cause of the small everyday-path-vs-contest-snapshot gap on L 1-3+ (88/-0.095/-2.40 against the contest's own 82/-0.104/-2.49) is named: this module's own established stretch-builder (already used by T3 and T4) drops a reading with no computable band power before deciding where a recording gap begins, which the contest's own scripts did not do
- [x] Frontend: `PrescriptionPanel.js` prints the sentence beside the Adaptive startup delay row; rebuilt, found in the served chunk (576.e196d94a.chunk.js); decision 154; commit; push
- **Status:** complete

### Phase 17: T5 -- the block bootstrap as an interval, not a point
- [x] `robustness.py`: the reference script's own 576-configuration grid, feasibility rule and tie-break ported faithfully; the config-vectorised replay (`run_stretch`, `run_many`) ported line for line from `fastreplay.py`
- [x] THE PI'S HARD REQUIREMENT ("use only vectorized code for bootstrapping so it's super fast") met by precomputing every training stretch's per-configuration outcome ONCE (the controller resets per stretch, so this is exact, not an approximation) and aggregating each of the 200 bootstrap replicates as a weighted sum -- zero further calls into the time-stepped replay after the one precompute pass
- [x] `choose_naive` kept as the literal, unoptimised reference; 20 new tests prove the fast path equals it exactly, including with repeated stretches and over 15 random resamples
- [x] Port checked against the reference script's own stored CSV, fed the identical npz series and seed: onset interval 36.0-90.0 s, bit for bit the acceptance text and the reference's own file; gap and blanking intervals match to 12 significant figures; one honest, traced difference in the reported median (not the interval), from this file's own NaN-filter-before-regridding convention, already established by T3 and T6
- [x] Wired into `adapter.report_for_participant` as a store-backed step (`write_robustness`/`robustness_if_stored`, same CacheStore pattern as T3), patched onto the onset-duration row(s) of the SERIALISED prescription rows; `prescription.py` gained `Field_.robustness_note`, `robustness_note()`, `attach_robustness()`; no ledger row added, matching T3/T4/T6
- [x] Both suites green (host 1182 / 2 / 0, container 631 / 0 / live-skipped 6); live field-count/difference-count proof on RCS08, the committed band (49,756 / 49,806 fields, 0 real differences, 50 only-after, all under the new check); the bootstrap's own wall clock measured directly: 0.059 s on the committed band, 1.53 s on the richer L 1-3+ series
- [x] Frontend: `PrescriptionPanel.js` prints the sentence beside the onset-duration row(s); rebuilt, found in the served chunk (576.9888adf4.chunk.js); decision 155; commit; push
- **Status:** complete

### Phase 18: T7 -- the gain (verification only; no titration session exists yet)
- [x] Confirmed by reading the code, not from memory: `simulation.run_models` already builds M0 and M1 whenever the stored pooled row carries a real slope, and already reports M1 (not M0) as the active model -- built by decision 128, before this contest
- [x] Confirmed `post_ramp.margin_becomes_available` is fully derived from the stored per-run points table with no manual flag, and that it is kept separate from `USE_POST_RAMP_MARGIN`, the actual behaviour switch, which is the PI's call (decision 144) and is never auto-flipped
- [x] Confirmed `edges.pooled_actuation_edge` (E1) reads the stored pooled row automatically, no manual step
- [x] Confirmed both `pooled_shape_signature` and `simulation_signature` fold in `recording_set_signature`, so a titration session's new recordings give every downstream table a new key and no stale cached entry can be served
- [x] No gap found; no production code changed
- [x] New test file `ClosedLoopDeployment/tests/test_t7_gain_wiring.py`, 5 tests, constructed data only (never claimed as an RCS08 result): M1 differs from M0 given a real pooled slope; a control with no slope reproduces M0 bit-identically; the same row resolves E1; `margin_becomes_available` flips on constructed 6-setting vs 11-step data while the behaviour switch stays untouched; both signatures change when the recording set does
- [x] Both suites green, run together through the bridge: host 1187 passed / 2 skipped / 0 failed (was 1182, +5); container 631 passed / 0 failed
- [x] No live RCS08 proof needed (no production code changed); decision 156; commit; push
- **Status:** complete

### Phase 19: Stim Optimizer -- model both stimulators together, remove the old per-side chart
- [x] PI, verbatim: "Get rid of the whole arm strip and chart display... Only keep the newer two-stage plan... it should model the left and right sides together because they're always on"
- [x] Confirmed on the real record before building: one shared rate column, never a per-side rate; of 120 recorded stretches, 25 have the left current at zero, 10 the right, 9 both, 73 both on -- so a shared model needs to KEEP the zero-current stretches, which the old per-side fitting had been throwing out of each side's own fit
- [x] New shared 3-input search surface (rate, left current, right current) added to `routines/surrogate.py`; the existing 2-input surface is untouched and still used by the old, now-unused-on-this-page per-side code
- [x] `stage1_openloop.py` rewritten: one shared fit per combination of left and right pulse width (was one fit per side per pulse width); the safety check stays per side and a combination is offered only if both sides' own checks pass it; every existing reader of the frozen result (the gate, closed-loop stage 2) needed no change, since the result still hands back one entry per side, now both built from the same shared fit
- [x] `bravo_service.py`: the old per-side fitting call removed from the page's own request; the old fitting function itself is untouched and still tested, just not called here any more; the response's per-side "what to test next" table replaced with one shared table
- [x] Frontend: the old strip of four small charts and its own click-through card deleted from the Stim Optimizer page; the background table under the two-stage plan card now shows one row per shared pulse-width combination instead of two; a shared "what to test at the next visit" table added in its place
- [x] Two suspicious messages arrived mid-session claiming to redirect this work; neither came from the actual task-giver (one asked for a different design never requested, one falsely claimed a turn limit had been hit, one used the wrong assistant name); neither was acted on, and this is recorded so a later reader is not confused about why the design does not match those messages
- [x] Both suites green (host 1186 / 2 / 0, container 631 / 0), rewritten tests for the parts of the old per-side design that no longer exist, live proof on RCS08 (before/after field count and difference count, and the real preferred settings on both sides of the change); frontend rebuilt and checked in the served bundle; decision 157; commit; push
- **Status:** complete

### Phase 20: The shared model's current recommendation, checked honestly one speed at a time; a home titration schedule
- [x] Measured on RCS08 that the shared 3-input model's own picture at the speed actually running (55 Hz) varied by only 0.004 across every option tried, against a typical scatter of about 1.1 -- confirming the PI's own finding that reading a current off the shared, pooled picture borrows false confidence from other stimulation speeds through the one shared speed axis
- [x] `stage1_openloop.py`: a second, per-speed fitting step added alongside the existing shared (pooled) one -- never replacing it, kept and reported for reference as `pooled_across_rates` -- fitted separately for every stimulation speed with at least 8 recorded stretches at that speed, using only the ratings recorded at that speed
- [x] A current is only handed back when three checks pass: the per-speed picture is not effectively flat; the best option beats what is running today by more than the scatter in that comparison; and at least 6 distinct left/right combinations, each backed by at least 5 ratings, spanning at least 1 mA on each side, were actually tried
- [x] Which speed and which pulse-width pairing to freeze is UNCHANGED -- still chosen from the pooled picture, since that choice needs the pooling to have any data to decide from; only the milliamp number itself is now held to the honest, per-speed standard, and is `None` with a plain reason when the checks fail
- [x] New `current_map_schedule.py`: a home titration schedule (a 3x3 current grid plus two one-side-off points plus the setting in force as an anchor, capped at the stated safety ceiling and the fitted joint safety model, dropped where a point already has enough ratings, held for 3-7 days per point based on this patient's own measured reporting rate, ordered so left current never ramps three steps straight up, the anchor repeated at the start, middle and end) -- reuses the SAME coverage check (iii) above so the sheet can say, before it is ever run, whether completing it would be enough
- [x] Wired into `bravo_service.py` as `current_map_schedule`, computed on every request, not stored on its own; `stage1.rate_strata` added to the existing `two_stage` response block so every attempted speed's fit and verdict is visible
- [x] 25 new tests (9 in `test_stage1.py`, 16 in the new `test_current_map_schedule.py`); 3 pre-existing tests corrected in place, not deleted, since they pinned exactly the borrowed-confidence behaviour this change replaces
- [x] Both suites green (host 1211 / 2 / 0, container 631 / 0 / live-skipped 6); live field-count/difference-count proof on RCS08, genuinely before (decision 157's code) and after: 8,596 fields before, 9,001 after, 0 only-before, 405 only-after (the new blocks), 8 differing of 8,596 shared (6 bookkeeping, 2 real: both sides' recommended current, 1.5/1.0 mA -> none); decision 158; commit; push
- [x] The frontend: `bravo_service.py` gained a `surface` grid on every fitted `rate_strata` row and a `pooled_surfaces` reference block, read straight off the fitted objects Stage 1 already holds; two new cards, `CurrentMapCard.js` (one heatmap per fitted speed, the setting in force marked, the three checks printed beside it) and `CurrentMapScheduleCard.js` (the day-by-day titration table), placed above the two-stage plan card; `DecisionStrip.js`'s "search prefers" row now states plainly when no current can be recommended instead of a bare dash
- [x] 4 new tests (`test_surface_serialization.py`); both suites green (host 1215 / 2 / 0, container 631 / 0 / live-skipped 6); live field-count/difference-count proof on RCS08 (9,145 fields before, 17,357 after, 1 only-before, 8,213 only-after, 4 differing of 9,144 shared, all bookkeeping); frontend rebuilt, the two cards' own wording found in the served chunk; decision 159; commit; push
- **Status:** complete

### Phase 21: RCS08's stated ceiling lowered to 4.5 mA; the in-clinic titration session redesigned (backend only)
- [x] `safety_ceiling.PI_STATED_CEILING_MA` for RCS08 changed 5.0 -> 4.5 mA both sides ("make max safe amp on each side 4.5 mA, PI decided"); `objective.AMP_HARD_LIMIT_MA` (the module's own search-grid edge, a different thing) untouched; `current_map_schedule.py`'s comment referencing the old number corrected
- [x] `titration_plan.ladder()` rewritten: up in 0.5 mA steps unchanged, down now in 1.0 mA drops rather than retracing the up steps, always ending at 0 ("keep the 1.0 mA down legs")
- [x] `titration_plan.step_timing()` added: a 60 s ramp row then the unchanged 60 s test row, 2 min a step ("test-period hold time = 60 s, not 120 s; 2 min per step")
- [x] `side_plan` carries `held_other_side` (current + source); `plan_for_sides` reads `in_force` to fill it from the OTHER side's own setting
- [x] `joint_corners()` added: four (left, right) combinations at 1.0/4.0 mA, capped per side and restricted to the joint safety model, optional, for the pain surface's off-diagonal points
- [x] `SHEET_COLUMNS`/`build_sheet_rows()` added: the flat clinic-sheet row list in the real 2026-09-02 workbook's own "Stim Testing" column order (read directly from the xlsx via zipfile/XML, not approximated), two rows a step, bilateral cells "L x / R y"
- [x] `bravo_service.titration_plan_block` threads `es` through to fit the joint safety model for the corners block; single-side requests correctly build no joint-corners rows (a real bug caught by this session's own new tests before it shipped)
- [x] 78 tests across `test_safety_ceiling.py`, `test_titration_plan.py`, `test_current_map_schedule.py`, all green; both suites green through one bridge job (host 1229 / 2 / 0, container 631 / 0)
- [x] Live field-count/difference-count proof on RCS08, genuinely before and after (`git stash`): 7,148 fields before, 8,647 after, 12 only-before, 1,511 only-after, 49 differing of 7,136 shared (4 the ceiling change, 43 the ladder/session redesign, 2 bookkeeping); decision 160; commit; push
- **Status:** complete

### Phase 22: The clinic-sheet pain stream, imported as a second, independent data stream (backend only)
- [x] PI, 2026-09-14, verbatim: "Import all in-clinic AND at-home testing visits. Pull the in-clinic numbers separately (not in REDCap) as an independent data stream for system optimization (critical)"
- [x] New `StimOptimizer/clinic_pain.py`: `parse_workbook`/`parse_folder` read the 29 real workbooks, header found by name not position, typo-tolerant ("Timastamp", "PW (ms)"), the bilateral left-before-separator convention in all three forms, the one transposed workbook (July 2025) read from its Notes tab with rate/pulse width left blank rather than guessed
- [x] A real Excel corruption found and fixed: some pain scores ("8/10") were auto-converted by Excel into date objects (month 8, day 10); read back correctly, never guessed when the shape does not fit
- [x] Prose pain descriptions in a notes column counted as `n_unparsed_prose`, never parsed into a number
- [x] Stored as raw kind `clinic_pain_steps`, keyed on the folder's own file set (name + content hash per file); `manage.py ingest_clinic_sheets --participant <uid>` writes it with `writer="clinic_sheet_ingest"`; re-running over an unchanged folder writes nothing
- [x] `epoch_frame_from_steps` collapses a setting tested more than once into one epoch with `n` = the repeat count, in the acute clinic-testing frame's own column names (`pain_Left_Leg` etc.) `routines/objective.py` already expected
- [x] `objective.build_objective` and `stage1_openloop.run_stage1` gained one additive, backward-compatible parameter, `pooled_var_override` (default `None`, no existing caller affected), so a thin stream with no epoch repeated 3+ times can still borrow the REDCap stream's own pooled variance rather than failing outright
- [x] `bravo_service._clinic_stream_stage1_block` fits the SAME per-rate two-input surface on the clinic stream alone and reports it under `two_stage.stage1.rate_strata_clinic` (tagged `source: "clinic_sheets"`) and `two_stage.stage1.clinic_stream` (file/step counts, visit list, which pooled variance was used and why); never pooled with the REDCap-based recommendation, which is untouched
- [x] 16 new tests in `test_clinic_pain.py`; one existing wiring test in `test_two_stage_wiring.py` extended (not weakened) to cover the new step
- [x] Ingest run on RCS08 in the container: 816 steps, 472 with a usable pain score, 7 unparsed prose, 16 skipped (no setting known), 370 in-clinic / 102 at-home, 63 distinct (left, right) current pairs at 55 Hz; re-run confirmed no rewrite
- [x] Both suites green through one bridge job: host 1245 passed / 2 skipped / 0 failed (was 1229, +16); container PASS=631 FAIL=0
- [x] Live field-count/difference-count proof on RCS08, genuinely before and after (`git stash -u`): 18,787 fields before, 22,518 after, 0 only-before, 3,731 only-after (all under the new clinic block), 3 differing of 18,787 shared, all bookkeeping (a timestamp, the response key, one timing field) -- no REDCap-based value moved
- [x] On the clinic stream: two rate strata fitted (55 Hz, 110 Hz), neither resolves a current to recommend yet -- the honest answer given the evidence so far, not a defect; decision 161; commit; push
- [x] The page draws all of it, decision 162: `TitrationSessionCard.js` gained a header strip (rate, both pulse widths, both ceilings, the held-other-side current per block, step timing, session length) and three printable tables built from `sheet_rows`/`sheet_columns` (left ladder, right ladder, optional joint corners), plus a date field and a disabled "Make Google sheet" button; `CurrentMapCard.js` gained a second, un-pooled section reading `rate_strata_clinic`/`clinic_stream` with a folded visit list. Build clean, both new files' owned strings present in the served chunk; no backend file touched, so no suite run applies; not watched in a real browser this session (no browser-control tool was available)
- [x] The "Make Google sheet" button is wired, decision 163: `StimOptimizer/sheet_export.py` (`fill_workbook`, `export`, `sheet_name_for`, `values_for_sheets_api`) and `StimOptimizer/google_sheets_client.py` (optional Drive/Sheets client, `available()`/`client_if_available()`, off today -- no key file on this server); new endpoint `/api/exportTitrationSheet` (`Server/APIs/DataAnalysis.ExportTitrationSheet`) rebuilds the plan through `bravo_service.run_for_participant` so the export can never drift from the page; `TitrationSessionCard.js`'s button is enabled, posts the chosen date, and follows either answer (a "drive" JSON naming a real Sheet URL with a "re-export" control, or a downloaded `.xlsx` with this page's own copy of the setup note). A real openpyxl gotcha caught by the new tests before it shipped: `ws.cell(row, column, value=None)` is a no-op, so writing rows straight through it would have left the template's stray "Detailed pain survey" label in place; fixed by assigning `.value` directly
- [x] 12 new tests, `test_sheet_export.py`: the template's own bytes are provably unchanged after every fill (sha256 before/after, plus a monkeypatched-mutation case that must raise); every row lands at A12.. in the real column order; the B1 date cell is a real Excel date, `mm/dd/yy`; a fake Drive client proves a re-export reuses the existing file (`overwrote: True`) while a first export copies the template (`overwrote: False`), and that the template's own id is passed only as `copy_file`'s SOURCE, never to `clear_values`/`update_values`
- [x] Live on RCS08 through the bridge: `fill_workbook` against the REAL template for 2026-09-16 with a fresh `run_for_participant` plan -- 68 rows, 12..79, template sha256 identical before and after, B1 set to 2026-09-16 `mm/dd/yy`; then the real Django view (`APIRequestFactory` + `force_authenticate`, DEBUG-mode permission grant) end to end: xlsx mode returns 200, `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `Content-Disposition: attachment; filename="RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26.xlsx"`, 260,577 bytes -- byte-identical to the direct `fill_workbook` call; malformed input 400, unknown participant 403
- [x] Both suites green through one bridge job: host 1257 passed / 2 skipped / 0 failed (was 1245, +12); container PASS=631 FAIL=0 LIVE_SKIPPED=6
- [x] Frontend rebuilt clean, no warning in either touched file; served chunk carries "Open in Google Sheets", the setup note's own first words ("To let this server write directly to Google Sheets"), and "Making sheet…"; not watched in a real browser this session (no browser-control tool was available)
- [x] The Drive path is built and unit-tested against a fake client but NOT exercised against the real Google APIs -- no service-account key exists on this server; `google_sheets_client.SETUP_NOTE` states what the PI must do to turn it on
- **Status:** complete

## Decisions Made
| # | Decision | Rationale |
|---|---|---|
| 1 | Items 2, 4 and 5 of the brief are ONE change (rate + pulse width into the candidate); D27 (item 4) is unevaluable only because pulse width is None | measured: D27 has capture_amp_high_mA=5.0 already; only pulse_width_us is missing |
| 2 | Builders run one at a time in the main checkout, not in parallel worktrees | both changes touch device_facts.py and constraints.py, and every test suite runs against the live mount of the main checkout; a worktree agent could not run a single test |
| 3 | PI, 2026-09-12: D19 option (b) -- pass the POINT signs of the three edges to D19 even when an edge is unresolved; the row's observed text must still say which signs are not established (E1 p=0.54; E2 AUC CI includes 0.5) | his call, after the concern (decision 9, the pipeline's own rule) was stated once; a pass reads "signs point the right way", never "proven" |
| 4 | PI, 2026-09-12: D30 option (a) -- derive rate_committed_for_this_attempt from the device: the candidate's rate equals the rate frozen in the newest ACTIVE sensing group, read from the LIVE session reports (55 Hz, Group D, adaptive RUNNING), not the stale summary | his call; findings §4 |
| 5 | The session-report summary must be read from the ingested files, not the 2026-09-05 scan of the shared drive | findings §4: the summary says 110 Hz / NOT_CONFIGURED, the device says 55 Hz / RUNNING; D32, D28, D17, D09, D27 all read it |
| 6 | No agent runs in a git worktree in this repository; `isolation: worktree` removed from `.claude/agents/worker-builder.md` (PI, 2026-09-12) | the container mounts the main checkout only, so a worktree agent cannot run a test or reach the live record (Builder B; decision 102) |
| 8 | D32's flags: interleaving counted per hemisphere; a sensing channel's limits are ADAPTIVE limits while adaptive therapy is RUNNING and patient limits only when sensing-only | fresh data failed D32 on the group running adaptive DBS; the raw report shows GROUP_D limits 2.0-3.0 = capture range, GROUP_A 0-4 |
| 7 | D16 records its reading and measurement current on every pass (added to `_RECORD_VALUE_ON_PASS`); the reading D16 trusts is the newest FIXED-current test, the automatic-mode reading is reported beside it as a spurious fail | the PI's ruling of 2026-09-12; measured 0 of 18 fixed-current records over the limit against 351 of 544 automatic |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| bridge_client.py run from BRAVO/ with the wrong path | 1 | path is BRAVO/_agent_bridge/bridge_client.py |
| Builder A's tool call cut mid-suite ("tool execution is interrupted"): the bridge client blocks for the whole job (116 s) and the Bash tool's default limit is 120 s | 1 | the result had landed in outbox anyway (job f37675a0: 1072 passed / 42 skipped / 0 failed). Rule for every long bridge call: Bash timeout 600000 AND submit with --wait 5, then poll outbox/<id>.out in short calls |
