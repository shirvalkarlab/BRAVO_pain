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
