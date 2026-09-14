# Test audit, 2026-09-12: the Stim Optimizer module

**What this is.** A read-only classification of every test under
`BRAVO/modules/StimOptimizer/tests/` (21 files counted with `wc -l` today, 8,230 lines including a
7-line `conftest.py`; 501 test functions counted with `grep -c '^def test_'` across the 20 test files).
Nothing was run except one 0.03-second check inside the container (whether the PyTorch libraries are
installed; they are not) and nothing was deleted. Every test body was read, and every function a
test calls was checked for production callers with a search across `BRAVO/modules` and `BRAVO/Server`,
leaving out every `tests/` directory and `BRAVO/_agent_bridge`.

**The one-line answer.** 200 of the 501 tests are sound: they call code the running platform reaches
and check a value. **285 test code that nothing in the running platform calls**, and most of those
belong to one designed-but-never-wired subsystem (the "two-stage" open-loop-then-closed-loop path and
its BoTorch/ordinal-safety backend). 8 pin a snapshot of RCS08's findings from 2026-09-02 that the
decision log has since moved past. 3 check only a signature or an exception, 1 is misnamed, 3 are
duplicates, 1 needs a file that is not on disk anywhere. **Nothing here should be deleted on this
report's say-so**; the two lists at the end say what is safe and what should be rewritten instead.

**How the classes were applied.** KEEP means the test reaches code the running platform actually
calls and checks a value. DEAD-TARGET means the function, branch or field it tests has no caller
outside the tests (the callers found, or "0 callers", are named on each line). SUPERSEDED-RULE means
the test pins a rule or a finding the decision log has since reversed. SHAPE-ONLY means the test
checks only that something is present, has a signature, or raises, and never checks a number or a
verdict. MISNAMED means the name promises something the body does not check. DUPLICATE means another
named test pins the same thing. LIVE-DATA means the test needs a file or the container and skips
otherwise.

---

## What the running platform actually reaches, measured before classifying anything

This is the map every DEAD-TARGET line below rests on. It was built by searching for each name
across `BRAVO/modules` and `BRAVO/Server` with tests and the scratch area excluded.

**Reached from the page.** The Stim Optimizer page's request (`Server/APIs/DataAnalysis.py:1941`)
calls `StimOptimizer.bravo_service.run_for_participant`, which reaches: the settings stream and the
design matrix (`adapter.py`); the flat per-arm fit (`pipeline.run`, which calls `plots.build_context`,
and through it `objective.build_objective`, the numpy surrogate `surrogate.ParameterGrid`,
`ObjectiveGP` and `SafetyGP`, the preference model (illustrative only, figure 4),
`acquisition.exploration_queue`, `select_batch_within_visit` and `expected_improvement`, and
`acquisition.check_stopping`); the resolution rule (`resolution.py`); the closed-loop readiness
block (`pipeline.live_evidence`, which calls `adapter.evidence_for_participant`,
`lfp_evidence.build_all`/`screen_cells`/`select_for` and `lfp_response.assess_response`); the
amplitude-effect and ground-truth readers (through `percept_adaptive` constants); and the five
Plotly figures.

**Reached from the Closed-Loop Deployment module.** `within_visit` (only `amplitude_response_shape`,
`amplitude_response_shape_pooled`, `rising_current_settings`, `mean_power_before_next_change`,
`CHUNK_S`, `PRE_CHANGE_WINDOW_S`; `build_all_within_visit` is called by
`ClosedLoopDeployment.adapter.amplitude_response_cached`, which decisions 85 and 101 record as
having no caller of its own); `amplitude_response`; `percept_adaptive` (`MODES`, `DUAL`, `SINGLE`,
`ADAPTIVE_LFP_BAND_HZ`, `MIN_ADAPTIVE_RATE_HZ`, `recommend_threshold_mode`, `timing_plan`,
`estimate_response_latency`, the settle and titration constants); `lfp_evidence.screen_cells`;
`lfp_response.assess_response` and `MIN_CAPTURE_SEPARATION_D`; and `adapter` (`evidence_inputs`,
`settings_stream`, `PRO_ITEMS`, `exposure_epochs`).

**Reached by nothing outside the tests.** `pipeline.run_two_stage` and `run_two_stage_live`,
`stage1_openloop.run_stage1`, `stage2_closedloop.run_stage2`, all of `routines/stage_gate.py` except
the `LfpEvidence` data holder and `ADAPTIVE_BAND_HZ`, all of `routines/session_analysis.py`,
`routines/schedule.py`, `routines/safety_ordinal.py`, `routines/surrogate_torch.py`,
`routines/validation.py` and its two helpers. `pipeline.run_two_stage_live`'s own docstring says so
in its own words: "the ONLY callers of `run_two_stage` and `run_stage2` anywhere in the repository
were tests, and the endpoint layer never invoked the staged path at all." None of these names appears
in `DECISIONS_and_open_items.md` (searched for "two-stage", "stage_gate", "safety_ordinal",
"session_analysis", "surrogate_torch": 0 hits). `ARCHITECTURE_modules_and_store.md:596` lists
`run_two_stage` in a glossary of names only. The module's own `TWO_STAGE_DESIGN.md` opens with
"Status: implemented and tested", and its `BOTORCH_REFACTOR.md` closes with "Do not add PyTorch to the
production Django container. Keep it an optional dependency of a research environment, and keep the
scikit-learn backend as the default."

**Two facts about the suite itself that the summary numbers hide.**

1. **40 tests have never run where the suite runs.** 23 tests in `test_surrogate_torch.py` and 17 in
   `test_safety_ordinal.py` carry a skip mark that needs the PyTorch libraries. Checked through the
   bridge today: `torch`, `gpytorch` and `botorch` are all absent from the container (`find_spec`
   returned False for each; `pytest` returned True). With the one design-matrix file and the one
   clinic-sheet file also absent (see `test_stage2.py` and `test_session_analysis.py` below), that is
   exactly the "42 skipped" every host-suite run since decision 84 has reported. Those 42 have been
   counted as part of a green suite while checking nothing.
2. **The stopping rule can never stop.** `pipeline.run` hands `acquisition.check_stopping` a
   one-item history (`pipeline.py:268`, `[m["mu_star"]]`), while the plateau needs `k + 1 = 4` items
   and the ceiling needs 8 (`acquisition.py:247-252`). So `stop`, `plateau_met` and `truncated` are
   always False on the page, and the three tests that assert those states are testing branches the
   page cannot reach. This is a fact about the production code, recorded here because it decides how
   those tests are classified.

---

## Summary table

| File | Lines | Tests | KEEP | DEAD-TARGET | SUPERSEDED | SHAPE-ONLY | MISNAMED | DUPLICATE | LIVE-DATA |
|---|---|---|---|---|---|---|---|---|---|
| test_acquisition.py | 155 | 17 | 11 | 6 | 0 | 0 | 0 | 0 | 0 |
| test_adapter.py | 321 | 15 | 13 | 0 | 0 | 2 | 0 | 0 | 0 |
| test_core.py | 298 | 29 | 24 | 5 | 0 | 0 | 0 | 0 | 0 |
| test_lfp_evidence.py | 665 | 28 | 24 | 1 | 0 | 0 | 1 | 2 | 0 |
| test_lfp_response.py | 174 | 15 | 12 | 3 | 0 | 0 | 0 | 0 | 0 |
| test_percept_adaptive.py | 179 | 19 | 2 | 17 | 0 | 0 | 0 | 0 | 0 |
| test_pipeline.py | 196 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_resolution.py | 97 | 7 | 6 | 1 | 0 | 0 | 0 | 0 | 0 |
| test_schedule.py | 111 | 12 | 0 | 12 | 0 | 0 | 0 | 0 | 0 |
| test_separation_span.py | 123 | 10 | 0 | 10 | 0 | 0 | 0 | 0 | 0 |
| test_settings_store.py | 369 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_service_store.py | 408 | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_session_analysis.py | 755 | 42 | 0 | 42 | 0 | 0 | 0 | 0 | 0 |
| test_stage1.py | 411 | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0 |
| test_stage2.py | 564 | 32 | 0 | 30 | 1 | 0 | 0 | 0 | 1 |
| test_stage_gate.py | 524 | 41 | 1 | 33 | 7 | 0 | 0 | 0 | 0 |
| test_surrogate_torch.py | 849 | 33 | 0 | 33 | 0 | 0 | 0 | 0 | 0 |
| test_safety_ordinal.py | 413 | 32 | 0 | 32 | 0 | 0 | 0 | 0 | 0 |
| test_safety_and_evidence.py | 769 | 58 | 41 | 15 | 0 | 1 | 0 | 1 | 0 |
| test_within_visit.py | 842 | 41 | 20 | 21 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **8,223** | **501** | **200** | **285** | **8** | **3** | **1** | **3** | **1** |

