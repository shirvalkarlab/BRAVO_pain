# Task Plan: Make Closed-Loop Work
## Goal
The Closed-Loop Deployment page's device-rule ledger stops blocking the verdict on rows whose only
problem is that the module never handed the rule the value the device already records; every row
that still blocks does so for a reason the PI has read and agreed with.

## Next Step
Nothing queued. For the PI: T2 and T3 of the contest's implementation plan are both built; T4
(threshold occupancy check), T5 (the block bootstrap as an interval on the card), T6 (the startup
dip measured in the module) and T7 (the titration session supplying the gain, decision 146, open
item 30) remain, plus the threshold re-centring / separation itself (decision 139's capture
question).

## Current Phase
Phase 14

phases: 14/14 complete

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
