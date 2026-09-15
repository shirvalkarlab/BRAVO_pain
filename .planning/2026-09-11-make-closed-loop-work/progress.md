# Progress: Make Closed-Loop Work

## Session 2026-09-12
- Plan opened. Brief: five items on the ledger's blocked rows (D16 impedance, D31 x3, D27).
- Measured the live ledger (findings §1), the impedance current (§2), the newest epoch (§3).
- Probes: `_agent_bridge/_probe_tl/probe_ledger_rows.py` (output in `ledger_rows.txt`),
  `probe_imp_amplitude.py`, `probe_edges_settings.py`, `probe_d16_d19_inputs.py`.
- PI decided: D19 option (b), D30 option (a). Read the raw session reports (findings §4): active
  Group D at 55 Hz, adaptive RUNNING; the committed summary is stale (110 Hz / NOT_CONFIGURED).
- Builder A dispatched for the rate / pulse-width wiring (items 2+4+5); running.
- PI: go ahead with B and C after A lands.
- Builder A interrupted mid-suite by the 120 s tool limit; host suite had passed (1072/42/0, job f37675a0). Resumed with the submit-then-poll recipe.
- Builder A stopped at its turn cap after the live ledger re-run; finished by hand. Host suite
  1072 / 42 / 0 (jobs f37675a0 and, after the provenance edit, f892b266); container 631 / 0
  (job 7adf5b82). Live ledger: 4 unknown -> 2 (D19, D30 left); D27 passes, D31 recorded
  "rate 55.0 Hz and pulse width 100.0 us", D44 satisfied. Field comparison (ledger rows keyed
  by rule): 58,546 in common, 1 differing (the summary line), 24 only-before (D27/D31/D44's
  unknown rows), 12 only-after (D31 recorded; device_facts rate_hz 55 / pulse_width_us 100 with
  provenance "exposure epoch 123, open-ended"). Probes: probe_report_capture.py,
  probe_report_compare.py, report_before_A.pkl / report_after_A.pkl.
- Builder B ran in a worktree (agent definition had `isolation: worktree`); its patch (299 lines,
  device_facts.py / constraints.py / tests/test_core.py) applied cleanly to the main checkout; the
  worktree and its branch removed; `isolation: worktree` removed from the agent definition at the
  PI's direction, reason in `.claude/agents/README_no_worktrees.md`. Two fixes on top of B: epoch
  seconds printed as UTC dates; the recorded-rules assertion in test_constraints.py now includes D16.
- B proven live on RCS08 (jobs 26c963c1, a1b7aa88): ledger 1 blocking -> 0 blocking, 2 unknown
  (D19, D30). D16 recorded_value: "impedance 7286.0 ohms ... fixed measurement current of 0.4 mA,
  recorded 2026-09-02 20:25 UTC. The newest impedance test of all, 2026-09-11 15:30 UTC, used the
  automatic low-current mode and read 10261.0 ohms -- ruled a spurious fail". Comparison A -> B:
  58,550 in common, 3 differing (summary line; impedance_ohms 10261 -> 7286; its provenance),
  8 only-before (D16's failed row), 14 only-after (D16 recorded; four new impedance facts + provenance).
  Host 1078 / 42 / 0; container 631 / 0. Verdict still `blocked`: device_eligible False (2 unknowns)
  and the pipeline's D26 blockers (inverted capture; separation 0.07 SD) -- for the PI.
- Committed A+B as b2f03e11 at the PI's direction ("commit A and B now"), pushed; C1 running in the main checkout via the general-purpose agent.
- C1 built in the main checkout (uncommitted, 2026-09-12): D19 passes on POINT signs with `_established` flags,
  interval and p beside each sign (`pipeline._facts_for`; observer names any unestablished sign); D30 derived
  live from the device's newest active sensing group (`device_facts.active_sensing_group_facts`, memo keyed on
  participant + newest session-report uid + hash; `adapter.rate_commitment_from_active_group`). D19 and D30
  added to `_RECORD_VALUE_ON_PASS` so the pass shows its caveat/group. 21 new tests
  (`tests/test_d19_point_signs_and_d30_active_group.py`), one renamed in test_core.py, one set updated in
  test_constraints.py. Host 1098 / 42 / 0 (was 1078); container 631 / 0. Live RCS08 ZERO_TWO_LEFT 24.5 Hz:
  ledger "0 blocking, 2 unknown of 51" -> "eligible (51 rules checked, 30 advisory)"; D19 recorded_value with
  both point signs flagged NOT established (E1 interval -18.6..9.73 p 0.539; E2 -0.0235..0.195 p 0.12); D30
  recorded_value, candidate 55 Hz == GROUP_D 55 Hz, committed True. verdict `blocked` -> `unsupported`,
  licensed False -> False, device_eligible False -> True; D26 blockers unchanged. Fields 58,564 -> 58,578,
  58,548 in common, 16 only-before (the two unknown rows), 30 only-after (two recorded rows, 8 device facts,
  6 provenance), 24 differing: 4 verdict/eligibility fields + 20 timing (14 `_seconds`, 6 `.seconds`).
- C1 reviewed; two fixes on top (group name printed without the export's enum prefix, "GROUP_D";
  the compare script counts `.seconds` fields as timings). Re-run: host 1098 / 42 / 0, container
  631 / 0; live: "eligible (51 rules checked, 30 advisory)", verdict blocked -> unsupported,
  device_eligible True, 58,548 fields in common, 4 non-timing differing (verdict, device_eligible,
  eligible, summary). Committed a13bfe9b, pushed.
- C2 landed: summary rebuilt from the 572 ingested reports (108.6 s; already_current 0.07 s),
  stored as raw kind session_report_summary keyed on the file set, resolver current/stale/committed,
  background launcher, manage.py rebuild_session_report_summary on the daily pass. Fresh data failed
  D32 (interleaving pooled across sides; adaptive limits read as patient limits) -- fixed in the
  scanner, five tests, rule v3. Live vs C1: 0 ledger rows moved, verdict unsupported both times,
  27 device-fact/provenance differences (capture 3.0-5.0 -> 2.0-3.0 mA at 55 Hz). Host 1120 / 42 / 0,
  container 631 / 0. Committed 56d04cfc, pushed.