**Tests likely to take more than 5 seconds** (from reading, not timing; the orchestrator runs the
suite): no file contains a sleep or a live-record load. The only candidates are the permutation tests
in `test_within_visit.py`, each of which fits a cluster-robust regression per band per shuffle:
`test_the_threshold_sweep_comes_from_one_permutation_loop_and_matches_separate_runs` (four runs of
200 shuffles over 18 bands, about 14,400 fits) is the longest, then
`test_a_localised_effect_is_detected_where_the_majority_rule_cannot_be_satisfied` and
`test_a_flat_panel_is_not_significant` (300 shuffles each, about 5,400 fits). `test_stage2.py` calls
the whole two-stage run in 10 tests (two surrogate fits plus a forward simulation each), likely one to
three seconds apiece. The `rate_model` fixture in `test_safety_ordinal.py` trains a variational
Gaussian process for 400 iterations, but it is skipped wherever PyTorch is absent, which today is
everywhere the suite runs.

---

## Per file: every test that is not KEEP

### test_acquisition.py (155 lines, 17 tests)

- `test_lcb_is_more_optimistic_with_larger_eta` -- DEAD-TARGET -- `acquisition.lower_confidence_bound`
  has 0 callers anywhere, not even inside `acquisition.py` (searched `BRAVO/modules` and
  `BRAVO/Server`; the only hit is its own definition at `acquisition.py:55`).
- `test_between_visit_batch_respects_separation` -- DEAD-TARGET -- `select_batch_between_visit` has 0
  callers outside tests; `surrogate_torch.py:553` names it in a docstring only. The page uses
  `select_batch_within_visit` (`plots.py:362`).
- `test_between_visit_is_more_spread_than_within_visit` -- DEAD-TARGET -- same function, same 0 callers.
- `test_plateau_alone_does_not_stop` -- DEAD-TARGET (branch) -- asserts `plateau_met` is True, which
  needs a history of at least 4 items; `pipeline.py:268` always passes 1, so the branch never runs live.
- `test_both_conditions_stop` -- DEAD-TARGET (branch) -- asserts `stop` is True; unreachable live for the
  same reason (a 1-item history can never satisfy the plateau).
- `test_ceiling_reports_truncated_not_converged` -- DEAD-TARGET (branch) -- asserts `truncated`, which
  needs `n >= max_batches` (8, or 3 with the config the test builds by hand); production only ever
  builds the default config and passes 1 item.

The eleven KEEP tests here cover the parts the page reaches: expected improvement, the exploration
fraction, within-visit batch selection, the safe mask, the exploration queue, and the coverage
condition, which is the one stopping condition a one-item history can evaluate.

### test_adapter.py (321 lines, 15 tests)

- `test_both_functions_take_the_argument_and_default_it_to_none` -- SHAPE-ONLY -- asserts only
  `p.default is None` and `p.kind is inspect.Parameter.KEYWORD_ONLY` on two signatures; no value is
  computed.
- `test_the_call_shapes_the_other_modules_use_still_bind` -- SHAPE-ONLY -- the body is five
  `inspect.signature(...).bind(...)` calls with no assertion at all; it passes if nothing raises.

The other 13 are sound: they count how many times the file parser is called and pin the numbers in the
design matrix (`[2.0, 3.0, 3.0]` amplitudes, `[6.5, 4.5, 2.5]` mean ratings).

### test_core.py (298 lines, 29 tests)

- `test_se_ladder_calibration_and_unreported_flag` -- DEAD-TARGET (half) -- calls
  `objective.side_effect_penalty` directly, which is only ever called inside the `se_severity` branch
  of `build_objective` (`objective.py:346-348`), and no design matrix the platform builds carries an
  `se_severity` column (`adapter.py`, `plots.py`, `pipeline.py`: 0 hits). **Protected**: the ladder is
  pre-registered in `OBJECTIVE_SPEC.md` section 2.3, which itself says "there is no structured
  side-effect severity field in the [record]" and "the ladder is collected prospectively from the first
  batch onward". A rule waiting for its data, like the reliable-change floor of decision 104.
- `test_moderate_and_severe_are_hard_infeasible` -- DEAD-TARGET (branch) -- builds the `se_severity`
  column by hand; same unreached branch, same protection.
- `test_objective_gp_refuses_infeasible_rows` -- DEAD-TARGET (branch) -- the refusal at
  `surrogate.py:174` fires only on a non-finite objective, which only the side-effect ladder produces;
  same protection.
- `test_head_is_excluded_with_a_reason` -- DEAD-TARGET -- `objective.EXCLUDED_ITEMS` is read by nothing
  (only its definition at `objective.py:130` exists); the assertion is `"head" in EXCLUDED_ITEMS and
  EXCLUDED_ITEMS["head"]`, membership and truthiness only.
- `test_prob_prefer_is_symmetric_and_bounded` -- DEAD-TARGET -- `PreferenceGP.prob_prefer` has 0
  callers outside tests (`preference.py:173` is the only hit). The preference model itself is reached
  only by `plots._fit_illustrative_preference`, whose own docstring calls figure 4 "ILLUSTRATIVE ...
  NOT patient preference".

### test_lfp_evidence.py (665 lines, 28 tests)

- `test_band_power_linear_is_still_there_for_its_other_callers` -- MISNAMED -- the name says the
  function is kept "for its other callers"; there are none. `band_power_linear` has 0 callers outside
  `lfp_evidence.py`, and its one internal use (`lfp_evidence.py:1060`) sits inside the retired
  decibel-density branch that no live caller selects (see the next line).
- `test_the_older_decibel_route_is_still_reachable_for_the_comparison` -- DEAD-TARGET -- the route is
  chosen by `band_power=BAND_POWER_DECIBEL_DENSITY`, which appears only at `adapter.py:441-552`; no
  caller passes it (`pipeline.live_evidence` and `ClosedLoopDeployment/adapter.py:828` both take the
  default). The adapter's comment keeps it "for the before-and-after measurement", a one-time
  comparison done on 2026-09-06.
- `test_the_call_shapes_other_modules_use_still_bind` -- DUPLICATE -- of
  `test_adapter.py::test_the_call_shapes_the_other_modules_use_still_bind`; both only call
  `signature.bind` and assert nothing.
- `test_the_stream_argument_still_stops_the_files_being_read_twice` -- DUPLICATE -- of
  `test_adapter.py::test_evidence_inputs_epochs_are_identical_whether_or_not_a_stream_is_passed`
  (which already counts one parse without a stream and zero with one) plus the signature half of
  `test_adapter.py::test_both_functions_take_the_argument_and_default_it_to_none`.

The other 24 are the strongest tests in the module: every cell carries a distinct number
(`100 + 10*row + column`), so reading the wrong row, column or route cannot pass, and the two
source-scanning guards refuse any new calibration constant by name.

### test_lfp_response.py (174 lines, 15 tests)

