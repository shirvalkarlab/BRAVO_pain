# Task Plan: Make Closed-Loop Work
## Goal
The Closed-Loop Deployment page's device-rule ledger stops blocking the verdict on rows whose only
problem is that the module never handed the rule the value the device already records; every row
that still blocks does so for a reason the PI has read and agreed with.

## Next Step
All seven phases landed (f2bdb7a5 layout, 8882c92c speed, e5531f43 Closed-Loop, b7910fdb
Biomarkers, 48bf7abf Stim Optimizer + C4). Three pages smoke-tested in the PI's browser. Open on
the PI: the four number-moving changes (decisions 141-143) -- the California day (B1), the 20 s
post-ramp margin (hazard 1, which now blocks D19 on L 1-3+ 24.5 Hz), the Right pulse width (S1),
and the stream safety anchors (S8, shipped OFF). Awaiting the D19 before/after measurement, then
the plain-language summary for him.

## Current Phase
Phase 7

phases: 7/7 complete

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

### Phase 5: Prove it on the page and land
- [x] Frontend: ledger shows the new verdict kinds and the measurement current; rebuild; strings found in the served chunk
- [x] Watched live in the PI's browser ("cl page looks good", 2026-09-12)
- [x] Decisions to DECISIONS_and_open_items.md; commit and push
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