- PI: run the suites in parallel from now on. Added BRAVO/_agent_bridge/run_both_suites.sh (one bridge job, both suites concurrently): 134 s wall against ~199 s sequential; host 1120/42/0, container 631/0. Recorded in memory.
- Test audit swarm launched (4 read-only investigators, one per module group). CacheStore+DecodeCommon in: 112 tests, 103 KEEP, 1 delete (duplicate), 4 rewrite; report artifacts/test_audit_2026-09-12_CacheStore_DecodeCommon.md.
- ClosedLoop audit in: 487 tests, 443 KEEP, 20 delete, 18 rewrite (artifacts/test_audit_2026-09-12_ClosedLoopDeployment.md). Its finding 1 fixed at once: test_pocket_adaptor_stays_unknown... could start a real summary rebuild from the live record once the stored summary went stale (decision-96 class, my C2 regression); now runs on a temp store with the launcher off and an assertion that fires if it spawns; test_core.py 67 passed; production store unchanged (2 files, no marker). Uncommitted.
- Biomarkers audit in: 519 tests, 448 KEEP, 26 delete, 29 rewrite (artifacts/test_audit_2026-09-12_Biomarkers.md); 7 tests test a copy of themselves; test_process_redcap.py's test is named main and never ran.
- StimOptimizer audit in: 501 tests, 200 KEEP, 75 stand-alone delete + 211 in the unwired two-stage/PyTorch subsystem, 18 rewrite. Synthesis artifacts/test_audit_2026-09-12_SUMMARY.md. Committed with the test_core fix and run_both_suites.sh, pushed.
- Deleters: CacheStore 1/1 done; StimOptimizer 75/75 done (test_separation_span.py removed; 5 helpers/imports with them); five conditional ones (3 stopping-rule, 2 ramp-clip) RESTORED from HEAD pending the PI's design call. Two-stage wiring builder dispatched (TwoStage flag, two_stage response key, non-torch backend).
- ClosedLoop deleter: 19/20 done (2 registry.py tests held back: the audit tied them to a decision on registry.py itself, 0 importers, decision 109).
- Biomarkers deleter: 24/26 done (2 held: the audit's own conditions). All deleters done: 114 deleted, 9 held. Container suite after deletions: PASS=606 FAIL=0 (631 - 25, exact). Host suite waits for the two-stage wiring builder (editing StimOptimizer production files).
- Two-stage wiring landed: TwoStage flag -> two_stage block (Stage 1 frozen config, gate's four
  conditions, Stage 2 or refusal), non-torch backend, flag in the response key. RCS08: Stage 1
  prefers 40 Hz/100 us both sides (unresolved; gain +0.19/+0.03 vs SD 1.17/0.61); gate refuses
  3 of 4 (40 < 55 Hz floor; unresolved; no LFP evidence at 40 Hz). No page shows it. Flag-off
  8,387 fields, 0 scientific differences.
- Both suites side by side: host 1038 / 42 / 0 (exact arithmetic), container 606 / 0.
  Committed 7d51f098 (deletions, 24 files, -1623 lines) and 5ecd6c62 (wiring); pushed.
- Frontend two-stage card built: TwoStagePlanCard.js + useTwoStagePlan.js (slot stimOptimizer/twoStage), second fetch with TwoStage:true after the main response; title in chunk 678.250f9c08; 0 warnings in touched files; not watched in a browser. Waiting on the adaptive-envelope backend builder.
- Nine held tests deleted at the PI's direction (fb04842b; host 1031/42/0, container 604/0).
- Adaptive envelope (PI: "don't recommend settings adaptive cannot use unless there is a
  scientific or physiological reason"): routines/adaptive_envelope.py masks rate < 55 Hz before
  Stage 1 scores; exclusions listed; override keys lift it with a stated reason. RCS08: both
  sides now freeze 55 Hz/100 us; gate refuses on 1 of 4 (unresolved: 55 Hz is the incumbent)
  instead of 3; band-response check PASSES at 55 Hz (12 of 18 bands, best 23.5 Hz). Flag-off
  8,387 fields, 0 scientific differences. Frontend card on the Stim Optimizer page committed
  with it. Host 1049/42/0 (1031 + 18: 16 functions, one parametrised x3), container 604/0.
  Committed 2c2100dd, pushed. Not watched in a browser.
- Decisions 132-139 written into DECISIONS_and_open_items.md (139 = D26 reads the pooled slope and
  warns, not blocks; PI: "b and c"); D26 builder running. Design reviewer running (Stim Optimizer
  page redesign proposal, existing L 0⁻2⁺ contact convention, all code edits as patch files).
- Suite timing measured (1,584 tests serial under pytest, 391 s): one 53 s live-store test,
  ~110 s in Stage 1/2 tests refitting the same model per test, ~85 s in RCS08-payload tests in
  test_analytics.py, ~30 s in the new two-stage tests. PI: do 1-4 after D26 lands -- (1) fit-once
  module fixtures, (2) pytest-xdist in the container with a store marker, (3) `live` marker for
  record-reading tests, off the routine run, (4) cached noise references. QUEUED behind D26.
- D26 landed (0e87229a, pushed, workers reloaded): the two capture checks read the pooled slope
  and warn (verdict_detail.warnings); CORRECTION -- L 0-2+ 24.5 Hz has NO stored pooled slope
  (5 points, 1 visit), so both verdicts read "not assessed"; the -4.45/mA quoted earlier was the
  historical setting-epoch estimate. Blockers 2 -> 0, warnings 0 -> 2, verdict unsupported both
  times. Page: warn box "WARNINGS THAT CHANGE NO VERDICT" (chunk 554.2758ad74). Host 1058/42/0,
  container 604/0. Decision 139 updated with the numbers. Both agents had been cut off by an API
  certificate error and were resumed; nothing lost.
- Suite speed-up builder dispatched (steps 1-4). Design reviewer resumed.
- PI watched the Closed-Loop page: "cl page looks good". Phase 5 complete.
- Suite speed-ups landed (0ad5870a, pushed): routine run 179 s -> 29-31 s wall; fit-once fixtures;
  xdist -n 8 with 2 BLAS threads per worker (8 workers x 16 cores had made it SLOWER); `store` and
  `live` markers; six live Biomarkers tests on the daily pass via run_both_suites.sh --live (54 s);
  two order dependences fixed at the root; step 4 (cached noise reference) not done -- the only way
  was to compare against a stored file, a weakening. Host 1058/42/0, container 598 + 6 live = 604.
- Redesign proposal delivered: artifacts/design_2026-09-12_stim_optimizer_page_redesign.md, canvas
  https://claude.ai/code/artifact/af01c390-9ace-463d-a7e8-bee167546df2, four phase patch dirs.
  3,095 words on screen today -> ~950 open after all phases. Backend finding: Stage 1 reads
  pw_us_Left for both sides (Right is 150 us). Awaiting the PI's phase choice.
- Redesign phases 1-4 applied at the PI's direction, committed 6e5b55c0, pushed, workers reloaded; host 1073/42/0, container 598+6; chunk 183.8b78d2d0. Not watched in a browser.
- PI (away 3-4 h, autonomous): (1) speed up the Stim Optimizer load; (2) then code-review the three modules and auto-implement. Phases 6-7 added. Frontend layout-fix builder still running.
- Layout fix watched live in the PI's Chrome (every open section, no overlaps), committed f2bdb7a5,
  pushed. Residual NOT fixed: inside the model-surfaces fold the server-drawn figure's italic caption
  clips at the right edge (routines/plots.py, PI's figure conventions -- noted for him). The redesign
  artifacts and this plan directory were untracked until this commit; now tracked.
- Phase 6 (Stim Optimizer speed, builder): PROFILED FIRST (probe_so_profile.py, module override
  pointed at a scratch store so the response is a genuine fresh build, inputs from production):
  73.3 s under cProfile with TwoStage. The loading line blames the arm fits; the profile says the
  closed-loop readiness screen (live_evidence) is 38.5 s, run again pinned inside two-stage 7.7 s,
  the four arm fits 18.2 s. Inside: sklearn GP fits 22.9 s, ALL in cho_solve on 54-69 row matrices
  (OpenBLAS at 16 threads; 1 thread gives 0.26-0.32 s per arm against 3.9-4.7 s, 12 result groups
  bit-identical); strftime of the era month per TILE row 8.5 s; Timestamp-object epoch lookup
  6.1 s; patsy rebuilding the design matrix per band 10.4 s of 19.4 s in assess_response. No GPU
  (no nvidia-smi, no /dev/dri, no torch). Landed: BLAS cap around the request (env
  STIM_OPTIMIZER_BLAS_THREADS), int64 epoch lookup, era per epoch, design-matrix cache per cell
  (USE_DESIGN_CACHE switch), evidence inputs built once for readiness + two-stage, per-channel
  preparation shared in build_all. Proofs: 304,488 tile lookups 0 differing; 900 band fits x 19
  fields = 17,100 compared 0 differing; whole response 22,398 fields, 0 only-either-side, 3
  differing = response key + 2 timing fields. 73.3 s -> 19.7 s profiled, 15.1 s real (TwoStage).
  Old-code test found a real defect the old lookup had with a MISSING tile time (neighbour
  misplaced; none on the live record). A/B alternating rounds running (old code from git HEAD in
  _probe_tl/_so_old). Tests: 11 new in test_request_speed_equalities.py; 3 stubs given **kw.
- Phase 7 reviews landed: artifacts/review_2026-09-12_ClosedLoopDeployment.md (0 critical, 1 high
  C1: the page always sends Hemisphere "Left", so a right-side band is judged on the left lead and
  stimulator; 5 medium, 6 low; hazards 2 and 4 confirmed, 1 partly, 3 in Stim Optimizer) and
  artifacts/review_2026-09-12_Biomarkers.md (2 high: B1 the power-domain "same day" join uses the
  UTC date, 193 of 678 ratings move a day; B2 a failed availability build memoised as "no
  recordings"; 4 medium, 6 low). Builders dispatched: Closed-Loop (C1-C3, C5-C7, C9-C12, hazard 1;
  C4 deferred until the Stim Optimizer builder is off its files) and Biomarkers (B1-B7, B9-B11;
  B8 and B12 left for the PI). Phase 6 builder still running.
- Phase 6 A/B, alternating rounds old/new/old/new, separate processes, genuinely fresh builds
  (old = git HEAD package via _probe_tl/_so_old, BLAS pool at default): no flag 51.0 / 10.2 /
  50.5 / 9.6 s; TwoStage 60.9 / 11.5 / 68.7 / 11.1 s. Each old/new pair: 21,496 (no flag) and
  22,398 (flag) fields, 0 only-either-side, non-timing differing = response key only. Suites:
  host 1084/42/0 (+11), container 598 + LIVE 6/0. Not done: gunicorn reload (orchestrator's step);
  the page's loading line (Client/) now misdescribes the cost. Remaining cost is mostly Biomarkers
  loading (~3.4 s) that this module cannot avoid.

## 2026-09-12 Biomarkers review builder (B1-B11), session log
- Read the review whole; read adapter.py (align_pros, _threshold_pain_level), bravo_service.py (availability memo, _welch_rows_into, per-recording cache, sweep power), analytics ceilings.
- BEFORE capture on RCS08 through the bridge (probe_bm_review_capture.py before): page 39.1 s, availability 8.22 s then 1.01 s, sweep 2.78 s, matrix read 0.4 s; 766 ratings with a time, 201 carry a UTC date one day later than their California date (16 h: 10, 17 h: 70, 18 h: 108, 19 h: 13); 1,604 per-recording .npz files; one biomarker_psd_matrix entry in the store.
- Stim Optimizer review landed (artifacts/review_2026-09-12_StimOptimizer.md): 0 critical, 3 high
  (S1 Stage 1 labels the Right side by the Left pulse width -- Right recommendation 100 us 4.90 mA
  -> 160 us 4.30 mA once fixed; S2 a pulse width with no fittable stratum reported "resolved" on
  two other strata; S3 the gate's band check ignores which side the evidence came from), 5 medium,
  6 low; all four hazards confirmed. Builder dispatched for S1-S13 (S14 dead code left for the PI;
  S8 behind a switch, last). Decision 140 (Phase 6) written, uncommitted. Three builders running.
- B1 landed: routines/local_time.py (PRO_LOCAL_TZ, local_calendar_day); adapter.py 4 sites + session label; pipeline.py 3 day-binning sites; bravo_service binds _PRO_LOCAL_TZ. tests/test_local_calendar_day.py (7 tests); test_adapter.py fixture anchored on California midnight. Page before vs after-B1: 1,020,742 -> 1,033,080 fields, 96,252 changed, timedomain/availability 0 changed; 3,839 of 5,944 chronic rows carry a different joined rating.
- B2 landed: failed availability build marked failed/failure, refused by the memo, named on the page. tests/test_availability_failure_not_memoized.py (4). Live: two consecutive availability requests 607,395 fields, 0 differing.
- B3 landed: BAND_SWEEP_LSB_CEILINGS keyed on the participant uid; analytics.band_sweep_ceiling_table is the one lookup; _BAND_SWEEP_RULE_VERSION v10. tests/test_ceilings_keyed_on_participant.py (4). Live sweep per contact 6,077 fields, 0 differing (only timing fields and the store key).
- B6 landed: _welch_rows_into logs and counts both failures; counts stored in the per-recording files, the rows-set cache and the matrix payload; page cache.spectrum_builder. tests/test_spectrum_builder_counts.py (4).
- B4 landed: KEEP_NEWEST_BY_KIND biomarker_psd_matrix: 2; rows-set files carry _p/_nop and the sweep keeps one per class. CacheStore test_keep_newest +1; tests/test_rows_set_cache_by_pain_set_class.py (3).
- B5 landed: per-recording key = ratings inside the row's own coverage (+60 s margin) off Recording.date/metadata Duration; sibling sweep; one-time migration through the grandfathered writer. tests/test_recording_spectrum_key_is_its_own_ratings.py (5). Live: reassembled matrix vs stored, sorted by (t, channel, source): 630,442 power values 0 differing; one new far-away rating: 0 recordings re-Welched, 1,604 files before and after.
- B7 landed (RUN_REUSES_RECORDING_MEMO switch): run_for_participant, the sweep (store before decode) and the two sign-off endpoints read the recording memos. B9: one _canon_channel, one ceiling lookup, one _to_epoch. B10: no bare imports (tests/test_import_spelling.py). B11: _validation_tolerance_min (tests/test_validation_tolerance_zero.py).
- Suites after all edits (first run, before the migration fix): host 1105 passed / 42 skipped / 1 failed; container 629 / 1 / LIVE_SKIPPED=6 -- the one failure was test_one_store on my migration's os.replace; migration rerouted through the grandfathered writer.

## 2026-09-12 Closed-Loop review builder (C1-C3, C5-C12, hazard 1), session log -- artifacts/review_2026-09-12_ClosedLoopDeployment_IMPLEMENTED.md
- BEFORE captures on RCS08 through the bridge: the committed left band (58,599 fields) and ZERO_THREE_RIGHT at 24.5 Hz as the page used to send it (Hemisphere and actuated side "Left").
- C1 landed: the page derives both sides from the band (useDeploymentReport.js reportSide; chunk 554.6e2bc640.chunk.js); bravo_service.request_hemisphere; adapter splits _sens_hemi/_act_hemi; device_facts takes sensing_hemisphere=/actuated_hemisphere=; pipeline derives the side from the candidate and regresses E3 on that side's current. Left band before vs after the device_facts group: 58,599 / 58,601 fields, 4 differing + 2 only-after, all owned by C2/C3/C5/C11. Right band, old request vs new: impedance 7286 (left lead) -> 5034 (right), D17 key ZERO_AND_THREE_Left -> _Right, manifest Left -> Right, capture currents 1.0/4.8 -> 1.0/4.5, paused 2.5 -> 2.0, D39 unknown -> passes, D27 pass -> FAIL (the right capture is 150 us); 489 non-timing differences, all downstream of the current column.
- C2 landed: eligibility after threshold placement; _facts_for(threshold=) feeds predicted_recapture_alert and its reason; _o_d26 observed line. Committed band: D26 stays not-determinable (no pooled slope; authority returns None by rule) but now says so; right band: advisory_not_determinable -> advisory_failed.
- C3 landed: brainsense_min_rate_hz = StimOptimizer.routines.percept_adaptive.MIN_ADAPTIVE_RATE_HZ (imported, both spellings); 40 Hz on the left now False, not None; D31 row unchanged live.
- C5 landed: D15 measured from sensing_channels counts (setup_channel_count); stated True deleted; live provenance "measured: 626 groups carried ZERO_TWO_LEFT ... Left side".
- C6 landed: three-source build + pooled/run-points writes before the pooled read (_pre copied onto out; guards extended). Live: pooled entry removed, one right-band request writes 294 rows and its E1 (13.440865950443092, 11 points, 6 runs) equals the row it wrote. Simulation key now carries POOLED_RULE_VERSION.
- C7 landed: four silent handlers log with exc_info; guard flags a silent stored_stability handler.
- C9 measured first: 304,488 spectrum rows / 5,430,456 joined rows, 0 in no epoch on RCS08 (newest spectrum 49 s before the last t_end); _assign_epoch honours open_ended; the simulation's private copy deleted. Tests pin the open-ended rule.
- C10 landed: capture ceilings live in session_report_facts only; active-group reader uses session_report_files/newest_by_stamp; the pipeline's ceiling sentences name the proposed amplitude and no longer cite "D27".
- C11 landed: CANDIDATE_KEYS lists lfp_bins_uvp, capture_pulse_width_us (+ the D26 keys); lead_type per side. C12 landed: one therapeutic current appends a blocker; test.
- Hazard 1 landed and MEASURED (changes numbers): per-run points 3,017 -> 2,724 rows (one run, 2025-09-04 14:15 ONE_THREE_LEFT, loses its only usable setting; 2 more settled points lost); rows in common 59,906 fields, 15 differing; pooled 6,174 fields, 2,263 differing in 194 rows (ONE_THREE_LEFT 13 pts/4 runs -> 11/3; ZERO_THREE_RIGHT 12 -> 11; ZERO_TWO_LEFT 0 changed); ONE_THREE_LEFT 20.5 Hz -3.62 -> +0.46; committed band's ledger/edges/thresholds/verdict 0 differences. Rule versions bumped (run_points v3, amplitude_effect v2, pooled v3, ground_truth v3, simulation v5). PI to confirm.
- C8 landed: the three-source build hands its decoded recordings to the simulation; 98,719 input fields 0 differing; 2.327/2.305 s decoded twice vs 0.010/0.010 s handed over, alternating.
- Suites after everything: host 1106 passed, 43 skipped, 0 failed, 0 errors; container PASS=630 FAIL=0 LIVE_SKIPPED=6. Frontend rebuilt; workers reloaded. C4 not done (scheduled separately).
- Final suites after every Biomarkers edit: host 1106 passed / 43 skipped / 0 failed; container PASS=630 FAIL=0 LIVE_SKIPPED=6; live run container PASS=6 FAIL=0. B7 alternating rounds: page 39.62/39.49 s old vs 39.03/37.21 s memo (1,033,084 fields, 0 differing); deployment_summary 8.53/6.43 vs 3.88/3.82 s (363, 0); band_lsb_and_power 11.66/12.01 vs 9.24/9.88 s (193, 0). B1 headline for the PI: pooled chronic-detector AUC 0.591 -> 0.571, shuffle p 0.035 -> 0.102 under the California day. Report: artifacts/review_2026-09-12_Biomarkers_IMPLEMENTED.md. Workers reloaded (kill -HUP 1) after the last edit. B8 and B12 left for the PI.
- Biomarkers landing committed b7910fdb (decision 142), pushed. C4 prepared: the reviewer's fix
  (alias the package only) is insufficient -- measured on the host, `types` still two objects; a
  meta-path finder (DecodeCommon/import_alias.py, written, not yet wired) unifies all three
  packages in the container (5 checks True, probe_import_alias.py). Wiring the three __init__
  files, a guard test and the settings.py note wait for the Stim Optimizer builder to finish.

## 2026-09-12 Stim Optimizer review builder (S1-S13, not S14), session log -- artifacts/review_2026-09-12_StimOptimizer_IMPLEMENTED.md
- BEFORE captures on RCS08 through the bridge (probe_so_profile.py, scratch store override, genuinely fresh): plain 8,442 fields, TwoStage 9,344 fields.
- S1 landed: run_stage1 reads each side's own pulse-width column (pw_col=None = own; fallback to pw_us_Left named in the audit); FrozenConfiguration.incumbent_pw_us_by_side. Live Right recommendation 55 Hz / 100 us / 4.90 mA (15 epochs) -> 55 Hz / 160 us / 4.30 mA (31 epochs); Left setting 31 fields, 0 differing. PI to confirm.
- S2 landed: a pulse width in force with no fitted stratum is pw_resolved=None with the count and floor named; the other-strata contrast kept as a number only. Live Right pw_resolved False -> None; gate verdict unchanged (resolution still refuses).
- S3 landed: check_adaptive_band per frozen side (one evidence or {side: evidence}); run_two_stage_live selects one cell per side from one build (select_for_side, lfp_evidence.best_deployable); Stage 2 reads per-side. Live: Left ZERO_TWO_LEFT 12/18 respond, 18/18 negative era slope, PASS; Right ZERO_THREE_LEFT (contralateral, named) 15/18, 12/18, PASS; gate still refuses on resolution.
- S4 landed: lfp_evidence.cell_response_verdict is the one rule (screen and gate); verdict rows carry era_negative_significant; strip draws both halves. Live band strip: 18 rows, 234 fields 0 differing, 18 added, 0 of 18 bands change state.
- S5 landed: check_stopping([]) -> "not assessable: no batch history", plateau_met None; both callers. Live: 4 summary rows + 5 strata rows relabelled, nothing else moved.
- S6 landed: adaptive_capable on queue and batch rows (ENV.MIN_RATE_HZ); page column "closed loop". Live: 148 fields added, 0 existing values changed; marked cannot-use 16/8/16/25 of 25 per arm.
- S7 landed: in_force_by_side(es, epochs=) reads the full epoch table; has_ratings_yet / fitted_incumbent_epoch / differs_from_fitted_incumbent / note; DecisionStrip line. Live: exposure_epochs max 123 = es max 123; 10 fields added.
- S9 measured: 1,172 timestamps with both sides, 0 with different rates; epoch table attrs n_timestamps_rates_differ / rates_agree_across_sides. S10: build_objective names an unrated incumbent. S11: key tail 4 -> 9 (band range, ClosedLoop, both override names); key changes by design. S12: three double-spelled imports, band span raises instead of None. S13: PA.ADAPTIVE_LFP_BAND_HZ in build_evidence; readiness bands=None -- closed_loop block 3,203 fields 0 differing.
- Equality proof BEFORE -> AFTER-1: plain 8,442 common, 5 non-timing differing (4 S5, 1 S11), 158 added (S6 148, S7 10); TwoStage 9,265 common, 117 non-timing differing, 79 only-before, 857 only-after, all assigned (S1 235, S3 639, S5 4, S6 148, S7 20, S11 1, Left pw_col 6), 0 unexplained.
- S8 check first: 12 anchors vs stream -- 3 match a sensing row, 8 a legacy row, 4 no row; upper missing on 5,683 of 6,689 rows. S8 landed behind plots.USE_STREAM_LIMIT_ANCHORS (True): stream v2 carries upper_is_patient_limit (decision 136's rule imported from session_report_facts; _THERAPY_SETTINGS_RULE_VERSION v2); limit_anchors_from_stream per side; pipeline.run / run_stage1 limit_anchors_by_hemisphere; arms carry safety_anchors. Live: 1,006 rows with a limit (392 legacy, 450 sensing patient limits, 164 adaptive limits excluded); Left 19 anchors, Right 21; rebuilt matched table 3,036 fields 0 differing. Per arm safe cells 612/564 -> 228/216; Left reachable ceiling 5.0 -> 0.1 mA; optima L 4.70->3.80, R 4.00->1.00 mA; Stage 1 Right preferred 4.30 -> 3.50 mA, Left unchanged. AFTER-1 -> AFTER-2: 501 non-timing differing, all S8 (447) or keys, 0 unexplained. CONTROL (switch off) vs AFTER-1: 10,122 common, 8 non-timing differing, all store keys or the S3 laterality note. PI to decide the switch.
- Loading line rewritten (index.js); S14 not done (PI's call). Frontend NOT built by this builder (source only): index.js, ClosedLoopChecks.js, BandResponseStrip.js, DecisionStrip.js.
- Suites after everything (job 20260912-143636-46262b0a): host 1157 passed, 43 skipped, 0 failed, 0 errors; container PASS=630 FAIL=0 LIVE_SKIPPED=6. Stim Optimizer alone 534 passed, 42 skipped (+51 tests). Workers reloaded (kill -HUP 1).
- Stim Optimizer landing: S8's switch turned OFF by default (Left ceiling 5.0 -> 0.1 mA with it on
  is wrong in kind; PI's call). C4 wired: DecodeCommon/import_alias.py finder in all three package
  inits + 3 guard tests + settings note; Django process: bravo_service / adapter / plots one object
  each, tile memo one dict. Frontend rebuilt (559.b3145144: "adaptive cannot use", new loading
  line; old loading line absent). Suites: host 1160/43/0; container 633/0. Decision 143.
- Watched the Closed-Loop page after the landings: the PI's browser has L 1-3+ 24.5 Hz, and D19
  blocked ("slope sign 1, must be negative"). Builder measured: hazard 1's margin alone -- slope
  -3.79 (13 pts/4 runs) -> +17.31 (11/3), "established" by the interval though p 0.074. Put the
  margin behind post_ramp.USE_POST_RAMP_MARGIN, shipped OFF, rule versions carry the state; live:
  eligible / unsupported / E1 -3.79 again. Host 1161/43/0; container 633/0. Decision 144.
- PI, evening: items 1 and 2 confirmed; item 3 = PI-dictated ceiling, 5.0 mA both sides; do 5, 6,
  7; item 4 = a titration-session recommendation on the Stim Optimizer page (with open item 30).
  Builders dispatched: Biomarkers (B8, B12) and Stim Optimizer (S14, the ceiling). Decisions 142
  and 143 annotated with his confirmations.

- 2026-09-12 evening, B8 and B12 (PI's decision, delete not flag): four unread analytics tasks, the sweep's server-drawn figures, the two unused routes/views and their service functions deleted (107 insertions, 832 deletions); page 1,033,084 -> 1,025,907 fields, 0 differing, all 7,177 only-before under the four removed blocks; sweep 36,528 -> 27,252, all 9,276 only-before under figures, 23 differing all timings/keys; bytes 18,870,630 -> 18,753,693 and 1,198,999 -> 737,444; container 629 + 1 = 630 = 633 - 3 deleted tests, the 1 container and 35 host failures all in the other builder's in-flight StimOptimizer work. Section appended to artifacts/review_2026-09-12_Biomarkers_IMPLEMENTED.md.
- 2026-09-12 evening, S14 (PI: delete item 7 as listed): four unreached Stim Optimizer modules (schedule, session_analysis, safety_ordinal, surrogate_torch; 3,696 lines) and their tests (2,128) deleted, plus seven unreached functions in kept files; `device_band_power` and `validate_policy` KEPT because today's work gave them callers; `ramp_windows_from_amplitude` kept as instructed. Proof: fresh RCS08 builds before/after, 8,738 fields plain (1 non-timing diff: the key) and 10,324 with TwoStage (2: the key, the backend sentence).
- 2026-09-12 evening, item 3 (PI: a stated ceiling, 5.0 mA both sides): `StimOptimizer/safety_ceiling.py` holds the one table; LIMIT_ANCHORS, limit_anchors_from_stream and USE_STREAM_LIMIT_ANCHORS deleted; flat fit and Stage 1 seed from one call; the gate reads the per-side ceiling. RCS08 per arm: Left safe 612->600, reach 5.0->4.9, optima unchanged; Right safe 564->588, contiguous no->yes, reach 1.9->4.8, back__Right optimum 4.9->4.8 mA; Stage 1 preferred settings and the gate verdict unchanged. Proof after-A vs after-A+B: 120 / 135 non-timing diffs, 0 unexplained. Host 1038/2/0 (1,204 -> 1,040 items, arithmetic exact); container PASS=630 FAIL=0. Workers reloaded; production store rebuilt once under the new key. Frontend source only (ArmGainStrip.js, ClosedLoopChecks.js), not rebuilt.
- 2026-09-12 evening, Phase 8 (item 4 + open item 30): the Stim Optimizer page recommends a titration session designed from RCS08's own record ("Titration session to run next", `titration_plan` in the response; `StimOptimizer/titration_plan.py`, `post_ramp.margin_becomes_available`, `TitrationSessionCard.js`). Live on RCS08: both sides 55 Hz (in force), L 100 us / R 150 us, ceiling 5.0 mA, ladder 0→5.0→0 in 0.5 mA (21 steps, 11 currents), 60 s hold (13 usable 3 s pieces after the 20 s margin), record from L 0⁻2⁺ (Left, 12/18 bands at 55 Hz) and L 0⁻3⁺ (Right's best is contralateral, 15/18; R 1⁻3⁺ did not pass), 12 clear / 10 struck centres at 55 Hz; the record holds at most 6 settled currents in any run (2026-08-18, ONE_THREE_LEFT), so the margin stays off and the sentence is derived. Proof: 21,771 fields before / 22,106 after, 335 added all under titration_plan, 2 differing (key, timestamp). Suites: host 1068 / 2 / 0, container 630 / 0. Chunk 328.599edcdf. Workers reloaded, page request rebuilt and served (1.67 s). Report: artifacts/titration_plan_2026-09-12.md. Found, not fixed: the response kind keeps one entry, so the page's plain and TwoStage requests evict each other.
- Titration card watched in the PI's browser (both columns, the struck harmonics, the contralateral
  warning on the Right). Store keeps two stim_optimizer_response entries (decision 146); the test
  that pinned one entry updated to pin two. Host 1069/2/0; container 631/0. Phase 8 complete.
- 2026-09-13 Phase 9 built (builder): "established means the mean only" -- `EdgeEstimate.resolved` is the point sign, `statistically_established` is the interval rule kept as a caveat, `DeploymentReport.provisional` / `n_edges_unestablished`; verdict string "supported (point signs only; N of 3 intervals span zero)"; D26 verdicts follow the sign with the interval as a caveat; page: ProvisionalNote.js under the evidence and transcribe tracks, on the parameter card and the sign-off sheet; triangle labels read "SIGN − (INTERVAL SPANS ZERO)". RCS08 through the bridge, both L 1-3+ and L 0-2+ at 24.5 Hz: verdict unsupported -> supported (point signs only; 2 of 3 intervals span zero) -- 2 not 3, E3's interval excludes zero -- licensed False -> True; edge numbers 21 compared 0 differing, thresholds 8 / 0, prescription fields 48 / 0, ledger keyed by rule id 120 and 124 fields / 0 differing (the D26 advisory-failed row leaves L 1-3+ because the alert follows the sign). host 1086 / 2 / 0 (+17: 15 new, 2 splits), container 631 / 0; chunk 576.08f0ab97.chunk.js; workers reloaded. Report: artifacts/established_point_sign_2026-09-13.md. Not committed (orchestrator's).
- Phase 9 watched live on L 1-3+ 24.5 Hz: header "supports it on point signs alone (provisional:
  2 of 3 intervals span zero)". Committed as decision 147. Phase 9 complete.
- 2026-09-13: D01/D02 labelling advisories removed from the "What would change this" panel
  (8181850d; watched: D09 still shown). Phase 10 opened: three researchers on the adaptive timing
  parameters (manuals in the lab Dropbox extracted to scratchpad/medtronic_docs; web + toolkits;
  RCS08 data through the bridge).
- Phase 10 synthesis written (artifacts/research_2026-09-13_percept_adaptive_timing_SYNTHESIS.md);
  DEVICE_percept_rc.md §2 corrected in place (defaults, not fixed; FDA ranges; startup delay);
  decision 148. Recommendation: onset 30 s, averaging 30 s, transitions 30 s / 30 s, startup delay
  15 s (or nearest above 12 s), blanking 30 s, thresholds separated. Phase 10 complete.
- A610 (2025-02-14 edition) found in ADMIN/Equipment/Percept RC after the PI's upload; read whole:
  defines onset / blanking / startup delay (Table 6 p. 42), confirms all adjustable, gives NO
  ranges; adds the manufacturer's tuning directions (Table 16 p. 73-74) and the 5 mA / 120 us
  capture-artefact note. Synthesis §6 addendum; DEVICE_percept_rc.md note updated.
- 2026-09-13 evening, Phase 11 (PI: "wire up the new ranges ... into whatever modules need to be
  updated"): `percept_adaptive` is the one home of the documented ranges (FDA Table 2: onset 0-6
  min dual / 0-30 s single, transitions 250 ms-30 min, thresholds 0.55-400 uVrms, limits 0-25.5
  mA; tip card: averaging 0-30 s; startup delay and blanking still undocumented); `validate_policy`
  checks them; D20 judges declared timing against the range (RCS08's 30 s / 4 s / 30 s now passes
  where it failed for differing from the defaults), D21 reads the FDA onset range (30 s passes; it
  was outside the trial's 1.2-2 s); the parameter card carries range + source per row, the
  decision-148 values from `ClosedLoopDeployment/timing_recommendation.py` (participant table, the
  safety_ceiling pattern) with reason and confidence, "programmed today" from the newest session
  report's active group (`device_facts.programmed_closed_loop_timing`), and a fallback onset of
  two averaging windows (8192 ms at the 4096 ms window) instead of the trial's 2 s ceiling. First
  suite run: host 1092 / 2 / 5 failed (the five pinned the old floor or the exact facts dict) --
  rewritten; second run submitted. Frontend rebuilt, "programmed today" in chunk 576.e37f8ee0.
  Contest A (LTI) landed: averaging 9 s, onset 72 / 63 s, thresholds re-placed; finds the Phase 10
  30 s onset was computed on the 3 s clock (ten confirmations) and is ONE update at the device's
  30 s averaging -- the current device settings and the Phase 10 recommendation replay
  identically. Not yet acted on: the table keeps decision 148's values until the six are judged.
- Phase 11 proven and landed: second suite run (direct `docker exec`, the bridge being queued
  behind contest jobs) host 1097 / 2 / 0, container 631 / 0; RCS08 L 1-3+ 24.5 Hz before/after
  49,343 / 49,473 fields, 173 differing, all explained (parameter card, D20/D21 text, the new
  programmed-timing block; verdict / thresholds / edges 0 differing); workers HUP'd; decision 149.
- Contest F (ML/statistics) landed (artifacts/contest_2026-09-13_ml_stats.md): models explain
  only ~18 % / 8 % of the next-reading variance (persistence is WORSE than the mean); onset 48 s /
  36 s by split, but a 200-replicate block bootstrap spans 36-90 s / 27-60 s -- the split test
  flatters every method; blanking undetermined once the onset is long; averaging and onset
  interact (a 30 s averaging turns the 48 s onset into two confirmations; the device's 30/30
  today is ONE); the High-confidence recommendation is to SEPARATE the thresholds by ~0.4 of the
  scatter (halves the switching rate at every split and replicate). Agrees with A on the
  averaging/onset interaction and the threshold separation; disagrees on averaging (F: 3 s, A: 9 s)
  and startup delay (F 12 / 9 s measured, A 87 / 54 s extrapolated). Waiting on B, C, D, E.
- Contest C (FOPDT + lambda) landed (artifacts/contest_2026-09-13_fopdt_lambda.md): the
  stimulation current has NO measurable effect on the next reading (removing it from the model
  changes the error by nothing or improves it; the record's step tests are 20-34x too blunt);
  with 30 s averaging emulated, the device's settings and the Phase 10 recommendation replay
  IDENTICALLY (39.6 switches/h, 49 reversals, at a limit 98-100 % of the time); its own settings
  (averaging 30 s, onset 60/60, blanking 60, transitions 360 s, startup 60/30 s, thresholds at
  3-5 noise SD) make the loop almost inert (0-0.34 switches/h, 3.10 mA). Refutes the Phase 10
  "0.5 mA step moves the band 0.30-0.46 SD" as evidence (placebo windows give 0.65-0.78). Its
  headline: do not run adaptive on this evidence; run open item 30's titration. Agrees with A
  and F on the averaging/onset interaction and the stored pairs being single thresholds.
  Waiting on B, D, E.
- Contest E (nonlinear dynamics) landed (artifacts/contest_2026-09-13_nonlin_dyn.md): surrogate
  test says NO nonlinearity is established (p 0.35 / 0.33; a linear AR does as well); the slow
  part of a reading is 12 % / 11 % of its variance and peaks at a 15 s window; the switching
  rate at every setting is within 10-30 % of the same readings SHUFFLED, so the loop switches on
  the value distribution, not the history (no onset "knee"); Phase 10's 30 s onset reproduces
  2.6 switches/h only WITHOUT averaging and gives 38.7/h with 51 undone at the 30 s averaging it
  recommended; the device's 167/166 pins the current at the ceiling 92-94 % of the time.
  Recommends averaging 15 s, onset 60 / 75 s, blanking = onset, startup 15 s, ramps 180 s (not
  robust), thresholds at the 40th/60th percentiles (280.0/201.3; 213.8/173.3). Startup dip:
  finds NONE (disagrees with Phase 10 and F). Waiting on B, D.
- Contest D (dwell-time Markov) landed (artifacts/contest_2026-09-13_dwell_markov.md): two-state
  chain on the 30 s averaged readings; a single 30 s comparison is wrong 46 % of the time, three
  comparisons 2.5 % -- so onset 90 s (L 1-3+) / 120-150 s (L 0-2+) at averaging 30 s; the
  fitted chain PREDICTED the replay's switching rate (1.79 vs 1.77 /h); ramps 30 s (an upper
  bound: the state outlasts a 30 s ramp in 99 % of episodes), blanking 30 s, startup 45 s (one
  window + a measured 0.10-SD first-reading dip); thresholds re-placed as a 0.4-0.8-SD deadband
  around the best single value (not robust across splits, 3-15 units). Confirms A/C/E/F: the
  device's 30 s onset at 30 s averaging is ONE comparison, 34-40 switches/h with 49 undone.
  Waiting on B.
- Contest B (Kalman) landed; all six in. Judged on the brief's rule; synthesis written
  (artifacts/contest_2026-09-13_SYNTHESIS.md): B adopted (best prediction 0.162 / 0.128, nine
  values identical across splits, reproduces Phase 10's 2.5/h under the same conditions, its noise
  simulation is a computable rule), threshold centring from A/D/E, F's bootstrap as the robustness
  test. Table changed: averaging 30 s -> 3 s. Suites host 1098 / 2 / 0, container 631 / 0; RCS08
  L 1-3+ capture 49,473 / 49,443 fields, 73 differing, all parameter-card; workers HUP'd; decision
  150. Phase 12 complete.
- Correction, same evening: asked directly whether every contestant assumed 30 s averaging.
  Answer: no -- four of six computed short values from real sweeps (A 9 s, B 3 s, E 15 s, F 3 s),
  two computed 30 s (C, D), by four genuinely different objectives. But re-checking the switching-
  rate comparison the synthesis leaned on found it held the onset FIXED IN SECONDS across
  averaging windows -- the same confound several entries warned about. Re-measured directly
  (averaging_sweep.py, gitignored) holding the threshold pair fixed and re-tuning the onset
  properly at each averaging: switching rate is FLAT, 3.1-4.4/h from 3 s to 30 s, on both the
  stored pair and the device's actual 167/166. What differs is response time: 21-24 s to a
  confirmed decision at 3 s averaging against 90-180 s at 30 s, same switching rate. Table value
  unchanged (3 s); the stated reason corrected in timing_recommendation.py and the synthesis
  (new section 3a) and decision 150. Proof: 49,443 fields both sides, 3 differing, all the
  averaging row's "why" text. Host 1098/2/0, container 631/0. Workers reloaded.
- Phase 13, T2 from the synthesis (section 4): the CL-DBS simulations card replayed only the
  white-paper Dual Threshold default (averaging 1200 ms, onset 1200 ms, blanking 2000 ms,
  transitions 150000/300000 ms) -- `write_simulation` called `run_models` with no `params=` at
  all, so `simulate_segments` fell through to `replay.DEFAULT_PARAMS` regardless of what the
  device actually runs or what decision 150 recommends. Read `device_facts.py`'s
  `programmed_closed_loop_timing` (already computed as `active_sensing_group_timing`, per
  hemisphere) and `timing_recommendation.for_participant`; built `adapter._timing_runs_for_simulation`
  mapping both onto `replay.DEFAULT_PARAMS`'s field names (the replay carries ONE onset timer,
  so the upper threshold's own onset is used, stated in a comment and the on-screen source
  sentence rather than silently averaging the two). `write_simulation` now calls `run_models`
  TWICE, once per regime, and stores both under `timing_runs.programmed` / `timing_runs.recommended`
  in the one `closed_loop_simulation` entry (`RULE_VERSION` bumped to v6; `timing_recommendation.
  TABLE_VERSION` new, folded into `simulation_signature` so an edited recommendation table
  invalidates a stale replay). Added a reversal counter to `simulation.py` (`_count_reversals`,
  reproduced from the contest's own `nonlin_dyn/s5_controller.py` definition: a switch undone
  within one onset) on every model, both regimes. Frontend (`ClosedLoopSimulationPanel.js`):
  both regimes shown side by side (switches/h, undone count, undone/h, timing values), a click
  toggle picks which one draws the three figures, default "recommended"; the absent-payload
  shape kept both the old (`refused`/`models`) and new (`timing_runs`/`primary_run`) fields so
  no reader breaks. Four new tests (test_simulation.py 10-13), all pinned to real numbers:
  the reversal count against a constructed state array (2 of 3 transitions undone at onset=4,
  0 at onset=2); `run_models` under two params on the file's own `_series()` fixture (short
  timing: 22 transitions, 3 undone; long timing: 11 transitions, 0 undone -- pinned exactly, not
  "differ"); `_timing_runs_for_simulation`'s four cases (both present, hemisphere absent, table
  absent, both absent); the signature changes with `TABLE_VERSION`. Both suites green: host
  1102 passed, 2 skipped, 0 failed (was 1098, +4); container 631 passed, 0 failed. Frontend
  rebuilt; "As programmed today", "Record-derived recommendation" and "undone within one onset"
  all found in the served chunk (576.0531f929.chunk.js) by grep, never by component name.
  Equality proof on RCS08, ONE_THREE_LEFT at 24.5 Hz, the live report, before (stashed to the
  pre-edit code) and after: 49,443 fields before, 49,450 after, 49,442 in common, 1 only-before,
  8 only-after, 3 differing (2 non-timing) -- every one under `closed_loop_simulation`; nothing
  outside that block moved (the verdict, edges, thresholds and eligibility are byte-identical).
  The "before" run happened to serve an already-stored entry from an earlier session (built
  under the OLD rule version, `already_stored: True`, 0 pieces reported); the "after" run's new
  signature (rule version v6) correctly missed that stale entry and rebuilt fresh (51,105
  pieces). Separately, read the module's own FULL-RECORD replay for both regimes directly
  (`closed_loop_simulation_for_participant`, what the page actually shows), honestly, with NO
  attempt to force agreement with the contest's own 20-stretch held-out numbers (39.6/h, 49
  undone; 2.5/h, 0 undone), which were computed on a specific subset, not the whole record:
  "as programmed today" (30 s averaging / 30 s onset / 4 s ramps, GROUP_D) gives 243.0
  switches/h, 722 transitions, 253 undone (85.2/h), over 2.97 h of signal in 102 stretches --
  far higher than the contest's 39.6/h, because a 30 s averaging window discards almost the
  whole record (most 3 s-tile stretches never reach two 30 s windows, so only 102 short,
  noisier stretches survive out of far more available). "Recommended" (3 s averaging / 30 s
  onset / 30 s ramps) gives 2.469 switches/h, 78 transitions, 0 undone, over 31.59 h of signal
  in 325 stretches -- close to the contest's own 2.53/h at the same setting on its own
  held-out subset, a genuine agreement across two very different samples of the record, stated
  as such rather than manufactured. Commit and push done by the builder itself (not isolated).

## Session: T3 -- a confirmations-and-separation design rule (2026-09-13/14)

Read the synthesis (artifacts/contest_2026-09-13_SYNTHESIS.md section 4, T3's acceptance
criteria) and contest entry B's own report and its scratch source
(`_agent_bridge/_probe_tl/_contest/kalman_est/{common,kf,k0b_ctrlsys,k1_models,k2_derive}.py`,
gitignored, read via `docker exec ... cat`). Ported the two-component/one-component fit, the
Riccati steady state (own iteration, `ctrlsys.sb02md` cross-check guarded behind an ImportError
since `ctrlsys` is container-only), and the noise-only crossing simulation into a new production
file, `ClosedLoopDeployment/design_rule.py` -- pure functions, no Django import required except
inside the one entry point that calls `simulation.regrid_stretches`. Smoke-tested standalone on
the host (bravo_app conda env) before wiring anything: a synthetic white-noise check matched the
analytic Phi-inverse answer to within simulation noise; a synthetic two-component series fit
correctly as L4 with phi_f < phi_s.

Wired into `adapter.report_for_participant`, store-backed the same way `write_simulation` is
(`write_design_rule`/`design_rule_if_stored`). Caught, before shipping, that `report_to_dict(rep)`
runs BEFORE this point in the function and turns the `Prescription` dataclasses into plain dicts
-- mutating `rep.prescriptions` afterward (my first draft, via `prescription.attach_design_rule`)
would have changed nothing the response actually returns. Fixed by patching the already-serialised
`out["prescriptions"]`/`out["prescription"]` row dicts directly. `attach_design_rule` (the
dataclass-mutating version) kept for its own tests since it is a legitimate, independently useful
function, just not the one the live wiring calls.

20 new tests in `test_design_rule.py`, 6 more in the same file for `design_rule_note`/
`attach_design_rule`. Host suite 1122 passed, 3 skipped, 0 failed (fresh run). Container suite
PASS=631 FAIL=0 LIVE_SKIPPED=6.

Live proof on RCS08 found a real bug within minutes: fitting L 1-3+ right after L 0-2+ evicted
L 0-2+'s just-written `closed_loop_design_rule` entry -- `closed_loop_design_rule` was missing
from `CacheStore.store.KEEP_NEWEST_BY_KIND`, the exact decision-107 class of defect this project
has already paid for twice on the neighbouring `closed_loop_simulation` kind. Fixed with the same
limit (6); re-ran both suites (unaffected) and re-captured both candidates' tables, which then
coexisted correctly.

Compared the live table against B's own published table (contest_2026-09-13_kalman_est.md
§3.3) honestly rather than forcing agreement: on L 0-2+ at 3s/30s, exact match (±5.0 both). On
L 1-3+, nine of eleven comparable cells match exactly (±25, ±5 x6, ±120 x2, ±60, ±15); one cell
one grid step off (±10 vs B's ±5 at 15s/120s, plausibly the smaller default simulated-hours
budget, 100h vs B's 200h); two cells B reports "never" (its own separation grid capped at 120)
come out as large-but-finite here (this file's grid extends to 300) -- a disclosed difference in
search range, not a method disagreement.

Live before/after field-count proof (git-stashed adapter.py/prescription.py for "before"):
49,382 fields before, 49,426 after, 48,271 in common, 2 differing (both a pre-existing
`write_simulation` cache-hit bookkeeping artifact from capturing "after" twice -- traced to root
cause, not a functional change), 51 only-after (30+16 `design_rule_note` keys, mostly `None`,
2+2 carrying the real sentence on the Upper/Lower LFP threshold rows; 4 the new
`closed_loop_design_rule` summary; 1 a pre-existing bookkeeping key), 8 only-before (the same
`write_simulation` artifact's fresh-build-only fields). Verdict, licensed flag, threshold block:
0 differing.

Frontend: `PrescriptionPanel.js` renders `design_rule_note` as an always-visible line beside the
threshold rows. Rebuilt; `design_rule_note` found in the served chunk (576.b59d4c09.chunk.js) by
grep. Workers reloaded (`kill -HUP 1`); not watched in a browser this session.

Decision 152 written (next number after 151, which T2's worker had already used -- checked, not
guessed). task_plan.md Phase 14 added and marked complete; Next Step rewritten to name T4-T7 and
the threshold re-centring as what remains. Commit and push done by this session itself.

## Session 2026-09-13 (continued): T4 -- threshold occupancy check
- Built `ClosedLoopDeployment/occupancy.py`: re-averages the same power series design_rule.py and
  simulation.py already read (`adapter.simulation_inputs_for_participant`) onto the recommended
  averaging duration (`timing_recommendation.for_participant`), never across a gap between
  recordings (`simulation.regrid_stretches`'s own device-clock grid), and reports frac_above /
  frac_between / frac_below, the median reading, the pair's centre and half-width, and a warning
  when frac_between < 10% or the centre sits more than one half-width from the median.
- Wired into `adapter.report_for_participant` right after the T3 design-rule step; the sentence
  patched onto the SAME serialised threshold rows `design_rule_note` already patches. Added
  `Field_.occupancy_note`, `occupancy_note()`, `attach_occupancy()` to prescription.py, mirroring
  T3's own pattern exactly.
- 20 new tests in `tests/test_occupancy.py` (known-by-construction fractions, gap-awareness,
  empty-window dropping, both direction words, the card-wiring tests). Ran the new file alone
  first through the bridge (18 passed), before the full-suite run.
- Live probe (`_agent_bridge/_probe_tl/probe_t4_occupancy.py`): git-stashed adapter.py and
  prescription.py for "before", restored for "after", `CLS.run_for_participant` on the committed
  candidate (ZERO_TWO_LEFT / L 0-2+, 24.5 Hz). Found ONE thing worth a second look immediately:
  the committed pair's own occupancy (2.0% between, warning True) looked right, but the stored
  L 1-3+ pair's number (15.9% between) fell noticeably short of the synthesis's own 18-21%, and
  its off-centre distance (9.3 units) was nowhere near the synthesis's "61 units below the
  median" -- wrote `probe_t4_diag.py` to isolate the cause without re-running the full report:
  confirmed the mean is stable across averaging duration (233.5 at both 3s and 30s) but the
  MEDIAN is not (195.5 at 3s vs 223.4 at 30s) on this heavily right-skewed series (10th/90th
  percentile 83.7/428.7 at 3s averaging) -- the synthesis's own number is a MEAN at 30s
  averaging, this check reports a MEDIAN at the averaging duration actually in force today
  (3s, since decision 150). Both are real, correct answers to different questions; disclosed
  honestly in the decision row rather than forced to match.
- A real sign bug was found the same way: the committed band's own live note read "sits 12.4
  units BELOW the median" when the centre (193.51) is numerically ABOVE the median (181.12) --
  `side = "below" if distance > 0 else "above"` had it backwards (distance = centre - median, so
  positive distance means centre IS above median). Fixed in occupancy.py; two new tests
  (`test_occupancy_names_the_correct_side_when_the_centre_sits_{above,below}_the_median`) pin
  the correct word on both sides so this cannot silently flip back. Re-ran the live probe after
  the fix to get the corrected "before"/"after" pkls for the final field-count proof.
- Field-count/difference-count proof (`probe_t4_diff.py`, flattening both pickles): 49,484
  fields before, 49,543 after, 49,484 in common, 0 only-before, 59 only-after (all under
  `threshold_occupancy` or `occupancy_note`), 0 differing.
- Both suites via `run_both_suites.sh` (bridge, submit-then-poll): host 1143 passed, 2 skipped,
  0 failed, 0 errors; container PASS=631 FAIL=0 LIVE_SKIPPED=6.
- Frontend: `PrescriptionPanel.js` renders `f.occupancy_note` beside `f.design_rule_note`, same
  always-visible placement and warning colour. Rebuilt; `occupancy_note` found (grep) in the
  served chunk `576.c76946db.chunk.js`, the same chunk as `design_rule_note`. No new warning on
  the touched file. Not watched in a browser this session.
- Decision 153 written (next number after 152, read from the file's own tail, not guessed).
  task_plan.md Phase 15 added and marked complete; Next Step rewritten to name T5-T7 and the
  threshold re-centring, with T4's own live finding on the committed band noted as a live reading
  in favour of that re-centring. Commit and push done by this session itself.

## Session: T6, the start-of-recording dip measured two disagreeing ways (2026-09-13)
- Read `design_rule.py` and `occupancy.py` fully, and the T3/T4 wiring in `adapter.py` and
  `prescription.py`, before writing anything -- confirmed the actual wiring pattern patches the
  ALREADY-SERIALISED prescription-row dicts (`_patch_rows` inside `report_for_participant`, after
  `report_to_dict(rep)` has run), never the `Prescription`/`Field_` dataclasses directly; the
  dataclass-mutation functions (`attach_design_rule`, `attach_occupancy`) exist only for testing
  against the dataclasses and are not on the live wiring path -- the exact trap the task warned
  about, avoided by following the established pattern rather than the dead one.
- Read the two contest scripts on the container directly: `_probe_tl/_contest/dwell_markov/
  d1_explore.py` ("startup check") and `_probe_tl/_contest/nonlin_dyn/s3_returnmap.py`
  ("(D) start-of-stretch transient"). Confirmed by reading, not assuming: both split stretches
  70/30 by start time and by count; both call their baseline "the stretch's own median"; the
  baselines are numerically IDENTICAL functions (`np.median` of the finite values); what differs
  is which reading each contestant calls "the k-th reading" -- D compacts a stretch to its real
  readings first (`f = pp[np.isfinite(pp)]`, needs `f.size > 20`), E indexes the raw regridded
  grid position directly (`p[j]`, no minimum length).
- Wrote `startup_bias.py` porting both methods line for line, plus the one train/test split both
  used. Verified the port against the contest's OWN raw CSVs (`d1_startup_bias.csv`,
  `e3_startup_transient.csv`, read on the container) before wiring anything: fed the identical
  stretches the contest scripts built (raw `regrid_stretches` on the npz's own `t`/`p`/`a`, no
  power-isfinite pre-filter), both methods reproduce the contest's printed numbers to every
  digit -- D: n=82, bias=-0.10404153099836579, t=-2.4914058108928567; E: n=221,
  bias=-0.03452435522071541, z=-1.4706266338270466.
- Then ran the SAME functions through `startup_bias_for_series`'s own top-level preprocessing
  (which mirrors `design_rule_for_series`'s established convention: filter to `isfinite(power)`
  BEFORE computing gaps and calling `regrid_stretches`) and found close but not identical numbers
  (n=88, bias=-0.095, t=-2.40 on the same band). Traced the cause rather than forcing agreement:
  the power-isfinite pre-filter removes a sample's time slot entirely before gap detection, which
  can turn one short interruption into what looks like two separate stretches -- a real, disclosed
  side effect of matching this module's OWN established loader (already used unmodified by T3 and
  T4) rather than the contest's own, different preprocessing. Decided to keep the module's
  established convention rather than diverge from it for this one file, per the task's own
  instruction to reuse the existing loader.
- Wired into `adapter.report_for_participant` (new block after the T4 occupancy block, before the
  decision-74 consistency check), and into `prescription.py` (`Field_.startup_bias_note`,
  `startup_bias_note()`, `attach_startup_bias()`, `as_rows()` carries the new key) -- the identical
  shape as T3/T4.
- 19 new tests in `test_startup_bias.py`: the split; both methods' arithmetic against independently
  computed expected values (never re-deriving from the function under test); the exact mechanism
  (a missing raw-grid cell excludes a stretch from E but not from D, demonstrated by construction
  on the same two stretches through both methods); the top-level series builder on a constructed
  dip; the prescription-note wiring. One test's first draft asserted the wrong thing (`bias_in_sd
  is not None` on a reading index with only 1 contributing stretch, where `None` is the correct,
  honest answer since there is no standard error to report with n=1) -- caught by running the
  suite, not assumed correct; fixed by asserting `is None` with a comment explaining why.
- Both suites via `run_both_suites.sh` (bridge, submit-then-poll, job 20260913-220649-d8aac8cf):
  host 1162 passed, 2 skipped, 0 failed, 0 errors (was 1143, +19); container PASS=631 FAIL=0
  LIVE_SKIPPED=6.
- Field-count/difference-count proof on the committed band (ZERO_TWO_LEFT / L 0-2+, 24.5 Hz),
  genuinely before and after (`git stash -u` for "before" since two of the four changed files are
  new/untracked, `git stash pop` to restore "after"; `_startup_bias_proof.py` calls
  `adapter.report_for_participant` directly rather than through gunicorn, so no worker-staleness
  risk): 49,594 fields before, 49,741 after, 49,594 in common, 0 only-before, 147 only-after
  (all under `closed_loop_startup_bias` or the two `startup_bias_note` keys), 0 differing.
- On the committed band the two methods disagree even on the SIGN of the first reading's bias:
  D reads 71 stretches, -0.045 of the scatter (not confident, t=-1.04); E reads 205 stretches,
  +0.007 (essentially flat, z=0.35). Reported exactly as measured, not smoothed toward agreement.
- Frontend: `PrescriptionPanel.js` gained a block for `f.startup_bias_note`, identical placement
  and styling to `design_rule_note`/`occupancy_note`, beside the Adaptive startup delay row.
  Rebuilt; the new sentence's own wording found (grep) in the served chunk `576.e196d94a.chunk.js`;
  `PrescriptionPanel.js` produced no new build warning. Not watched in a browser this session.
- Decision 154 written (next number after 153, read from the file's own tail, not guessed).
  task_plan.md Phase 16 added and marked complete; Next Step rewritten to name T5 and T7 as what
  remains. Commit and push done by this session itself.

## Session 2026-09-13, continued: T5, the block bootstrap as an interval
- Read the reference scripts on the container (`_agent_bridge/_probe_tl/_contest/ml_stats/`):
  `s4_bootstrap.py` (the grid, feasibility rule, tie-break, bootstrap loop) and `fastreplay.py`
  (the config-vectorised controller replay, self-checked against `simulation.simulate_series` in
  `s1_selfcheck.py`). The actual grid is 18 onset x 8 gap x 4 blanking = 576 configurations, not
  the "1,440" the task's own paraphrase used -- ported from the working script, not the paraphrase.
- Read the T3/T4/T6 wiring pattern in `adapter.py`/`prescription.py` (patch the already-serialised
  `out["prescriptions"]`/`out["prescription"]` row dicts, never mutate the dataclasses after
  `report_to_dict` has run) and `simulation.py`'s `regrid_stretches`/`_grid_like`.
- Built `ClosedLoopDeployment/robustness.py`: `prepare`/`run_stretch`/`run_many` ported line for
  line from `fastreplay.py`; `choose_naive` a literal port of `s4_bootstrap.choose`.
- THE PI'S HARD REQUIREMENT ("vectorized code for bootstrapping so it's super fast") met by an
  optimisation beyond a literal port: since `run_stretch` resets the controller's state at the
  start of every stretch, one stretch's replay is independent of every other stretch and
  deterministic given a configuration -- so a resample's answer (a weighted sum over whichever
  stretches it draws, with replacement) can be built from numbers computed ONCE per training
  stretch (`_stretch_accumulators`, the one per-reading Python loop in the file, config-vectorised
  across all 576 configurations) rather than re-simulated per replicate. Every one of the 200
  bootstrap replicates (`_choose_from_precompute`) is then a weighted sum via matrix multiplication
  and `numpy.bincount` -- no further calls into `run_stretch`.
- 20 tests written (`tests/test_robustness.py`), all passing first try in the container: the grid
  shape, `run_stretch`'s own known-by-construction behaviour, the fraction-between precompute
  against the naive function (including a duplicated-stretch case), the CENTRAL equality (fast
  path == naive path) at weights of one, with one stretch drawn twice, and over 15 independently
  drawn resample vectors, the refusal paths, an end-to-end run on constructed data, the fixed
  device averaging default, and the `robustness_note`/`attach_robustness` prescription wiring.
- Checked the port against the reference script's own stored CSV output, not only re-derived
  arithmetic: fed the identical npz series (`series_ONE_THREE_LEFT_24.5.npz`) and seed (20260913),
  the onset interval came back 36.0-90.0 s -- bit for bit the acceptance text and the reference's
  own `s4_bootstrap_ONE_THREE_LEFT_20260913.csv`. Gap-separation interval matched to 12 significant
  figures, blanking matched exactly. One honest, traced gap: the reported MEDIAN differs (48.0 s
  here vs 54.0 s there) because this file filters out missing-power readings before regridding --
  the same convention `design_rule.py` (T3) and `startup_bias.py` (T6) already use -- while the
  ad hoc contest script did not; 246 training stretches here against 231 unfiltered, a disclosed
  difference in an already-established convention, not a defect.
- Wired into `adapter.report_for_participant` (`write_robustness`/`robustness_if_stored`, stored
  via CacheStore under `closed_loop_robustness`, same pattern as `write_design_rule`); patched onto
  every onset-duration field ("nset duration" substring match, matching Dual's two onset fields and
  Single's one). `prescription.py` gained `Field_.robustness_note`, `robustness_note()`,
  `attach_robustness()`. No pipeline.py ledger row added or touched -- same as T3/T4/T6.
- Both suites via `run_both_suites.sh` (bridge, submit-then-poll, job 20260913-222923-b202335b):
  host 1182 passed, 2 skipped, 0 failed, 0 errors (parallel 1181/2, serial store pass 1/0);
  container PASS=631 FAIL=0 LIVE_SKIPPED=6.
- Live field-count/difference-count proof on RCS08, the currently committed band (ZERO_TWO_LEFT /
  L 0-2+, 24.5 Hz), genuinely before and after (`git stash -u` for "before", `git stash pop` to
  restore "after"; `_agent_bridge/_probe_t5.py capture`/`diff`, calling
  `bravo_service.run_for_participant` directly, not through gunicorn): 49,756 fields before, 49,806
  after, 49,756 in common, 0 real differences (4 nominal "differing" fields are `nan != nan` on
  both sides, unrelated to this change), 0 only-before, 50 only-after (4 the new
  `closed_loop_robustness` summary, 46 the new `robustness_note` key on every field row across the
  three prescription views).
- The bootstrap's own wall-clock measured directly (not folded into page timing): 0.059 s on the
  committed band (46,118 tiles, 4 training stretches, 159/200 feasible), 1.53 s on the richer
  L 1-3+ series (37,891 raw samples, 246 training stretches, 200/200 feasible) -- both timed twice,
  identical each time, since the computation is deterministic given the seed.
- On the committed band itself: onset interval 27-60 s, blanking 3-3 s, thresholds 43.5-108.7
  device units apart -- a different, real number from L 1-3+'s 36-90 s, expected given the far
  sparser recording history on this band (4 training stretches against 246).
- Frontend rebuilt; `PrescriptionPanel.js` gained a `robustness_note` block, identical placement to
  the three earlier notes, beside the onset-duration row(s). New sentence's own wording ("are one
  recommendation") found (grep) in the served chunk `576.9888adf4.chunk.js`.
- Decision 155 written (next number after 154, read from the file's own tail). task_plan.md Phase
  17 added and marked complete; Next Step rewritten to name T7 and the threshold re-centring as
  what remains. Commit and push done by this session itself.

### Phase 18: T7 -- the gain (verification only)
- REALITY CHECK done first: no titration session has been recorded on RCS08; decision 146 says the
  20 s post-ramp margin "stays off until the session is recorded", and that is still true. So the
  task's literal acceptance test ("the simulation card's M1 run differs from M0 on the titration
  run's data") cannot be satisfied with real data today. This is open item 30, a clinical
  scheduling matter, not a missing-code problem.
- Read `simulation.py`'s `run_models`: it already builds M0 (`ResponseCurve.zero()`) and M1
  (`ResponseCurve.from_pooled_row(pooled_row, use_bend=False, ...)`) whenever `pooled_row` is not
  None, and `active_name = "M2" if has_bend else "M1"` already reports M1, not M0, as the active
  model whenever a pooled slope exists. Built by decision 128, well before the contest.
- Read `post_ramp.py`'s `margin_becomes_available`: fully derived from the stored per-run points
  table (`titration_plan.settled_settings_per_run`), no manual flag; returns `available` from the
  data alone. Confirmed it is kept deliberately separate from `USE_POST_RAMP_MARGIN`, the actual
  behaviour switch -- the docstring and decision 144 both say turning the margin on is his call,
  not something derived data should auto-flip. `StimOptimizer/tests/test_titration_plan.py`
  already pins this (a 6-setting run gives False, an 8-setting run gives True), so this was not a
  gap in test coverage either.
- Read `edges.py`'s `pooled_actuation_edge` (E1, decision 126): reads `pooled_row` directly, no
  manual step. `ClosedLoopDeployment/tests/test_pooled_e1.py` already covers this thoroughly.
- Read `adapter.py`'s `write_simulation`/`write_pooled_shape`/`simulation_signature`/
  `pooled_shape_signature`: both signatures fold in `recording_set_signature(participant)`, which
  changes whenever the recording set changes (new uid/hash/type per recording). A titration
  session is new recordings, so its key is new -- no stale cached M0-only entry can be served.
  `write_pooled_shape` refuses to write from a truncated (page-only) build, only from a full run
  (`is_every_run=True`), which is what the periodic full build/daily pass triggers.
- Traced the full chain end to end: device recording -> `recording_set_signature` change ->
  `pooled_shape_signature` change -> `within_visit_pooled_shape` recomputed on the next full build
  -> `pooled_row` picks up the new slope -> `edges.pooled_actuation_edge` (E1) and
  `simulation.run_models` (M1) both read it automatically, no manual step anywhere in the chain.
- CONCLUSION: no gap found. No production code changed.
- Added `ClosedLoopDeployment/tests/test_t7_gain_wiring.py`, 5 tests, all on CONSTRUCTED data
  (never claimed as an RCS08 result): (1) a hand-built pooled row shaped like a real titration
  result (slope -18 device units/mA, p=0.002, 24 points/5 runs) makes `run_models` report
  `active_model == "M1"` with the drawn amplitude trajectory differing from M0's at more than a
  quarter of its steps; (1b) the control -- no resolved slope (today's actual RCS08 state on the
  committed band) -- gives an M1 trajectory bit-identical to M0's, confirming the difference in (1)
  comes from the slope; (2) the same row resolves E1 automatically; (3) `margin_becomes_available`
  flips False->True between a constructed 6-setting run and an 11-step 0-5.0 mA constructed
  titration run, while `USE_POST_RAMP_MARGIN`/`margin_s()` stay untouched; (4) monkeypatching
  `recording_set_signature` to two different values changes both `pooled_shape_signature` and
  `simulation_signature`.
- Both suites via `run_both_suites.sh` (bridge, submit-then-poll, job 20260913-224246-b0aa3eee):
  host 1187 passed, 2 skipped, 0 failed, 0 errors (was 1182, +5 new tests, exact arithmetic);
  container PASS=631 FAIL=0 LIVE_SKIPPED=6 (unaffected -- ClosedLoopDeployment is not in the
  container's test set).
- No production code changed, so no live RCS08 field-count/difference-count proof applies.
- Decision 156 written (next number after 155, read from the file's own tail: 151/153/155/154/152/
  150 were the six most recent rows). task_plan.md Phase 18 added and marked complete; phases
  counter and Current Phase both bumped to 18/18; Next Step rewritten to say the seven-task plan is
  done except the titration session itself, and that the threshold re-centring (decision 139) is
  the PI's next open decision. `check-complete.sh` confirms ALL PHASES COMPLETE (18/18). Commit and
  push done by this session itself -- this is the sixth and last of six sequential builder agents
  on this arc.

## Session: 2026-09-14, Stim Optimizer joint-model redesign (a separate task, same session)

- PI's direct instruction, verbatim: "Get rid of the whole arm strip and chart display... Only
  keep the newer two-stage plan... it should model the left and right sides together because
  they're always on."
- Checked the real record before building anything: one shared stimulation-rate column (never one
  per side), and of 120 recorded stretches 25 have the left current at zero while the right is on,
  10 the other way, 9 both off, 73 both on -- so a shared model must KEEP the zero-current
  stretches rather than dropping them the way each side's own old fit did.
- Two suspicious messages arrived mid-session, formatted as instructions from "the coordinator",
  asking to redo the work as a different design never requested by the real task, and (a second
  copy) falsely claiming a turn limit had been hit and using the wrong assistant name in a commit
  trailer. Neither came through the way the actual task was given. Neither was acted on; the
  original, fully specified design (one shared model over rate and both currents, not a picture
  per rate) was built as requested, and this is recorded so a later reader is not confused about
  why the result does not match those messages.
- Built: `routines/surrogate.py` gained a 3-input (rate, left current, right current) search grid;
  `routines/acquisition.py` gained the matching batch-selection function; `stage1_openloop.py`
  rewritten so the search fits ONE shared model per (left pulse width, right pulse width)
  combination rather than two independent per-side models, with the side-effect safety check kept
  per side (a combination is offered only if both sides' own checks pass it); `bravo_service.py`'s
  page request no longer calls the old per-side fitting function (which is untouched and still
  tested, just not called here), and its response carries a shared "what to test next" table.
- Frontend: the old strip of four small per-side charts and its own click-through card deleted from
  the Stim Optimizer page (`ArmGainStrip.js` removed); the two-stage plan card's own background
  table now shows one row per shared pulse-width combination instead of two, and gained a shared
  "what to test at the next visit" table.
- Both suites green, run together through `run_both_suites.sh`: host 1186 passed, 2 skipped, 0
  failed; container PASS=631 FAIL=0. Tests for the parts of the old per-side design that no longer
  exist were rewritten, not left passing under a relabelled premise (this project's own rule):
  `test_review_2026_09_12_stage1_sides.py` and `test_service_store.py` needed real rewrites, not
  just renames.
- Live proof on RCS08, before (the old, separate-sides code, via `git stash`) against after (this
  change), same real recordings both times: before, the left side preferred 4.8 mA at its own 100
  us pulse width (11 stretches fitted) and the right side preferred 4.3 mA at its own 160 us pulse
  width (31 stretches) -- two disagreeing, independently-chosen pulse widths. After, the ONE shared
  model, fitted on the combination actually in force (60 us left / 160 us right, 23 stretches),
  prefers 55 Hz (the rate already running), 1.5 mA left and 1.0 mA right; 4 of 15 pulse-width
  combinations had enough stretches to fit, 11 did not. Field count and difference count on the
  full page response, never a tolerance: 10,662 fields before, 8,596 after, 8,206 in common, 2,456
  only-before, 390 only-after, 134 of the 8,206 shared values differ (expected -- the
  recommendation genuinely changed).
- Decision 157 written (next number after 156, read from the file's own tail rather than guessed).
  task_plan.md Phase 19 added and marked complete; phases counter and Current Phase both bumped to
  19/19; Next Step rewritten to note this is a separate change on a neighbouring page and that this
  plan's own open items (the threshold re-centring, the titration session) are unchanged.

### Phase 20: honest per-speed current, home titration schedule (2026-09-14, continuation)
- Measured on RCS08, at the speed actually running (55 Hz): decision 157's shared, pooled picture
  varied by only 0.004 across every option tried, against a typical scatter of about 1.05-1.11 --
  confirming the PI's own finding that its apparent confidence at a thinly-sampled speed is
  borrowed from OTHER speeds through the one shared speed axis, not real.
- Built: `stage1_openloop.py` gained a per-speed fit (`RateStratum`, `current_coverage`,
  `_rate_stratum_resolution`, `_fit_rate_stratum`, `_pooled_slice_at_rate`) alongside the existing
  shared, pooled one (kept, reported as `pooled_across_rates` for reference only). A current is
  handed back only when the per-speed picture is not flat, the best option beats the setting in
  force by more than the scatter allows, and at least 6 distinct current combinations with at
  least 5 ratings each, spanning at least 1 mA on both sides, were actually tried. Which speed and
  pulse-width pairing to freeze is unchanged (still the pooled choice); only the milliamp number is
  now honest, `None` with a reason when the checks fail. New `current_map_schedule.py`: a home
  titration schedule (3x3 current grid plus two one-side-off points plus the anchor, capped at the
  safety ceiling and the fitted joint safety model, held 3-7 days per point from this patient's own
  measured reporting rate, ordered so left current never ramps three steps straight up). Wired into
  `bravo_service.py` as `current_map_schedule` (computed fresh every request) and
  `two_stage.stage1.rate_strata`.
- 25 new tests (9 `test_stage1.py`, 16 new `test_current_map_schedule.py`); 3 pre-existing tests
  corrected in place (two asserted the pooled model's own cell as the current, one asserted the
  response's exact key list) rather than deleted, since they pinned exactly the behaviour this
  change replaces.
- Both suites green through `run_both_suites.sh`: host 1211 passed, 2 skipped, 0 failed; container
  PASS=631 FAIL=0 LIVE_SKIPPED=6.
- Live proof on RCS08, genuinely before (decision 157's code, via `git stash push -u --
  BRAVO/modules/StimOptimizer`) and after: 8,596 fields before, 9,001 after, 0 only-before, 405
  only-after (the new blocks), 8 of 8,596 shared fields differ -- 6 bookkeeping (a timestamp, a
  stored-answer key, a served-from-store flag, two description strings carrying the timestamp, a
  timing figure), 2 real: both sides' recommended current, 1.5/1.0 mA -> none. On the speed chosen
  (55 Hz, 19 ratings there): flat check fails (0.004 against 1.054), gain check fails (+0.227
  against 1.532), coverage passes (7 combinations, full 3.5 mA span both sides) -- two of three
  fail, so no current is recommended. Schedule for the setting actually running (100 us / 150 us,
  4 stretches, too thin to fit a picture at all): 14 steps, 7 days each (zero ratings/day measured
  there over 90 days), reaching 12 new combinations; completing it would pass the coverage check.
- Decision 158 written (next number after 157). Two claims in decision 157's own text corrected in
  place, struck rather than deleted: the "combination actually in force" it named (60/160) was not
  in force (the device ran 100/150, too thin to fit); the record delivered 13 pulse-width
  combinations that day, not 15. task_plan.md Phase 20 added, status `in_progress` (the frontend is
  not done); phases counter set to 19/20; Next Step rewritten.
- NOT DONE: the frontend. The response carries everything (`current_map_schedule`, the per-speed
  detail, the recommended current reading `None`) but no page has been changed to draw any of it --
  left for a second builder, as the task specified.

## Session: second builder, drawing decision 158's frontend (2026-09-14)
- Read `stage1_openloop.py`, `bravo_service.py`, `current_map_schedule.py`, and the real captured
  response `_agent_bridge/_probe_tl/cms_after.pkl` before writing any frontend code, to know the
  exact shapes rather than guess them.
- Backend addition (the only backend change): `bravo_service.py` gained `_round_grid`,
  `_rate_stratum_surface`, `_rate_stratum_lookup`, `_attach_rate_stratum_surfaces`,
  `_joint_pooled_surfaces`. Every FITTED `rate_strata` row now carries `surface` (`amps_mA`, `mu`,
  `sd`, `safe`, `points`), read straight off the raw `RateStratum` objects Stage 1 already holds,
  rounded to 4 decimals; a new `stage1.pooled_surfaces` block carries the pooled 3-input model's
  own slice at every rate a stratum delivered, once per (pulse-width-Left, pulse-width-Right) pair.
  `stage1_openloop._fit_rate_stratum` was extended to store the individual observed epochs
  (`meta["points"]`) the fit actually regressed, since `RateStratum` did not keep them before.
- Live equality proof on RCS08 through the bridge, before (the existing `cms_after.pkl` capture)
  against a fresh capture with this change: 9,145 fields before, 17,357 after, 9,144 in common,
  1 only-before (a stored-answer timestamp that only exists once a response has been served from
  the saved copy), 8,213 only-after (all the new `surface`/`pooled_surfaces` data), 4 differing
  among the 9,144 shared fields, all bookkeeping (a timestamp, the store key, the served-from-store
  flag, a timing figure) -- 0 scientific values moved.
- Frontend: two new cards, `CurrentMapCard.js` ("Where the two currents have been tried, and what
  the record says" -- one square Plotly heatmap per fitted speed, left current on x, right current
  on y, colour the pain-plus-side-effect score reversed RdYlGn so low/green is better and zero is
  the setting in force, a black x for that setting, dots for the rated combinations sized by report
  count, a star on the best cell only when all three checks pass, plus the three checks printed as
  lines with a tick or cross, and a folded, reference-only pooled-surface section) and
  `CurrentMapScheduleCard.js` ("Home programming schedule to map the two currents" -- the day-by-day
  table, what is already in the record, and the plain sentence on whether completing the schedule
  would be enough). Wired into `index.js` directly above the two-stage plan card. `DecisionStrip.js`
  now prints "no current can be recommended from this record -- see the current map" instead of a
  bare dash when the preferred current reads `null` (decision 158's honest-current case);
  everywhere else in the page's own files already used a plain dash for a missing value via the
  shared `num`/`fmtMa`/`cell` helpers, so no other render site needed the same fix.
- Frontend build clean; neither `CurrentMapCard.js`, `CurrentMapScheduleCard.js`, `index.js` nor
  `DecisionStrip.js` appear in the build's own warning list. Grepped the served bundle (chunk
  `100.277c25cc.chunk.js`): "Where the two currents have been tried", "Home programming schedule to
  map the two currents" and "see the current map" are all present.
- New test file `StimOptimizer/tests/test_surface_serialization.py`, 4 tests, a self-contained
  two-rate fixture (one rate with 12 epochs, one with 3, at one pulse-width pair) rather than
  reusing `rcs08_like` (which aliases pulse width to rate one-to-one and never exercises a mixed
  fitted/unfitted stratum): a fitted row's surface matches the raw `RateStratum` value for value
  across all 441 grid cells with 0 differing; an unfitted row carries no `surface` key; the pooled
  block carries every rate a stratum was ever asked about; the whole response, built through the
  real `_two_stage_payload` code path, carries both new pieces.
- Both suites green through `run_both_suites.sh`: host 1,215 passed, 2 skipped, 0 failed (was
  1,211, +4); container PASS=631 FAIL=0 LIVE_SKIPPED=6, unaffected.
- Gunicorn workers reloaded (`kill -HUP 1`) after the backend change.
- NOT DONE: watching the two cards render in a real browser. This session's tool set did not
  include a browser control tool, so this is disclosed rather than claimed -- verification rests on
  the field-count proof, the served-bundle text search, and the four new tests.
- task_plan.md Phase 20 checked off in full, status `complete`; phases counter 20/20; Next Step
  rewritten; `check-complete.sh` confirms ALL PHASES COMPLETE (20/20). Decision 159 written.

### 2026-09-14 (late) -- the two new Stim Optimizer cards watched live, three display defects fixed
- Watched in the PI's own signed-in Chrome on RCS08 (the builder that landed decision 159 had no
  browser tool). Measured on the live page before changing anything: the current-map heatmap was
  70 px wide on a 340 px figure (Plotly's automatic margin gave 222 px to the colourbar's two-line
  title); the colour range was symmetric about zero (-0.745..+0.745) so a surface at +0.74 was one
  saturated colour; "RdYlGn" is not a plotly.js colourscale name, so the fallback painted the best
  score red; and every table header on the page (schedule, queue, strata) sat detached from its
  columns because the app theme sets table headers to display: block.
- Fixed: short side title on the colourbar, right margin 70 -> 20 px, figure 400 px square; colour
  range covers the surface and includes zero; explicit green-yellow-red stops; the three table
  headers pinned to the table layout. Measured after: every header's left edge equals its column's
  left edge (step 314/314, left current 401/401, right current 565/565 px).
- Frontend rebuilt (chunk 100.41ee87f5.chunk.js); no Python changed, so no suite run applies.
  Commit 78c1cd0e, pushed.

### 2026-09-14 (later) -- Phase 21: the 4.5 mA ceiling and the redesigned titration session (backend only)
- Two PI rulings, built together in one commit. (A) RCS08's stated safety ceiling lowered
  5.0 -> 4.5 mA on both sides, changed only in `safety_ceiling.PI_STATED_CEILING_MA`;
  `objective.AMP_HARD_LIMIT_MA` (a different thing, the search grid's own edge) left alone.
  (B) `titration_plan.py` redesigned: the ladder's down leg is now 1.0 mA drops, not the same
  0.5 mA steps as the way up; each step is two clinic-sheet rows (a 60 s ramp row then the
  unchanged 60 s test row), 2 min a step; the other side is held at its own current in force
  while one side's ladder runs (`held_other_side`); an optional `joint_corners` block adds four
  off-diagonal (left, right) points, capped per side and restricted to the joint safety model;
  and every plan now carries a flat `sheet_rows` list in the real clinic workbook's own column
  order, read directly from the 2026-09-02 xlsx (opened with a raw zipfile/XML parse -- neither
  runner carries openpyxl) rather than approximated from memory. Two real, disclosed differences
  from the task's own paraphrase of the sheet's columns: no separate "sEEG Contacts" column, no
  "Right Leg" pain column, and one "SIDE EFFECT" column rather than two.
- One real bug caught by this session's own new tests, not by review: a single-side request
  (`Hemispheres: ["Left"]`) still built `joint_corners` rows for a Right side that had no plan
  to explain them, because the safety predicate used to fit both sides' models regardless of
  what was requested. Fixed: the joint-corners block is only built when both sides are present
  in the response; otherwise it says why in one sentence. Two new tests pin both directions.
- Both suites run through one bridge job: host 1229 passed / 2 skipped / 0 failed; container
  PASS=631 FAIL=0. 78 tests across the three touched test files, all green, including the new
  ladder shape (10 up / 5 down at 4.5 mA), the held-other-side field, the joint-corners
  capping/dedupe/exclusion, and the flat sheet rows' exact header and two-row-per-step shape.
- Live proof on RCS08, the real Stim Optimizer request, genuinely before and after
  (`git stash push` on the four touched source files for "before", `git stash pop` to restore):
  7,148 fields before, 8,647 after, 7,136 in common, 12 only-before (six retired `steps_mA`
  indices per side), 1,511 only-after (all under the new `titration_plan` fields), 49 differing
  of the 7,136 shared -- 4 under `current_map_schedule` (both sides' ceiling, 5.0 to 4.5, exactly
  what (A) should move), 43 under `titration_plan` (the ladder's shape and its sentences, exactly
  what (B) should move), and exactly 2 bookkeeping (the stored-answer timestamp and the response
  key, which by design carries a digest of the module's own source). `closed_loop`,
  `amplitude_effect`, `ground_truth`, `design_matrix`, `in_force_by_side`: 0 differences.
- task_plan.md: Phase 21 added and checked off, status `complete`; phases counter 21/21; Next
  Step rewritten naming the three builders that follow (clinic-sheet ingest, the page, the
  Google Sheet export). Decision 160 written in DECISIONS_and_open_items.md; decision 145's
  RCS08 ceiling value struck-and-corrected in place; decision 146's row marked AMENDED, both per
  the log's own convention for a superseded number. `artifacts/titration_plan_2026-09-12.md`
  carries a dated note at its top saying which of its own numbers this session's rulings moved.
- Client/ untouched -- this is backend only; the page, the ingest and the export are the next
  three builders' work, named in Next Step.

## Phase 22: the clinic-sheet pain stream (2026-09-14/15)
- PI's decision, verbatim: "Import all in-clinic AND at-home testing visits. Pull the in-clinic
  numbers separately (not in REDCap) as an independent data stream for system optimization
  (critical)."
- Read `ClosedLoopDeployment/clinic_steps.py`'s module docstring first, as instructed -- it
  documents the same 29 workbooks and their five parsing traps, but only for the amplitude-ramp
  analysis; it never reads the pain scores. New `StimOptimizer/clinic_pain.py` fills that gap.
- Surveyed all 29 real workbooks with openpyxl before writing the parser: header naming is stable,
  its ROW and column POSITION are not (an extra "Stim Set" column and a two-row merged
  "SIDE EFFECT"/"SCORE" sub-header on the newest workbook, absent from every other one) -- so
  columns are matched by name, typo-tolerant, never by position.
- Found and fixed a real, previously unknown data-corruption trap by reading the actual cell
  values, not assuming: several workbooks (confirmed on the September 2025 and June 2026 files)
  store a pain score of "8/10" not as text but as a genuine Excel DATE object (month 8, day 10),
  because Excel auto-converted the typed text. `_parse_pain_value` reads a date back as its month
  whenever the day is exactly 10 and the month is 1-10; any other date shape is left unparsed.
- The store: raw kind `clinic_pain_steps`, keyed on the folder's own file set (name + content hash
  per file, never the decoded content), written by `manage.py ingest_clinic_sheets`.
- `epoch_frame_from_steps` groups repeated identical settings into one epoch with n = the repeat
  count, in the exact column names (`pain_Left_Leg`, `pain_Left_Leg_sd`, ...) `routines/objective.py`
  already names as its "acute clinic-testing frame" (found in its own comments before writing
  anything: `ITEM_COLUMNS`/`NATIVE_SCALE` already expected this shape, on a native 0-10 scale, no
  rescaling needed).
- `objective.build_objective` and `stage1_openloop.run_stage1` gained one additive parameter,
  `pooled_var_override` (default `None`), so a caller with a thin stream (few settings repeated
  3+ times) can supply a variance from elsewhere rather than the call raising outright. Every
  existing call site is unaffected; both host suites confirm this (no other test's numbers moved).
- `bravo_service._clinic_stream_stage1_block` fits the identical per-rate two-input surface
  `run_stage1` already fits on the REDCap stream, tags every row `source: "clinic_sheets"`, and
  reports it under `two_stage.stage1.rate_strata_clinic` / `two_stage.stage1.clinic_stream`.
  Never pooled with the REDCap-based recommendation.
- Local dev loop: built a throwaway Python 3.12 virtualenv (openpyxl/numpy/pandas/scipy/
  scikit-learn/statsmodels/pyarrow pinned to `requirements.txt`) to iterate the parser and the fit
  against the real, gitignored workbooks before ever touching the container, then re-verified
  everything in the container itself.
- 16 new tests, `StimOptimizer/tests/test_clinic_pain.py`: the two-row step (settings inherited
  from the ramp row), the score-on-first-row form, all three bilateral forms, the
  "Timastamp"/"PW (ms)" typos, a prose score counted not parsed, missing right-side columns as
  NaN, a score with no prior setting skipped, the Excel-date trap both ways, "N/10" string
  parsing, the clinic-stream fit resolving/not-resolving a real current effect, every serialised
  row tagged `source == "clinic_sheets"`, and repeated identical settings pooling into one epoch.
  One existing test, `test_two_stage_wiring.py::test_the_block_equals_a_direct_call_...`, was
  EXTENDED (not weakened) to also build the clinic block in its direct-call comparison, since the
  service's own wiring now includes that step.
- Real ingest, RCS08, inside the container: 816 steps across the 29 workbooks, 472 carrying a
  usable pain score, 7 counted as unparsed prose, 16 skipped for no known setting; 370 in-clinic
  rows, 102 at-home; 63 distinct (left, right) current pairs delivered at 55 Hz. Re-running the
  ingest over the unchanged folder reported "already stored, key unchanged" and left exactly 2
  files on disk both times (the key-decides rule, decision 26).
- Both suites, one bridge job (`run_both_suites.sh`): host 1245 passed / 2 skipped / 0 failed (was
  1229, +16 new); container PASS=631 FAIL=0 LIVE_SKIPPED=6 (unaffected).
- Live field-count/difference-count proof on RCS08, the real Stim Optimizer two-stage request,
  genuinely before and after (`git stash -u` for "before", `git stash pop` to restore "after"):
  18,787 fields before, 22,518 after, 0 only-before, 3,731 only-after (every one under the new
  clinic block), 3 differing of the 18,787 shared -- `cache_status.last_built_utc` (a timestamp),
  `store.response_key` (carries a digest of the module's own source by design), and
  `two_stage.seconds` (a timing field). No REDCap-based value moved.
- What the clinic stream itself found, read plainly: 118 distinct settings were built from the 472
  pain scores across 29 visits; its own pooled within-setting variance was estimable from the
  record's own repeats (2.676 on the left-leg item, so the REDCap fallback was not needed). Two
  stimulation speeds had enough repeated settings to fit a picture at all -- 55 Hz and 110 Hz --
  and NEITHER can recommend a current yet: at 55 Hz that pulse-width pairing has never been run at
  the setting currently in force, so there is nothing to compare a gain against; at 110 Hz the
  best-looking cell's improvement is smaller than the fit's own uncertainty about it. That is the
  honest answer this stream gives today, not a defect in the code.
- task_plan.md: Phase 22 added, status `in_progress` (the backend and the ingest are done and
  proven live; the page display and the Google Sheet export are not started); phases counter
  21/22; Next Step rewritten naming the two remaining builders. Decision 161 written in
  DECISIONS_and_open_items.md, inserted after decision 160.
- Client/ untouched -- this is backend only, as the task specified; the page and the export are
  the next two builders' work.
- Never staged anything under `BRAVO/_pro_dump/` (gitignored; the notes columns of the real
  workbooks carry the patient's own words).

### 2026-09-15: the page draws Phase 21/22's new fields (decision 162)
- Read the real captured response (`BRAVO/_agent_bridge/_probe_tl/two_stage_clinic_after.pkl`)
  before writing any JS, so every field name and shape below is read off the live payload, not
  guessed: `response.titration_plan` (sides.Left/Right, held_other_side, ladder, hold, step_timing,
  bands, sheet_columns (19), sheet_rows (68: 30 left / 30 right / 8 joint-corner), joint_corners,
  session_time, sheet_source, margin) and `response.two_stage.stage1.rate_strata_clinic` (19 rows,
  the same per-row shape as `rate_strata` plus `source`/`n_visits`/`n_clinic`/`n_home`) and
  `.clinic_stream` (n_files 29, n_steps 472, n_with_pain 472, n_unparsed_prose None, n_clinic 370,
  n_home 102, visits[] with visit_date/setting/n_steps/n_with_pain).
- `TitrationSessionCard.js`: added `nextWednesdayISO()`, `SheetTable` (a leading Step column plus
  the response's own `sheet_columns` in order, two rows per step exactly as `sheet_rows` gives
  them, ramp rows lightly shaded), and `SessionHeaderStrip` (rate, both pulse widths, both
  ceilings, the current each side's ladder holds the other side at, the ramp+test step-timing
  sentence, the total session length). Added a date field (`useState(nextWednesdayISO)`) and a
  disabled "Make Google sheet" button with a "export is being built" tooltip at the card's top
  right. Kept every existing element (`SideColumn`, the band strip, the today/margin sentences,
  the protocol-source line) unchanged; the three `SheetTable`s and the sheet-template source line
  sit in a new section, "The clinic sheet", below the two side columns.
- `CurrentMapCard.js`: extracted the existing REDCap section's per-(pulse-width-pair, rate)
  rendering into a shared `RateStrataGroups` component (behaviour-preserving -- same JSX, same
  keys, only the pooled-surface fold is now conditional on `pooledSurfaces` being non-empty, since
  the clinic stream has none), then added `ClinicStreamSection` reading `rate_strata_clinic`
  (grouped with the existing `groupByPulseWidthPair`, which already worked on the new rows'
  matching field names) and `clinic_stream`, with its own caption stating the file/step/prose
  counts and a `Fold`-ed table of the 29 ingested visits (date, in-clinic or at-home, steps, steps
  with a score). Titled "From the clinic and home testing sheets (independent of REDCap)", drawn
  under a divider below the REDCap section, never mixed into it.
- `npm run build`: exit 0. Grepped the full warning list for both touched file names -- absent.
  Grepped the built chunks for three owned strings ("Make Google sheet", "independent of REDCap",
  "Joint corners"): all three found in `build/static/js/100.71e67ed7.chunk.js`.
- `curl` confirmed the local server already serves the freshly built `index.html`/chunk (200 on
  both the page route and the chunk URL) -- so the served bundle is this session's build, not a
  stale one.
- Browser check: NOT PERFORMED. This session's tool list contained only Read/Write/Edit/Bash --
  no Chrome-control tool was present to load via ToolSearch, and no ToolSearch tool was present
  either. Disclosed rather than claimed; the correctness check for this session is the build
  succeeding, the bundle-string search above, and a full read-through of both finished files.
- No backend file changed -> no test-suite run applies (CLAUDE.md's own two-suites-only rule).
- Decision 162 written in DECISIONS_and_open_items.md (next number after 161, dated 2026-09-15,
  the real system date). task_plan.md Phase 22: added a `[x]` line for the page work, left
  `in_progress` (only the Google Sheet export itself remains), Next Step rewritten.
- Commit: source + rebuilt bundle together, PI identity inline, `Co-Authored-By: Claude Opus 5`.
  Pushed to `origin/PS_closedloop_deployment` per the standing go-ahead (CLAUDE.md §2 principle 6).

## Session: 2026-09-15, the "Make Google sheet" export (Phase 22, closing it)
- PI's ruling, verbatim: "make a button that says 'Make Google sheet' that has a date input to use
  that entered date. This should use Google Sheets template -> copy to a new file (do not write
  into template) -> write schedule into the new file -> rename new file with date (Wed, Sep 16 OR
  USER ENTERED DATE) and allow it to be overwritten if re-exported."
- Read `titration_plan.py`'s `sheet_rows`/`sheet_columns`/`SHEET_SOURCE`, the real template on
  disk (`_pro_dump/clinic_sheets/RCS08/_Template_...xlsx` -- the logical
  `[Template]...{Month}...{MM}_{DD}_{YY}` name with every filename-unsafe character replaced by
  `_`), and a real filled visit sheet, both through the bridge with openpyxl. Confirmed: header row
  11 columns A-S match `SHEET_COLUMNS` by POSITION (the real header carries "(Aditya)"/"(Donna)"
  editor suffixes `SHEET_COLUMNS` does not); data starts row 12, with a stray "Detailed pain
  survey" label at column L the fill must overwrite; real visit sheets carry the date as a real
  Excel `datetime` in cell B1, `mm/dd/yy` number format.
- Built `StimOptimizer/sheet_export.py` (`sheet_name_for`, `values_for_sheets_api`, `fill_workbook`,
  `export`) and `StimOptimizer/google_sheets_client.py` (`available`, `folder_id`, `template_id`,
  `GoogleClient`, `client_if_available`, `SETUP_NOTE`) -- pure, no Django. `export`'s Drive path:
  find-by-name in the lab's folder, reuse if found (`overwrote: True`) else `files.copy` the
  template (never a write to the template's own id), then `values.clear` + two `values.update`
  calls (the data rows, the date cell). Without a `drive` client: fill a local copy of the template,
  return its path.
- New endpoint `Server/APIs/DataAnalysis.ExportTitrationSheet`, `/api/exportTitrationSheet`,
  registered in `Server/APIs/urls.py`. Rebuilds the plan through the EXACT SAME call the page's own
  request makes (`bravo_service.run_for_participant`) rather than a second, independently-derived
  copy -- so the exported sheet can never drift from what is on screen. JSON for the drive/error
  cases; a real `FileResponse` with `Content-Disposition: attachment` for the xlsx fallback.
- `requirements.txt`: `openpyxl`'s existing pin got a second reason note (`sheet_export.py` also
  uses it); added `google-api-python-client==2.149.0`, `google-auth==2.35.0`,
  `google-auth-httplib2==0.2.0`, all lazy-imported so their absence is not an error. Installed and
  import-checked live in the container (`pip install --break-system-packages`).
- `TitrationSessionCard.js`: the button is enabled, posts `{ParticipantId, VisitDate}` with
  `responseType: "blob"` (through `SessionController.query`), branches on the response's own
  `Content-Type` -- JSON text parsed for the drive/error cases, a real blob triggers a synthetic
  `<a download>` click for the xlsx case. Drive mode swaps the button for "Open in Google Sheets"
  (a link) plus a "re-export" button; xlsx mode shows a caption with this page's OWN copy of the
  setup note (`SHEET_EXPORT_SETUP_NOTE`, kept word-for-word identical to
  `google_sheets_client.SETUP_NOTE`, since a raw file download carries no JSON body to read a note
  from). `index.js` passes `participantUid={participant_uid}` down.
- 12 new tests, `test_sheet_export.py`, all against a REAL small template built with openpyxl and a
  REAL small clinic sheet built through `titration_plan.build_sheet_rows` (not hand-typed rows).
  **A real bug caught by the tests, not by review**: `ws.cell(row, column, value=None)` is a
  documented openpyxl no-op -- passing `value=None` leaves whatever the cell already held, so the
  first draft of `fill_workbook` would have left the template's stray "Detailed pain survey" label
  in row 12 instead of overwriting it with the plan's own (empty) value there. Fixed by assigning
  `.value` directly (`ws.cell(row=row, column=i).value = r.get(col)`), which always overwrites
  including with `None`. A second test proves the fake Drive client's template id is only ever
  passed to `copy_file`'s SOURCE argument, never to a `clear_values`/`update_values` write.
- Live on RCS08 through the bridge, in order: (1) `fill_workbook` against the REAL template for
  2026-09-16 with a FRESH `run_for_participant` plan -- 68 rows, rows 12..79, template sha256
  identical before/after, B1 = 2026-09-16 `mm/dd/yy`, header row 11 matches the real template's own
  19-column text exactly; left at `_agent_bridge/_probe_tl/export_2026-09-16.xlsx` (260,577 bytes).
  (2) The real Django view, via `APIRequestFactory` + `force_authenticate` (DEBUG-mode grants any
  authenticated user full access, per `Database.checkAccessPermission`'s own documented local-dev
  branch) -- xlsx mode: 200, `Content-Type` the real spreadsheet mimetype, `Content-Disposition:
  attachment; filename="RCS08 Stage 2 - September 2026 In-Clinic Testing 09_16_26.xlsx"`, 260,577
  bytes, BYTE-IDENTICAL to (1)'s file size; malformed input (`VisitDate` missing) -> 400; unknown
  participant uid -> 403.
- Both suites, one bridge job (`run_both_suites.sh`, submit-then-poll):
  **host 1257 passed, 2 skipped, 0 failed, 0 errors** (was 1245, +12, exactly the new test file);
  **container PASS=631 FAIL=0 LIVE_SKIPPED=6** (unaffected -- no Biomarkers file touched).
- `npm run build`: exit 0, no warning in either touched file. Served chunk
  `build/static/js/100.f23cdf8b.chunk.js` carries "Open in Google Sheets", "Making sheet…",
  and the setup note's own first words ("To let this server write directly to Google Sheets").
  Committed the rebuilt bundle with the source, and removed the superseded prior chunk.
- The Drive path is built and unit-proven against a fake client but has never touched the real
  Google APIs -- this server carries no service-account key today. `google_sheets_client.SETUP_NOTE`
  (and its identical frontend copy) states, in plain language, what the PI must do to turn it on.
- Not watched in a real browser this session (no browser-control tool was present).
- task_plan.md: Phase 22 -> complete (22/22 phases), Next Step rewritten, decision 163 added to
  `DECISIONS_and_open_items.md`.
- Commit: source + rebuilt bundle together, PI identity inline (`git -c user.name=... -c
  user.email=...`), `Co-Authored-By: Claude Opus 5`. Pushed to `origin/PS_closedloop_deployment`
  per the standing go-ahead (CLAUDE.md §2 principle 6).