- `test_device_band_power_is_a_sum_of_squares_over_the_band` -- DEAD-TARGET -- `lfp_response.device_band_power`
  has 0 callers anywhere (`three_source_response.py` has functions with similar names,
  `read_device_band_power` and `device_band_power_in_window`, which are its own and do not call this one).
- `test_band_power_refuses_a_band_with_no_bins_and_bad_shapes` -- DEAD-TARGET -- same function.
- `test_derived_threshold_uses_the_device_formula_on_the_captures` -- DEAD-TARGET (field) -- the
  `derived_threshold` field is read only at `stage2_closedloop.py:257`, itself unreached;
  `screen_cells` does not report it and the Closed-Loop module reads none of it (grep of
  `ClosedLoopDeployment/*.py`: 0 hits).

### test_percept_adaptive.py (179 lines, 19 tests)

Only two tests here touch a value the running platform reads. The rest test a device-policy checker
(`validate_policy`) whose only caller is the unreached Stage 2 (`stage2_closedloop.py:143`), a
threshold formula (`derive_single_threshold`) with 0 callers, a band check
(`band_is_adaptive_capable`) whose only callers are in the unreached `stage_gate.py`
(lines 157 and 571), and eleven constants read by nothing. The live versions of these rules are in
`ClosedLoopDeployment/constraints.py` (a single neurostimulator, line 1547; band width, 1652;
polarity, 1807; rate and pulse width frozen, 2002; paused amplitude, 2083; contralateral sensing,
2164; the rate floor, 2257). One thing worth the PI's eye: `constraints.py:2257` enforces a 30 Hz
floor while `percept_adaptive.MIN_ADAPTIVE_RATE_HZ` is 55 Hz and is only *reported* in the optimizer
response (`bravo_service.py:747`), never enforced by anything that runs.

- `test_single_inverse_cannot_drive_therapy` -- DEAD-TARGET -- `can_drive_therapy` is read only inside
  `validate_policy`; 0 live readers.
- `test_single_threshold_derivation_matches_the_device_formula` -- DEAD-TARGET -- `derive_single_threshold`
  and `SINGLE_THRESHOLD_FRACTION`: 0 callers.
