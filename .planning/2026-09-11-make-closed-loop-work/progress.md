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