- `test_inverted_captures_are_refused` -- DEAD-TARGET -- `derive_single_threshold`: 0 callers.
- `test_whole_band_must_be_inside_the_adaptive_range_not_just_the_centre` -- DEAD-TARGET --
  `band_is_adaptive_capable`: callers only in `stage_gate.py`. The edge rule itself is live elsewhere
  (decision 83's `_deployment_summary_adaptive_band_gate` in Biomarkers; rule D08 in `constraints.py`).
- `test_the_selected_biomarker_bands_against_the_device_constraint` -- DEAD-TARGET -- same function;
  also a stale premise: its docstring says "the nrs band selected by the exploration scan sits at
  3.92 Hz", and decision 59 records that band moving to 0.95 Hz. The numbers are hard-coded, so the test
  keeps passing.
- `test_policy_validation_flags_limits_and_paused_amplitude` -- DEAD-TARGET -- `validate_policy`.
- `test_contralateral_drive_is_a_supported_configuration` -- DEAD-TARGET -- `CONTRALATERAL_DRIVE_SUPPORTED`
  read by nothing; assertion is `is True`.
- `test_adaptive_json_field_names_are_recorded` -- DEAD-TARGET -- `ADAPTIVE_JSON_FIELDS` read by nothing;
  membership only.
- `test_a_fully_specified_policy_passes` -- DEAD-TARGET -- `validate_policy`; also repeats the first
  assertion of `test_policy_validation_flags_limits_and_paused_amplitude`.
- `test_rate_below_the_adaptive_floor_is_refused` -- DEAD-TARGET -- three of its four assertions go
  through `validate_policy`; the fourth pins `MIN_ADAPTIVE_RATE_HZ == 55.0`, which is only reported.
- `test_missing_rate_is_refused_rather_than_defaulted` -- DEAD-TARGET -- `validate_policy`.
- `test_open_loop_rates_that_fail_closed_loop_are_named_as_such` -- DEAD-TARGET -- `validate_policy`.
- `test_two_neurostimulators_is_a_contraindication` -- DEAD-TARGET -- `validate_policy` and a constant
  read by nothing.
- `test_lfp_must_be_shown_to_respond_to_stimulation` -- DEAD-TARGET -- `validate_policy`.
- `test_indication_and_config_locks_are_recorded` -- DEAD-TARGET -- five constants
  (`ADAPTIVE_LABELLED_INDICATION`, `RATE_AND_PW_FROZEN_ONCE_BRAINSENSE_CONFIGURED`,
  `ADAPTIVE_EXCLUSIONS`, `BRAINSENSE_AUTO_DISABLED_DURING`) read by nothing.
- `test_device_band_power_definition_is_recorded_as_linear_sum_of_squares` -- DEAD-TARGET -- asserts two
  substrings of a sentence stored in `DEVICE_BAND_POWER`, which nothing reads.
- `test_the_55_hz_floor_interacts_with_the_selected_biomarker_bands` -- DEAD-TARGET -- `validate_policy`;
  same stale 3.92 Hz premise as above.

KEEP: `test_adaptive_band_is_8_to_30_hz_and_sensing_only_is_wider` (the 8-30 Hz pair is read by
`bravo_service.py:730`) and `test_dual_is_minutes_and_single_is_milliseconds` (the ramp, onset and
blanking times are read by `ClosedLoopDeployment/replay.py:131-133` and `simulation.py:167-168`).

### test_pipeline.py (196 lines, 14 tests)

All 14 KEEP. Two small notes: `test_provenance_defaults_are_labelled_not_stale` also pins
`PLT.INCUMBENT_EPOCH` and `PLT.INCUMBENT_XY`, two constants defined at `plots.py:70-71` and read by
nothing (the other two it pins, `DATA_HORIZON` and `WASHIN_MIN`, are live defaults); and the two
`pipeline.run` tests write into `/tmp/stimopt_test` rather than a pytest temporary directory.

### test_resolution.py (97 lines, 7 tests)

- `test_the_constant_has_exactly_one_definition` -- DEAD-TARGET -- asserts
  `stage1_openloop.RESOLUTION_K is resolution.RESOLUTION_K`; `stage1_openloop` is reached by nothing
  (see the map above), so the re-export it guards has no reader.

The other six are sound; the headline they check (`plots._incumbent_verdict`) is drawn by figure 1
(`plots.py:508`).

### test_schedule.py (111 lines, 12 tests)

All 12 -- DEAD-TARGET -- `schedule.randomized_block_schedule` and `schedule.safety_filter` have 0
callers outside tests (`pipeline.py:190` names `safety_filter` in a comment only;
`session_analysis.py:5` names the module in a docstring). Not named in any decision. The tests
themselves are well built (every setting once per block, no adjacent repeats across 40 seeds,
reproducible from the seed); what they test is the generator of a clinic sheet the platform never
produces. Names: `test_every_setting_appears_exactly_once_per_block`, `test_no_setting_on_adjacent_steps`,
`test_schedule_is_reproducible_from_the_seed_alone`, `test_balance_is_reported_and_near_the_session_midpoint`,
`test_fill_in_columns_are_present_and_blank`, `test_candidate_metadata_is_carried_through`,
`test_single_setting_is_refused_rather_than_silently_degenerate`, `test_duplicate_ids_are_refused`,
`test_one_block_is_still_a_valid_schedule`, `test_safety_filter_rejects_above_ceiling_with_a_reason`,
`test_safety_filter_rejects_beyond_what_was_ever_delivered`, `test_safety_filter_keeps_everything_inside_both_bounds`.

### test_separation_span.py (123 lines, 10 tests)

All 10 -- DEAD-TARGET -- `lfp_response.span_needed_for_separation`, `expected_separation_d` and
`within_arm_sd_from_result` have 0 callers outside `lfp_response.py`, where they call only each other
(`lfp_response.py:364,378`). Not named in any decision. The requirement they were built for (say how
wide a current range would have been needed, METHODS section 7 item 1) is served live by the
amplitude-effect table of decision 40, which reports the number and range of currents tested per
run. Names: `test_expected_separation_is_slope_times_span_over_scatter`,
`test_the_within_arm_scatter_is_recovered_from_the_gates_own_numbers`,
`test_a_narrow_ladder_is_named_as_a_protocol_shortfall_not_a_flat_band`,
`test_a_flat_band_is_not_reported_as_a_ladder_instruction`, `test_a_cell_that_already_clears_is_left_alone`,
`test_an_inestimable_slope_says_nothing_rather_than_guessing`, `test_the_ceiling_is_explicit_and_never_silently_infinite`,
`test_the_floor_itself_is_not_scaled_by_the_span`,
`test_a_span_already_wider_than_needed_is_named_as_an_inconsistency_not_a_shortfall`,
`test_widen_the_ladder_only_fires_when_the_span_really_is_too_narrow`.

### test_settings_store.py (369 lines, 14 tests)

All 14 KEEP. These pin decision 37 through the real store in a temporary directory of their own
(the override stays in force while the directory is removed, so the production root cannot be
touched, which is the trap decision 129 records), and check values: one parse then a read-back
equal frame for frame, the timezone surviving the round trip, both input keys in the sidecar, a new
report set giving a new key, a tampered chain refused.

### test_service_store.py (408 lines, 18 tests)

All 18 KEEP. These pin decision 41's wiring with the fit stood in for and the store real, including
the `rank` column that the first live run lacked. The four write-backs, the served response, the
refusal-then-recompute-then-replace sequence and the degraded-response-is-not-stored rule are all
checked on values read back from disk.

### test_session_analysis.py (755 lines, 42 tests)

All 42 -- DEAD-TARGET -- `routines/session_analysis.py` has 0 callers outside tests; it analyses a
filled-in clinic sheet that only `schedule.py` (also 0 callers) can produce. Not named in any
decision. The tests are careful (a known effect put in and recovered; clustering on the step widens
the standard error; drift removed by the block factor) and every one of them tests an analysis the
platform never runs. One of them, `test_the_real_clinic_sheet_is_accepted_and_analysable_once_filled`,
additionally skips unless a file exists at a hard-coded path under `/Users/pshirvalkar/.claude-science/`;
the file is on this Mac and cannot be in the container, so where the suite runs that test silently
never runs. Names: `test_clock_times_are_read_in_every_format_a_clinician_writes`,
`test_unreadable_times_return_nothing_rather_than_a_guess`, `test_the_resolution_a_time_was_written_to_is_reported`,
`test_minute_only_sheets_are_flagged_as_approximate`, `test_the_realised_washin_is_re_derived_and_not_taken_from_the_protocol`,
`test_steps_rated_too_soon_are_excluded_and_the_count_is_reported`, `test_a_step_at_exactly_the_threshold_counts_as_compliant`,
`test_missing_times_are_not_assessed_rather_than_assumed_compliant`, `test_unverified_steps_can_be_held_out_and_the_choice_is_visible`,
`test_a_rating_time_before_the_programming_time_is_a_data_error_not_a_short_washin`,
`test_a_known_setting_effect_is_recovered_with_the_right_sign_and_size`, `test_every_reported_coefficient_is_a_difference_from_the_incumbent`,
`test_standard_errors_are_clustered_on_the_step`, `test_within_visit_drift_is_removed_by_the_block_factor`,
`test_the_same_drift_is_NOT_removed_when_the_block_factor_is_dropped`, `test_block_adjustment_buys_precision_even_when_the_design_is_intact`,
`test_a_single_block_session_drops_the_block_term_instead_of_failing`, `test_a_session_with_too_few_steps_for_its_parameters_is_refused_not_fitted`,
`test_the_noise_floor_is_measured_from_the_repeated_incumbent`, `test_repeated_anchor_ratings_inside_a_block_give_a_drift_free_noise_floor`,
`test_a_measured_spread_of_zero_does_not_become_a_gate_of_zero`, `test_the_noise_floor_is_not_assessed_when_the_incumbent_was_rated_once`,
`test_the_verdict_table_covers_all_four_outcomes`, `test_a_difference_smaller_than_the_noise_floor_is_not_called_resolved`,
`test_resolution_is_judged_against_the_uncertainty_of_the_DIFFERENCE`, `test_the_contrast_standard_error_carries_both_settings_uncertainty`,
`test_a_setting_with_too_few_usable_steps_gets_not_assessed_not_a_verdict`,
`test_not_assessed_reaches_the_verdict_table_end_to_end_when_washin_kills_a_setting`,
`test_a_contrast_with_no_usable_standard_error_gets_no_verdict`,
`test_the_minute_resolution_caveat_fires_even_on_a_partly_minute_resolution_sheet`,
`test_when_nothing_beats_the_incumbent_the_report_says_so_plainly`, `test_side_effect_codes_and_words_are_both_accepted`,
`test_a_blank_side_effect_cell_is_unknown_and_never_none`, `test_the_severity_distribution_is_reported_per_setting`,
`test_every_moderate_or_severe_event_is_flagged_individually`, `test_no_amplitude_severity_dose_response_model_is_fitted`,
`test_ratings_outside_the_zero_to_ten_scale_are_dropped_and_counted`, `test_a_completely_blank_sheet_produces_no_verdicts_and_does_not_crash`,
`test_a_site_the_clinician_left_blank_is_reported_as_unfitted_not_as_null_effects`, `test_the_primary_outcome_is_the_left_leg`,
`test_the_analysis_accepts_a_csv_path_as_well_as_a_frame`, `test_the_real_clinic_sheet_is_accepted_and_analysable_once_filled`.

### test_stage1.py (411 lines, 24 tests)

All 24 -- DEAD-TARGET -- every test calls `stage1_openloop.run_stage1` or its helpers; `run_stage1`'s
only callers are `pipeline.run_two_stage` (0 callers) and the module's own usage docstrings
(`stage1_openloop.py:74`, `stage2_closedloop.py:55`). Not named in any decision. Names:
`test_every_stratum_is_referenced_to_one_common_incumbent`, `test_an_incumbent_absent_from_the_matrix_is_refused`,
`test_one_surface_is_fitted_per_adequately_sampled_pulse_width`, `test_an_undersampled_stratum_is_skipped_with_its_reason_never_pooled`,
`test_the_epoch_counts_are_internally_consistent`, `test_pulse_width_is_reported_as_not_observed_when_the_column_is_absent`,
`test_a_stratum_that_never_ran_the_incumbent_rate_reports_not_assessed_not_resolved`, `test_not_assessed_never_counts_as_resolved`,
`test_the_unsupported_refusal_names_the_extrapolation`, `test_choosing_the_setting_already_in_force_is_reported_as_unresolved`,
`test_resolution_propagates_both_standard_deviations`, `test_the_audit_detects_aliasing_when_each_pulse_width_has_its_own_rate`,
`test_the_audit_detects_a_crossed_design`, `test_the_pulse_width_contrast_refuses_a_rank_deficient_design`,
`test_the_pulse_width_contrast_is_estimable_on_a_crossed_design`,
`test_undersampled_levels_are_excluded_from_the_contrast_and_the_exclusion_is_reported`,
`test_a_sign_disagreement_between_the_two_views_is_reported_as_a_reason`, `test_a_single_pulse_width_level_is_unidentifiable_not_null`,
`test_the_frozen_configuration_cannot_be_written_to`, `test_an_override_requires_a_reason`,
`test_an_override_records_itself_and_changes_no_setting`, `test_the_frozen_configuration_carries_its_declared_provenance`,
`test_an_unknown_hemisphere_column_is_refused_not_substituted`, `test_the_summary_reports_support_alongside_every_verdict`.

### test_stage2.py (564 lines, 32 tests)

- `test_the_run_against_the_reconciled_biomarker_plate_refuses_for_three_stateable_reasons` --
  SUPERSEDED-RULE -- pins `stage_gate.RCS08_SELECTED_BANDS` and `RCS08_RESPONSE_SUMMARY`, a snapshot
  dated 2026-09-02 in the code itself: the nrs band at 3.9215 Hz with permutation p 0.0809, the
  left-leg band at 14.817 Hz with p 0.4166 and q 0.5055, and "3 of 15 cells suppress, one-sided
  p 0.996". Decision 59 records the nrs band moving from 3.9215 Hz to 0.95 Hz; decisions 38, 62 and
  64 make the calibrated 22-centre grid (8.5-29.5 Hz) the headline, with 47 of 264 rows clearing the
  correction; decisions 56 and 124 replace the 15-cell verdict with the pooled amplitude response.
  The test asserts the three 2026-09-02 numbers verbatim (`"0.4166"`, `"0.5055"`, `"3 of 15"`).
- `test_the_real_design_matrix_cannot_proceed_to_closed_loop` -- LIVE-DATA -- looks for
  `rcs08_bo_design_matrix.csv` in two places and skips if absent; `find .` over the repository finds
  no such file, so this test has always skipped silently.
- The other 30 -- DEAD-TARGET -- every one calls `stage2_closedloop.run_stage2` or
  `pipeline.run_two_stage`, whose only callers are each other and the tests. Not named in any
  decision. Names: `test_stage2_does_not_start_when_the_gate_refuses`, `test_the_refusal_names_which_condition_failed`,
  `test_not_starting_is_reported_as_a_terminal_answer_not_an_error`, `test_every_blocking_condition_is_carried_into_the_refusal`,
  `test_allow_gate_failure_runs_the_enumeration_but_records_that_nothing_is_deployable`, `test_stage2_refuses_a_caller_supplied_rate`,
  `test_stage2_refuses_a_caller_supplied_pulse_width`, `test_the_refusal_quotes_the_device_constraint_and_the_frozen_values`,
  `test_every_emitted_policy_inherits_the_frozen_rate_and_pulse_width`, `test_a_validated_policy_cannot_be_mutated`,
  `test_the_frozen_configuration_is_unchanged_by_a_stage2_run`, `test_a_band_outside_the_adaptive_range_is_rejected_not_moved_into_range`,
  `test_a_sensing_only_mode_is_rejected_rather_than_silently_swapped`, `test_a_sub_floor_frozen_rate_makes_every_candidate_invalid`,
  `test_without_lfp_evidence_every_candidate_is_rejected_for_the_unmeasured_response`, `test_no_valid_policy_ever_carries_a_device_problem`,
  `test_amplitude_windows_never_leave_the_delivered_envelope_or_the_ceiling`, `test_an_envelope_that_cannot_be_bounded_yields_no_window`,
  `test_single_mode_predicts_the_device_derived_threshold_rather_than_choosing_one`, `test_dual_mode_carries_a_manual_threshold_pair`,
  `test_the_ranking_basis_states_that_it_is_not_an_efficacy_ordering`, `test_the_ranking_is_ordered_by_capture_separation`,
  `test_the_two_stage_run_reports_honestly_that_it_cannot_proceed`, `test_both_routes_for_supplying_selected_bands_reach_the_gate_identically`,
  `test_supplying_the_same_gate_argument_by_both_routes_is_an_explicit_error`, `test_other_gate_kwargs_still_reach_the_gate`,
  `test_the_original_flat_entry_point_still_works`, `test_lfp_may_be_a_factory_that_receives_the_frozen_configuration`,
  `test_a_plain_evidence_object_still_works_unchanged`, `test_the_factory_may_refuse_by_returning_none_and_the_gate_then_blocks`.

### test_stage_gate.py (524 lines, 41 tests)

- KEEP (1): `test_precomputed_band_power_is_used_when_supplied` -- the `band_power` form of the
  `LfpEvidence` holder is exactly what the live builders construct (`lfp_evidence.py:1068`,
  `within_visit.py:642`) and `power_for` is called by the live screen (`lfp_evidence.py:1155`).
- `test_band_power_uses_the_device_definition_of_a_sum_of_squares` -- DEAD-TARGET -- the
  `magnitude` plus `freqs` form of the holder routes to `lfp_response.device_band_power`, which has 0
  callers; no live builder uses that form.
- SUPERSEDED-RULE (7), all pinning the frozen 2026-09-02 plate described under `test_stage2.py`
  (decisions 59, 38/62/64, 56/124): `test_supplying_selected_bands_adds_two_separately_reported_conditions`,
  `test_the_out_of_window_band_is_excluded_by_the_device_not_by_its_statistics` (asserts the band spans
  `1.4215`-`6.4215` Hz and names `"3.921"`), `test_the_only_adaptive_capable_band_is_not_statistically_supported`
  (asserts `perm_p == 0.4166` and `fdr_q == 0.5055`), `test_the_nrs_band_lost_its_nominal_significance_under_selection_correction`
  (asserts `perm_p == 0.0809`), `test_a_supplied_failing_response_summary_is_reported_with_its_source`,
  `test_a_supplied_summary_takes_precedence_over_row_level_evidence`, `test_the_reconciled_plate_carries_its_provenance`
  (asserts `responds is False` on the 15-cell verdict).
- The other 32 -- DEAD-TARGET -- every one calls `stage_gate.evaluate_gate` or one of its condition
  checks, whose only callers are `stage2_closedloop.py` and `pipeline.run_two_stage` (0 callers).
  Names: `test_the_gate_refuses_a_sub_55_hz_rate_and_names_the_rate_condition`, `test_a_rate_exactly_at_the_floor_passes`,
  `test_one_hemisphere_below_the_floor_blocks_the_whole_gate`, `test_the_gate_refuses_an_unresolved_open_loop_choice`,
  `test_a_not_assessed_component_is_reported_as_never_asked_not_as_refused`,
  `test_a_recorded_override_licenses_the_resolution_condition_but_is_reported_as_an_override`,
  `test_an_override_does_not_license_any_other_condition`, `test_the_gate_refuses_when_no_band_inside_8_to_30_hz_passes_the_response_test`,
  `test_a_band_outside_the_adaptive_range_is_refused_on_the_range_alone`, `test_the_whole_band_must_be_inside_the_range_not_just_its_centre`,
  `test_missing_lfp_evidence_is_not_assessed_and_still_blocks`, `test_a_responding_band_passes_and_reports_its_separation`,
  `test_default_band_centres_all_lie_inside_the_adaptive_range`, `test_limits_above_the_declared_ceiling_are_refused`,
  `test_limits_above_the_delivered_envelope_are_refused_with_the_severity_evidence`, `test_inverted_limits_are_refused`,
  `test_defaulted_limits_say_so_rather_than_looking_checked`, `test_limits_inside_the_envelope_and_under_the_ceiling_pass`,
  `test_all_four_conditions_are_always_evaluated_and_reported`, `test_omitting_selected_bands_leaves_the_original_four_condition_shape`,
  `test_a_band_outside_the_window_would_be_excluded_even_with_a_significant_p_value`,
  `test_a_band_surviving_permutation_but_not_fdr_is_refused`, `test_a_band_with_no_permutation_p_is_not_assessed_rather_than_passed`,
  `test_a_supported_adaptive_capable_band_passes`, `test_the_selection_thresholds_are_the_conventional_values_and_are_not_relaxed`,
  `test_a_supplied_summary_with_no_verdict_is_not_assessed`, `test_a_supplied_passing_summary_passes`,
  `test_the_gate_can_pass_when_every_condition_is_met`, `test_passing_requires_strictly_true_never_none`,
  `test_a_configuration_with_no_settings_is_not_assessed_rather_than_passed`, `test_describe_names_every_blocking_condition`,
  `test_an_unknown_condition_name_raises_rather_than_returning_a_default`.

### test_surrogate_torch.py (849 lines, 33 tests)

All 33 -- DEAD-TARGET -- `routines/surrogate_torch.py` has 0 callers outside tests (the only other
mention is `safety_ordinal.py:118`, itself unreached). The module's own document,
`BOTORCH_REFACTOR.md`, recommends against it: "Do not add PyTorch to the production Django
container. Keep it an optional dependency of a research environment, and keep the scikit-learn
backend as the default." 23 of the 33 carry `@needs_torch` and have never run in the container
(checked today: `torch`, `gpytorch`, `botorch` absent). The remaining 10 (the import-without-torch
check, seven "delivered envelope" tests and the length-scale profile) run, and test a module nothing
calls. Names: `test_module_imports_without_torch_and_says_so`, `test_safe_set_is_contiguous_in_amplitude`,
`test_no_monotone_amplitude_ceiling_is_imposed`, `test_unknown_region_is_labelled_unknown_not_safe_or_unsafe`,
`test_clinician_ceiling_is_a_hard_bound`, `test_expansion_cap_keys_off_worst_severity`,
`test_envelope_refuses_an_empty_or_unusable_history`, `test_envelope_does_not_extrapolate_beyond_delivered_frequencies`,
`test_envelope_report_is_self_describing`, `test_frequency_lengthscale_profile_needs_no_torch_and_finds_its_maxima`;
and, never run: `test_interface_parity_with_sklearn_objective_gp`, `test_matched_hyperparameters_reproduce_sklearn_posterior`,
`test_as_used_arms_diverge_and_the_report_says_where`, `test_length_scale_prior_keeps_the_estimate_off_the_boundary`,
`test_latent_only_standard_deviation_is_smaller_by_the_nugget`, `test_objective_gp_refuses_infeasible_and_degenerate_input`,
`test_fantasy_freezes_hyperparameters`, `test_preference_gp_interface_and_ranking`,
`test_preference_prob_prefer_is_a_probability_and_antisymmetric`, `test_preference_gp_rejects_ties_and_bad_indices`,
`test_severity_gp_prior_mean_is_flat_not_monotone`, `test_constrained_acquisition_returns_eligible_cells_with_provenance`,
`test_outcome_constraint_moves_the_batch_away_from_predicted_risk`, `test_constraint_probability_is_graded_where_a_mask_would_be_binary`,
`test_selector_refuses_an_empty_or_undersized_candidate_set`,
`test_reported_marginal_likelihood_matches_sklearn_when_the_models_are_identical`, `test_the_log_prior_is_counted_exactly_once`,
`test_reading_the_hyperparameters_leaves_the_model_ready_to_predict`,
`test_fitting_under_the_prior_cannot_beat_pure_likelihood_on_likelihood`,
`test_prior_scale_sweep_reports_the_transition_rather_than_a_single_number`,
`test_a_tighter_prior_moves_the_estimate_toward_the_prior_median`,
`test_which_way_the_free_fit_degenerates_is_a_property_of_the_data_not_the_model`,
`test_a_tight_prior_picks_the_length_scale_rather_than_estimating_it`.

### test_safety_ordinal.py (413 lines, 32 tests)

All 32 -- DEAD-TARGET -- `routines/safety_ordinal.py` has 0 callers outside tests (`schedule.py:156`
and `surrogate_torch.py:1095` name it in docstrings; both are themselves unreached). Same
`BOTORCH_REFACTOR.md` recommendation as above. 17 carry `@needs_torch` and never run in the
container; the `rate_model` and `rare_event_model` fixtures also skip when PyTorch is absent. The
15 that do run are label-handling and mask-arithmetic tests on a module nothing calls. Names:
`test_encode_severity_maps_the_ordered_scale_to_ascending_integers`,
`test_encode_severity_marks_every_flavour_of_missing_as_minus_one_not_as_none`,
`test_prepare_drops_uncoded_procedural_and_incomplete_rows_and_says_so`, `test_prepare_never_turns_a_missing_severity_into_none`,
`test_prepare_separates_never_coded_rows_from_explicitly_coded_ones`, `test_prepare_reports_the_adverse_rate_at_zero_amplitude_separately`,
`test_recomputed_set_follows_the_latest_classification`, `test_cumulative_set_never_shrinks_which_is_its_whole_point_and_its_whole_risk`,
`test_cumulative_admission_is_gated_on_evidence_not_on_probability_alone`, `test_cumulative_mode_refuses_to_run_without_evidence_counts`,
`test_an_unknown_mode_is_rejected_at_construction`, `test_contiguity_violations_finds_a_gap_a_clinician_could_not_ramp_through`,
`test_a_lower_interval_mask_has_no_contiguity_violations`, `test_lower_interval_projection_removes_only_unreachable_cells`,
`test_lower_interval_leaves_an_already_contiguous_mask_alone`; and, never run:
`test_cutpoints_are_ascending_with_the_first_pinned_at_zero`, `test_category_probabilities_are_a_proper_distribution`,
`test_the_model_recovers_a_rate_effect_without_being_told_to_look_for_one`, `test_no_monotone_amplitude_relationship_is_imposed`,
`test_a_region_with_no_data_is_unknown_and_never_safe`, `test_uncertainty_is_larger_where_there_are_fewer_observations`,
`test_evidence_is_on_the_scale_of_a_count_of_observations`, `test_credible_interval_brackets_the_mean_and_widens_with_credible_mass`,
`test_a_confidently_dangerous_region_is_labelled_elevated_not_unknown`, `test_classify_requires_both_conditions_before_calling_a_cell_safe`,
`test_fit_refuses_an_unlabelled_row_rather_than_treating_it_as_none`, `test_fit_refuses_a_rank_outside_the_declared_scale`,
`test_a_non_positive_value_on_a_log_axis_is_refused`, `test_predicting_before_fitting_raises_rather_than_returning_something_plausible`,
`test_fitting_is_reproducible_for_a_given_seed`, `test_p_at_least_rejects_a_level_outside_the_scale`,
`test_the_two_update_rules_agree_when_the_model_never_changes`.

### test_safety_and_evidence.py (769 lines, 58 tests)

- `test_safety_filter_refuses_an_energy_budget_argument` -- DEAD-TARGET -- `schedule.safety_filter`, 0
  callers; and the assertion is that an unknown keyword raises `TypeError`, which Python does for any
  function.
- `test_the_flat_limit_binds_identically_at_every_rate` -- DEAD-TARGET -- `schedule.safety_filter`.
- `test_above_the_flat_limit_is_refused_at_every_rate` -- DEAD-TARGET -- `schedule.safety_filter`.
- `test_band_power_exponentiates_before_summing` -- DUPLICATE -- of
  `test_lfp_evidence.py::test_band_power_linear_is_still_there_for_its_other_callers`: the same
  inputs (`log10(2)`, `log10(8)`, centre 10.5, width 2.0, `log_scale="log10"`) and the same expected
  10.0; and `band_power_linear` is on the retired route anyway.
- `test_band_outside_the_frequency_axis_returns_none_rather_than_nearest_bins` -- DEAD-TARGET --
  `band_power_linear`, retired route, 0 live callers.
- `test_marginal_familiarity_does_not_imply_the_pair_was_ever_delivered` -- DEAD-TARGET --
  `schedule.safety_filter` with `prior_triples`.
- `test_a_genuinely_delivered_triple_passes_and_reports_its_record_count` -- DEAD-TARGET -- same.
- `test_joint_check_is_opt_in_and_validates_its_own_input` -- DEAD-TARGET -- same.
- `test_the_platform_stores_decibels_and_undoing_it_wrongly_is_silent` -- DEAD-TARGET -- `band_power_linear`.
- `test_db10_is_the_default_because_that_is_what_the_platform_stores` -- DEAD-TARGET -- `DEFAULT_LOG_SCALE`
  is read only by the retired decibel branch.
- `test_unknown_log_scale_raises_rather_than_guessing` -- DEAD-TARGET -- `band_power_linear`.
- `test_frame_from_matrix_attaches_the_shared_frequency_axis_to_every_row` -- DEAD-TARGET --
  `lfp_evidence.frame_from_matrix` is called only at `adapter.py:549`, inside the
  `BAND_POWER_DECIBEL_DENSITY` branch no caller selects.
- `test_frame_from_matrix_can_restrict_sources_but_keeps_all_by_default` -- DEAD-TARGET -- same.
- `test_frame_from_matrix_refuses_a_shape_mismatch` -- DEAD-TARGET -- same.
- `test_matrix_to_evidence_round_trip_uses_the_db_convention` -- DEAD-TARGET -- assembled matrix to
  decibel frame to evidence, the whole retired route; its own comment says the value it pins "is
  deliberately NOT on the device's own number scale".
- `test_screen_cells_refuses_the_retracted_parameters` -- SHAPE-ONLY -- asserts only that
  `screen_cells(..., energy_budget=...)` raises `TypeError`, which any function does for an unknown
  keyword; no value is checked.
- `test_an_era_with_one_amplitude_contributes_nothing_to_the_within_era_slope` -- DEAD-TARGET -- the
  body calls no Stim Optimizer code at all: it fits two `statsmodels` regressions on data it builds
  itself and compares their slopes. It proves a property of ordinary least squares, not of this
  module.

**A note on 14 tests counted as KEEP here, for the rewrite list.** The nine `build_evidence` tests
from `test_nanosecond_timestamps_raise...` to `test_hemisphere_must_be_named_explicitly`, and the
five "production column names" tests from `test_build_evidence_accepts_the_adapters_real_column_names`
to `test_an_explicit_era_column_wins_and_is_recorded`, feed `build_evidence` a frame in the retired
decibel-density shape (`log_psd` and `freqs` columns). The rules they assert (stimulation-off windows
dropped, other rates never pooled, one amplitude is unusable, an unknown channel is named, the era
falls back to the calendar month, the adapter's real column names bind) live in the code that runs
before the branch on frame shape (`lfp_evidence.py:882-960`), so they are live and are checked
nowhere else; `test_lfp_evidence.py` covers the calibrated route but not these cases. They are
sound today and should be moved onto the calibrated tile frame (`_cache_entry` in
`test_lfp_evidence.py`) before the decibel route is removed, or they will go dark with it.

The remaining KEEP tests here are the amplitude-limit guards, the twelve `screen_cells` tests with a
stubbed response function (the screen is live at `pipeline.py:393` and
`ClosedLoopDeployment/adapter.py:1035`), the five timing-plan tests, the latency estimator, the five
threshold-mode tests (`recommend_threshold_mode` and `timing_plan` are read by the Closed-Loop
prescription and protocol code), and the two recent-era tests.

### test_within_visit.py (842 lines, 41 tests)

Twenty tests here cover the four functions the Closed-Loop Deployment module reads (the average of
the last thirty seconds before the current changes, the per-run curvature test, the pooled
curvature-and-slope test, and the dependency-direction guard) and are sound. The other 21 test three
things nothing calls.

- `test_builder_returns_the_same_shape_build_all_does_and_screen_cells_eats_it` -- DEAD-TARGET --
  `build_all_within_visit`'s only caller is `ClosedLoopDeployment.adapter.amplitude_response_cached`,
  which has 0 callers of its own (decisions 85 and 101 record exactly this). **Protected in part**:
  decision 101 says functions of this class are "NOT deleted" without the PI, so this and the next
  four are listed as the PI's call, not as safe.
- `test_the_visit_supplies_era_and_cluster_and_amplitude_varies_inside_it` -- DEAD-TARGET --
  `build_within_visit_evidence`, reached only through the path above.
- `test_a_real_negative_slope_survives_the_builder` -- DEAD-TARGET -- same.
- `test_unusable_cells_are_audited_with_a_reason_never_silently_absent` -- DEAD-TARGET -- same.
- `test_centre_count_mismatch_raises_rather_than_mislabelling_bands` -- DEAD-TARGET -- same.
- `test_the_fast_estimator_matches_the_gates_statsmodels_fit` -- DEAD-TARGET -- `_band_t_cluster_robust`
  is called only inside `band_cluster_permutation` (`within_visit.py:854,882`), which has 0 callers.
- `test_clusters_are_runs_of_adjacent_same_signed_bands` -- DEAD-TARGET -- `_clusters_along_axis`, same.
- `test_a_localised_effect_is_detected_where_the_majority_rule_cannot_be_satisfied` -- DEAD-TARGET --
  `band_cluster_permutation`: 0 callers outside tests. The code's own block comment
  (`within_visit.py:677-720`) says it "MUST NEVER FEED THE DEPLOYABILITY GATE" and is "a search
  instrument"; nothing on any page runs the search. Not named in any decision.
- `test_a_flat_panel_is_not_significant` -- DEAD-TARGET -- same.
- `test_the_p_value_can_never_beat_its_own_resolution` -- DEAD-TARGET -- same.
- `test_it_refuses_rather_than_returning_a_meaningless_number` -- DEAD-TARGET -- same.
- `test_the_result_states_that_it_cannot_locate_the_effect` -- DEAD-TARGET -- same.
- `test_the_threshold_sweep_comes_from_one_permutation_loop_and_matches_separate_runs` -- DEAD-TARGET --
  same; also the slowest test in the module by construction.
- `test_a_higher_threshold_never_grows_a_cluster` -- DEAD-TARGET -- same.
- `test_the_primary_threshold_is_always_present_in_the_sweep` -- DEAD-TARGET -- same.
- `test_the_older_median_rule_is_still_there_and_still_does_its_own_thing` -- DEAD-TARGET -- its
  comment says "Other code calls step_settled_medians"; the search finds 0 callers of
  `step_settled_medians` anywhere outside `within_visit.py`, and `step_settled_stats` is reached only
  through the unwired builder above.
- `test_the_ramp_exclusion_covers_the_longest_ramp_actually_observed` -- DEAD-TARGET -- `RAMP_EXCLUDE_S`
  and `LONGEST_OBSERVED_RAMP_S` are read only by the unwired builder and by the ramp-clip branch below;
  `ClosedLoopDeployment/clinic_steps.py:95` names the constant in a comment only.
- `test_the_step_summary_is_the_average_and_the_middle_value_stays_available` -- DEAD-TARGET --
  `step_settled_stats` and `step_settled_medians`, same unwired path (PI's call, as above).
- `test_ramp_windows_come_from_the_device_and_a_burst_is_one_step` -- DEAD-TARGET --
  `ramp_windows_from_amplitude`: 0 callers outside tests (searched all of `BRAVO`).
- `test_a_block_whose_current_never_holds_still_is_refused_not_described_as_a_ramp` -- DEAD-TARGET --
  same function.
- `test_the_look_back_window_is_clipped_at_the_measured_end_of_the_ramp` -- DEAD-TARGET (branch) --
  the `ramp_end_t` argument of `mean_power_before_next_change` is passed by no live caller: the
  three-source panel calls it with `block`, `step_end_t`, `window_s` and `min_chunks` only
  (`three_source_response.py:844-847`), and `ramp_end_t`/`ramp_margin_s` appear nowhere else outside
  tests. Worth the PI's eye: commit `790ed21` (2026-09-05) added this clip so the average "cannot
  average signal recorded while the current was still moving", and today nothing that runs asks for
  it.

---

## Safe to delete now

These are DEAD-TARGET with 0 callers and no decision protecting them, or DUPLICATE, or
SUPERSEDED-RULE where the decision log is explicit. Deleting a test does not delete the function it
tested; whether the function goes too is a separate question.

**A. Stand-alone dead targets (64 tests).**

- `test_acquisition.py`: `test_lcb_is_more_optimistic_with_larger_eta`,
  `test_between_visit_batch_respects_separation`, `test_between_visit_is_more_spread_than_within_visit`,
  `test_plateau_alone_does_not_stop`, `test_both_conditions_stop`, `test_ceiling_reports_truncated_not_converged`
  (the last three only if the one-item history in `pipeline.py:268` is accepted as the design; if the
  PI wants the stopping rule to be able to stop, keep them and fix the caller instead).
- `test_core.py`: `test_head_is_excluded_with_a_reason`, `test_prob_prefer_is_symmetric_and_bounded`.
- `test_lfp_evidence.py`: `test_the_older_decibel_route_is_still_reachable_for_the_comparison`.
- `test_lfp_response.py`: `test_device_band_power_is_a_sum_of_squares_over_the_band`,
  `test_band_power_refuses_a_band_with_no_bins_and_bad_shapes`,
  `test_derived_threshold_uses_the_device_formula_on_the_captures`.
- `test_percept_adaptive.py`: all 17 DEAD-TARGET tests listed above.
- `test_resolution.py`: `test_the_constant_has_exactly_one_definition`.
- `test_separation_span.py`: all 10.
- `test_stage_gate.py`: `test_band_power_uses_the_device_definition_of_a_sum_of_squares`.
- `test_safety_and_evidence.py`: `test_band_outside_the_frequency_axis_returns_none_rather_than_nearest_bins`,
  `test_the_platform_stores_decibels_and_undoing_it_wrongly_is_silent`,
  `test_db10_is_the_default_because_that_is_what_the_platform_stores`,
  `test_unknown_log_scale_raises_rather_than_guessing`, the three `test_frame_from_matrix_*` tests,
  `test_matrix_to_evidence_round_trip_uses_the_db_convention`,
  `test_an_era_with_one_amplitude_contributes_nothing_to_the_within_era_slope`.
- `test_within_visit.py`: the 10 `band_cluster_permutation` tests (`test_the_fast_estimator_matches_the_gates_statsmodels_fit`
  through `test_the_primary_threshold_is_always_present_in_the_sweep`), `test_ramp_windows_come_from_the_device_and_a_burst_is_one_step`,
  `test_a_block_whose_current_never_holds_still_is_refused_not_described_as_a_ramp`,
  `test_the_look_back_window_is_clipped_at_the_measured_end_of_the_ramp`,
  `test_the_ramp_exclusion_covers_the_longest_ramp_actually_observed`. (Before deleting the last two:
  decide whether the ramp clip of commit `790ed21` was meant to be live; if so the fix is in
  `three_source_response.py`, not here.)

**B. Duplicates (3).** `test_lfp_evidence.py::test_the_call_shapes_other_modules_use_still_bind`,
`test_lfp_evidence.py::test_the_stream_argument_still_stops_the_files_being_read_twice`,
`test_safety_and_evidence.py::test_band_power_exponentiates_before_summing`.

**C. Superseded snapshot (8).** The seven `test_stage_gate.py` tests and the one `test_stage2.py` test
that pin the 2026-09-02 RCS08 plate (nrs at 3.9215 Hz, left-leg at 14.817 Hz, "3 of 15 cells"):
decisions 59, 38, 62, 64, 56 and 124 have all moved past it. The two constants
`stage_gate.RCS08_SELECTED_BANDS` and `RCS08_RESPONSE_SUMMARY` would go with them.

**D. The whole two-stage subsystem and its research backend (211 tests): a subsystem decision, not a
test decision.** `test_schedule.py` (12), `test_session_analysis.py` (42), `test_stage1.py` (24),
`test_stage2.py` (30 remaining), `test_stage_gate.py` (32 remaining), `test_surrogate_torch.py` (33),
`test_safety_ordinal.py` (32), and the three `schedule.safety_filter` tests plus the three joint-check
tests in `test_safety_and_evidence.py` (6). Every one qualifies on the brief's rule (0 callers, no
decision), and none should go one test at a time: they are the test suite of a designed subsystem
(`TWO_STAGE_DESIGN.md`, `BOTORCH_REFACTOR.md`) that the running platform never calls. If the PI
retires the subsystem, these go with it; if he intends to wire it in, they stay and the wiring is the
work. Either way, the 40 PyTorch-gated tests should leave the production suite now, because
`BOTORCH_REFACTOR.md` itself says the libraries they need do not belong in the container, so they
can never run where the suite runs.

**How the 285 DEAD-TARGET tests divide.** 64 in list A, 211 in list D, 9 protected (next paragraph),
and 1 (`test_within_visit.py::test_the_older_median_rule_is_still_there_and_still_does_its_own_thing`)
in the rewrite list because half of it checks a live function.

**Not safe, although dead.** Three `test_core.py` side-effect-ladder tests (pre-registered in
`OBJECTIVE_SPEC.md` section 2.3, awaiting prospective data) and the six `test_within_visit.py` tests
of the within-visit builder and the step summaries (reached only through
`amplitude_response_cached`, which decisions 85 and 101 record as unwired and kept pending the PI).

---

## Rewrite, do not delete

- `test_lfp_evidence.py::test_band_power_linear_is_still_there_for_its_other_callers` -- MISNAMED --
  rename to say what is true (the function is kept for the retired decibel route), or delete it
  together with that route.
- `test_adapter.py::test_both_functions_take_the_argument_and_default_it_to_none` and
  `test_the_call_shapes_the_other_modules_use_still_bind` -- SHAPE-ONLY -- fold into one test that
  calls both functions with the shipping argument shapes and checks a value (the parse count, which
  the neighbouring tests already do), or accept them as signature guards and say so in the name.
- `test_safety_and_evidence.py::test_screen_cells_refuses_the_retracted_parameters` -- SHAPE-ONLY --
  either delete (Python already refuses an unknown keyword) or turn it into a source scan that the
  name `energy_budget` appears nowhere in `lfp_evidence.py`, which is what the retraction actually
  needs guarded.
- `test_safety_and_evidence.py`, the 14 `build_evidence` tests named in that file's note -- KEEP today,
  but move their fixtures from the decibel-density frame (`log_psd`, `freqs`) onto the calibrated tile
  frame before the decibel route is removed; the rules they check are live and are checked nowhere
  else.
- `test_within_visit.py::test_the_older_median_rule_is_still_there_and_still_does_its_own_thing` --
  the comment "Other code calls step_settled_medians" is false today (0 callers); if the test stays,
  the comment must go.
- `test_acquisition.py`, the three stopping-rule branch tests -- if the PI wants the stopping rule to
  be able to fire on the page, the change is to pass a real history at `pipeline.py:268`; the tests
  are then right and the caller was wrong.

---

## Three things found on the way that are about the code, not the tests

1. **The ramp clip is not wired.** Commit `790ed21` added `ramp_end_t` to
   `mean_power_before_next_change` so the thirty-second average could stop at the measured end of the
   ramp; the only live caller (`three_source_response.py:844`) does not pass it, and
   `ramp_windows_from_amplitude`, which measures that end, has 0 callers. Where this is on screen: the
   Closed-Loop Deployment page's "Stimulation amplitude effects on band power, measured three ways"
   panel, whose time-domain column is built by that call. Whether the panel's own step boundaries
   already exclude the ramp is a question for whoever owns `three_source_response.py`; this audit only
   establishes that the clip built for it is not used.
2. **Two rate floors.** `percept_adaptive.MIN_ADAPTIVE_RATE_HZ = 55.0` (PI-supplied, per its
   comment) is reported in the optimizer response and enforced by nothing that runs;
   `constraints.py:2257` enforces 30 Hz on the Closed-Loop page's device-rule ledger. On screen: the
   Stim Optimizer page shows the 55; the Closed-Loop page's ledger applies the 30.
3. **The package docstring lists a file that does not exist.** `StimOptimizer/__init__.py` names
   `routines/design.py`; there is no such file (the epoch construction lives in `adapter.py`).
