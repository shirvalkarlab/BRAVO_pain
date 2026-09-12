# Test audit, 2026-09-12: the Closed-Loop Deployment module

**What this is.** A read-only classification of every test under
`BRAVO/modules/ClosedLoopDeployment/tests/` (26 files, 8,907 lines counted today with `wc -l`, of which
two are `__init__.py` and `conftest.py`; 487 test functions counted with `grep -c 'def test_'`). Nothing
was run and nothing was deleted. Every test body was read, and every function a test calls was checked
for production callers with a search across `BRAVO/modules` and `BRAVO/Server`, leaving out every
`tests/` directory and `BRAVO/_agent_bridge`. The four files changed today (commits `b2f03e11`,
`a13bfe9b`, `56d04cfc`) were read as they stand now.

**The one-line answer.** 443 of the 487 tests are sound: they call live code with a hand-built input
and check a computed value. 44 are not, and they fall into six kinds, listed per file below. **Nothing
here should be deleted on this report's say-so**; the two lists at the end say what is safe and what
should be rewritten instead.

**How the classes were applied.** KEEP means the test reaches code the running platform actually
calls and checks a value. DEAD-TARGET means the function or branch it tests has no caller outside the
tests any more (the callers found are named on each line). SUPERSEDED-RULE means the test pins a rule
the record has since reversed. SHAPE-ONLY means the test checks only that something is present, has
the right keys or length, or does not raise, and never checks a number or a verdict. MISNAMED means the
name promises something the body does not check. DUPLICATE means another named test pins the same
thing. LIVE-DATA means the test reaches the live database or the container.

---

## Summary table

| File | Lines | Tests | KEEP | DEAD-TARGET | SUPERSEDED | SHAPE-ONLY | MISNAMED | DUPLICATE | LIVE-DATA |
|---|---|---|---|---|---|---|---|---|---|
| test_adapter_caching.py | 695 | 34 | 20 | 12 | 0 | 0 | 0 | 2 | 0 |
| test_amplitude_effect.py | 266 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_bootstrap.py | 512 | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_bravo_service.py | 161 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_calibrated_join.py | 107 | 7 | 6 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_clinic_steps.py | 140 | 11 | 5 | 6 | 0 | 0 | 0 | 0 | 0 |
| test_constraints.py | 911 | 54 | 49 | 0 | 1 | 2 | 2 | 0 | 0 |
| test_core.py | 1429 | 67 | 59 | 6 | 0 | 1 | 0 | 0 | 1 |
| test_d19_point_signs_and_d30_active_group.py | 264 | 20 | 18 | 0 | 0 | 2 | 0 | 0 | 0 |
| test_direction_consistency.py | 134 | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_grid_matches_biomarkers_settings.py | 168 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_ground_truth.py | 229 | 11 | 10 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_pooled_e1.py | 94 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_pooled_shape_store.py | 150 | 9 | 8 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_prescription_modes.py | 309 | 15 | 13 | 0 | 0 | 2 | 0 | 0 | 0 |
| test_programmed_settings_from_epochs.py | 137 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_protocol.py | 360 | 28 | 27 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_reliable_change.py | 166 | 15 | 15 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_replay.py | 348 | 29 | 29 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_report_contract.py | 297 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_run_points_store.py | 200 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_session_report_summary_store.py | 488 | 22 | 22 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_simulation.py | 381 | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_stability.py | 293 | 21 | 20 | 1 | 0 | 0 | 0 | 0 | 0 |
| test_three_source_response.py | 430 | 26 | 25 | 0 | 0 | 1 | 0 | 0 | 0 |
| test_track_d_grid_stability_translation.py | 225 | 7 | 6 | 0 | 0 | 0 | 1 | 0 | 0 |
| **Total** | **8,907** | **487** | **443** | **25** | **1** | **12** | **3** | **2** | **1** |

Tests likely to take longer than 5 seconds each, judged by reading (not measured; the orchestrator
runs the suite):

- `test_bootstrap.py::test_cr0_over_rejects_a_true_null_and_the_bootstrap_does_not` (two
  parameter sets): each runs 120 simulated datasets, and for every one a statsmodels fit, a
  399-draw bootstrap, and a bootstrap interval search that calls the bootstrap many more times.
- `test_bootstrap.py::test_the_bootstrap_still_detects_a_real_effect`: the same loop, 120 datasets.
- `test_bootstrap.py::test_the_interval_and_the_p_value_agree_about_zero` (12 interval searches) and
  `test_the_bootstrap_interval_is_wider_than_the_cr0_interval_at_few_clusters` (15) are the next
  slowest; probably a few seconds each.
- `test_core.py::test_the_biomarker_module_still_does_not_import_the_closed_loop_module` starts a
  fresh Python process that imports the Biomarkers analytics module (scipy, statsmodels); a few
  seconds.

Nothing in the module sleeps. No test loads the RCS08 recordings.

---

## Two things the PI should know before reading the lists

**1. One test touches the live database and can start a real background job (test_core.py).**
`test_pocket_adaptor_stays_unknown_rather_than_assumed_absent` calls
`device_facts.session_report_facts_for` for the RCS08 identifier with no store override and no
stub. Since today's commit `56d04cfc` that function looks up the participant's ingested session
reports in the database and, when the stored summary is not current, calls
`launch_summary_rebuild_in_background`, which spawns `manage.py rebuild_session_report_summary`
against the production cache root (`device_facts.py` lines 784-830: the launcher refuses only when
the store is on a test override root, and this test sets none). In the container, where the host
suite runs, that is the decision 96 and 107 class of slip: a unit test starting a real process. On
this machine, with no database, the same call falls through to the committed
`_facts_RCS08.json` and starts nothing. The test's own assertion is also weak
(`"has_pocket_adaptor" not in f or f["has_pocket_adaptor"] is None`).

**2. A whole family of tests exercises a branch nothing reaches any more, kept on purpose.**
Since 2026-09-05 (commit `90eb109`, and decision 45 which made the join accept it) the sensed-signal
frame the Closed-Loop report receives carries one column per band (`band_lsb_<centre>`), already on
the device's own scale. The older frame, one whole spectrum per row in `log_psd` and `freqs`, is
still accepted by `adapter.joined_table` and `adapter._joined_signature` (the `else` branch at
`adapter.py` lines 331-334 and 1115-1123), and the StimOptimizer docstring that produces the frame
says of the older kind "still accepted". But no production caller asks for it:
`StimOptimizer.adapter.evidence_inputs` defaults to the calibrated kind and the only two callers
(`ClosedLoopDeployment/adapter.py:828`, `StimOptimizer/adapter.py:579`) pass no override. So
`adapter.band_powers` (called only from that branch) and the array-column hashing inside
`_frame_fingerprint` are live code that no request reaches. Five tests are marked DEAD-TARGET for
this reason and are listed separately at the end as "kept on purpose, the PI's call", not as safe
to delete. Eight more tests (the joined-table memo tests in test_core.py and test_adapter_caching.py)
use the old frame shape only as a fixture for memo behaviour that is shape-independent; those are
KEEP, with a note that the fixture docstrings ("as the real frame is") are no longer true.

---

## Per file: every non-KEEP test

### test_adapter_caching.py (695 lines, 34 tests; 20 KEEP)

The nine tests below all go through `adapter.amplitude_response_cached`, which has **0 callers outside
tests** (search of `BRAVO/modules` and `BRAVO/Server`; the only mentions are its own definition at
`adapter.py:975` and the tests). Decisions 85, 100 and 101 already record that this path "has no
production caller" and that its missing provenance was left as is for that reason; none of them says
to keep the function.

- `test_the_same_clinic_sheet_twice_fits_nothing_the_second_time` -- DEAD-TARGET -- target
  `amplitude_response_cached`, 0 callers outside tests.
- `test_an_edited_clinic_sheet_makes_the_figures_be_worked_out_again` -- DEAD-TARGET -- same target,
  0 callers; also `clinic_steps_signature` is called only from that function (`adapter.py:1007`).
- `test_a_new_visit_appended_to_the_sheet_also_invalidates` -- DEAD-TARGET -- same target.
- `test_re_decoded_recordings_invalidate_even_though_the_sheet_is_untouched` -- DEAD-TARGET -- same.
- `test_nothing_else_invalidates_the_figures` -- DEAD-TARGET -- same.
- `test_the_figures_memo_stays_bounded` -- DEAD-TARGET -- same; `response_cache_stats` also has 0
  callers.
- `test_force_refresh_recomputes_even_though_nothing_changed` -- DEAD-TARGET -- same.
- `test_a_second_process_finds_what_the_first_one_built` -- DEAD-TARGET -- the vehicle is
  `amplitude_response_cached`; the property it pins (a second process reads the file the first
  wrote) is pinned in `CacheStore/tests/test_store.py::test_store_if_absent_reads_from_the_root_it_writes_to`.
- `test_a_corrupt_shared_file_is_a_miss_and_not_an_error` -- DEAD-TARGET -- same vehicle; the
  property is pinned in `CacheStore/tests/test_store.py::test_load_newest_reports_an_unreadable_entry_and_discards_it`
  and `test_a_payload_with_no_sidecar_in_a_checkable_format_is_refused`.
- `test_a_column_of_arrays_is_hashed_over_its_bytes_and_not_given_up_on` -- DEAD-TARGET (kept on
  purpose) -- array-valued columns exist only in the pre-2026-09-05 frame; the calibrated frame the
  platform produces has scalar columns, hashed by the other branch of `_joined_signature`
  (`adapter.py:331`).
- `test_arrays_of_differing_lengths_are_still_hashed_value_by_value` -- DEAD-TARGET (kept on
  purpose) -- same reason.
- `test_a_file_whose_stored_key_does_not_match_is_ignored` -- DUPLICATE -- the store's own
  `test_a_file_whose_stored_signature_disagrees_is_discarded_rather_than_returned` and
  `test_a_mismatched_sidecar_is_a_miss_without_the_payload_being_opened` pin this; what this copy adds
  is only that the three-line delegation in `adapter._shared_load` still delegates.
- `test_an_oversized_entry_is_refused_rather_than_filling_the_disk` -- DUPLICATE -- the store's
  `test_an_entry_over_the_limit_is_refused_and_leaves_nothing_behind` pins it; this copy adds only that
  `adapter._SHARED_CACHE_MAX_BYTES` still reaches the store.
- `test_clearing_this_process_does_not_by_default_clear_the_shared_files` -- DEAD-TARGET --
  `clear_inputs_cache` and `inputs_cache_stats` have 0 callers outside tests (the fixture in this
  file and this test are their only users).

Note on the KEEP tests: `_psd_frame`'s docstring says "as the real frame is"; it is the frame as it
was before 2026-09-05. The memo tests that use it (`test_a_second_identical_request...`,
`test_the_joined_table_is_rebuilt_when_a_value_changes...`, `test_the_joined_table_memo_evicts...`)
test memo behaviour that does not depend on the frame's shape, so they stand, but the fixture should
be moved to the calibrated shape that `test_calibrated_join.py::_cal_frame` already builds.

### test_calibrated_join.py (107 lines, 7 tests; 6 KEEP)

- `test_the_pipeline_runs_end_to_end_on_a_calibrated_frame_and_returns_three_edges` -- SHAPE-ONLY --
  the assertions are `d["available"] is True`, `set(d["edges"]) >= {"E1", "E2", "E3"}` and
  `d["manifest"]["n_table_rows"] > 0`; no edge value is checked.

### test_clinic_steps.py (140 lines, 11 tests; 5 KEEP)

- `test_settled_window_takes_the_intersection_of_nominal_and_observed` -- DEAD-TARGET --
  `clinic_steps.settled_window` has 0 callers outside tests (search finds only its definition at
  `clinic_steps.py:130`; the `settled_window_s` field in `three_source_response.py` is a different
  thing). Not named in any decision. The reasoning it encodes lives in the module's own comments
  (`USE_INTERSECTION_OF_NOMINAL_AND_OBSERVED`, `TOTAL_SETTLED_HOURS_AT_45S_RAMP`), which survive
  without the test.
- `test_a_thirty_second_step_has_no_settled_time_at_all` -- DEAD-TARGET -- same target.
- `test_one_missing_duration_does_not_void_the_step` -- DEAD-TARGET -- same target.
- `test_the_degeneracy_guard_records_a_stricter_cluster_floor_than_the_run_used` -- DEAD-TARGET --
  `MIN_VISITS_FOR_CLUSTER_ROBUST` and `DEGENERATE_CI_WIDTH_LOG10` are defined at
  `clinic_steps.py:274` and `:278` and read by nothing outside this test; the assertion is
  `>= 8` and `0 < x < 0.01` on two constants. The constants' comments carry the 2026-09-05 lesson
  (CLAUDE.md section 2 principle 4 applies to the constants, not to this test).
- `test_settled_medians_exclude_the_ramp_and_stop_at_the_window_end` -- DEAD-TARGET (rewrite, do
  not delete) -- it calls `within_visit.step_settled_medians`, a thin alias with 0 production
  callers (`within_visit.py:561-569`: "New work should call step_settled_stats"); production calls
  `step_settled_stats` with the mean summary (`within_visit.py:613`). The ramp exclusion it checks
  is shared with the live path, so the test should point at `step_settled_stats` and move to
  `StimOptimizer/tests`, where `test_within_visit.py` already tests that function.
- `test_a_step_with_too_few_settled_tiles_is_dropped_not_imputed` -- DEAD-TARGET (rewrite, do not
  delete) -- same alias, same recommendation.

Note: `test_arm_bins_round_to_the_declared_width` is KEEP (`amplitude_arm_bins` is called at
`within_visit.py:626` and `:836`) but it tests a StimOptimizer function from this module's test
directory and is the only test of that function anywhere; it belongs in `StimOptimizer/tests`.

### test_constraints.py (911 lines, 54 tests; 49 KEEP)

- `test_every_rule_carries_its_citation_and_a_plain_english_reason` -- SHAPE-ONLY -- asserts
  `rule.title.strip()`, `rule.source.strip()`, `rule.page.strip()` and `len(rule.human_text) > 120`;
  presence and length only.
- `test_every_failure_row_carries_the_page_that_forbids_it` -- SHAPE-ONLY -- asserts
  `row["page"].strip()`, `row["source"].strip()`, `row["why"].strip()`; presence only.
- `test_the_remaining_unknown_blocks_on_the_record_as_it_stands` -- MISNAMED -- the name and the
  `rcs08_participant` fixture docstring ("the participant record as it actually stands today: D04
  and D31 unread") describe the record before 2026-09-04; `test_core.py::test_participant_scoped_device_facts_reach_the_participant_dict`
  and decision 100 record that D04 is now read from the device facts (`n_neurostimulators=1`) and
  becomes evaluable. The rule it pins (an unread D04 blocks) is still right; the name is not.
- `test_the_two_unknowns_are_distinguishable_from_an_undeclared_input` -- MISNAMED -- the name says
  "the two unknowns"; the body asserts one unknown (`by_kind["D04"]`), one undeclared input
  (`by_kind["D34"]`), and explicitly `"D31" not in by_kind` with the comment "D31 is deliberately NOT
  asserted here any more".
- `test_d30_makes_the_frequency_search_and_the_closed_loop_sequential` -- SUPERSEDED-RULE -- the
  name pins the framing the PI rejected on 2026-09-05 (`constraints._p_d30` docstring: "REWORDED
  2026-09-05 after the PI rejected the previous framing... 'of course, we can always test more open
  loop frequencies in real life'"), and D30 was changed again today (`a13bfe9b`, derived from the
  device's active sensing group). The body checks only that the retired key `frequency_search_closed`
  still works, which the last three lines of `test_d30_asks_a_per_attempt_question_not_a_permanent_one`
  already pin.

### test_core.py (1,429 lines, 67 tests; 59 KEEP)

- `test_linear_band_power_is_the_arithmetic_mean_not_the_exponentiated_mean_of_logs` --
  DEAD-TARGET (kept on purpose) -- `adapter.band_powers` is called only at `adapter.py:1123`, inside
  the branch of `joined_table` for the pre-2026-09-05 frame, which no production caller supplies
  (see "Two things" item 2 above).
- `test_band_powers_rejects_a_mismatched_frequency_axis` -- DEAD-TARGET (kept on purpose) -- same.
- `test_max_statistic_permutation_permutes_whole_epochs` -- DEAD-TARGET -- `edges.max_statistic_permutation`
  has 0 callers outside tests (definition at `edges.py:333`; no mention in any decision; the
  2026-09-03 measurement that used it is quoted in another test's docstring only).
- `test_registry_is_append_only_and_detects_tampering` -- DEAD-TARGET -- `registry.Registry` has 0
  importers anywhere; decision 109 states "no code imports registry.py, the reader written for it"
  and did not decide to keep or delete it.
- `test_registry_refuses_an_unexplained_amendment` -- DEAD-TARGET -- same.
- `test_fingerprint_tracks_array_valued_spectra_and_not_merely_the_timestamps` -- DEAD-TARGET (kept
  on purpose) -- array-column hashing is reached only by the old-frame branch of
  `_joined_signature` (`adapter.py:334`); the calibrated frame's hashing is pinned by
  `test_calibrated_join.py::test_the_fingerprint_hashes_every_band_column_so_one_changed_power_is_a_new_key`.
  The general rule it also checks (a missing named column raises) is pinned by
  `test_fingerprint_says_when_it_could_not_hash_rather_than_degrading_silently` and by
  test_adapter_caching.py.
- `test_pocket_adaptor_stays_unknown_rather_than_assumed_absent` -- LIVE-DATA -- reaches the
  database through `session_report_facts_for(RCS08 uid)` with no stub and no store override; in the
  container it can spawn a real `manage.py rebuild_session_report_summary` (see "Two things" item 1).
  It cannot silently skip, because it has no skip condition: on a machine without the database it
  falls through to the committed file and passes, so it never says which path it took. The
  assertion is `"has_pocket_adaptor" not in f or f["has_pocket_adaptor"] is None`.
- `test_capture_amplitudes_exclude_zero_because_both_must_be_therapeutic` -- SHAPE-ONLY -- every
  assertion is a substring search of `pipeline.py`'s source text (`"amps[amps > 0]" in src`,
  `"amps.min(), amps.max()" not in src`, `"(amps > 0) & (amps <= lo_a)" in src`); no pipeline run,
  no capture amplitude checked. A renamed variable would fail it and a wrong threshold would pass it.

Notes on KEEP tests in this file: the five joined-table memo tests and
`test_fingerprint_says_when_it_could_not_hash...` use `_tiny_inputs`, the old frame shape, as a
fixture only (memo and missing-column behaviour are shape-independent). Three tests
(`test_a_degenerate_time_base...`, `test_duplicate_timestamps...`, `test_sparse_coverage_forbids...`)
test `prescription.duty_cycle`, which the backend still computes and serialises (`prescription.py:624`,
`adapter.py:1433`) although the duty-cycle card was removed from the page in decision 128; live but
shown nowhere. `test_the_pipeline_resolves_the_amplitude_column...` mixes one value check
(`canonical_amp_col("Left") == "amp_mA_Left"`) with source-text checks.

### test_d19_point_signs_and_d30_active_group.py (264 lines, 20 tests, new today; 18 KEEP)

- `test_d19_human_text_records_the_pi_decision_and_its_date` -- SHAPE-ONLY -- asserts three
  substrings of the rule's prose (`"2026-09-12" in text and "POINT signs" in text`); nothing computed.
- `test_d30_human_text_records_the_pi_decision_and_its_date` -- SHAPE-ONLY -- same
  (`"option a" in text and "ACTIVE sensing group" in text`).

### test_ground_truth.py (229 lines, 11 tests; 10 KEEP)

- `test_table_from_build_has_every_column_and_tolerates_an_empty_build` -- SHAPE-ONLY -- asserts
  `list(GT.table_from_build({}).columns) == list(GT.COLUMNS)` and the same for `None`; columns only,
  no row.

### test_pooled_shape_store.py (150 lines, 9 tests; 8 KEEP)

- `test_the_stored_row_carries_every_field_the_check_reads` -- SHAPE-ONLY -- `for k in (...): assert
  k in row`; the values are checked by the two tests above it in the file.

### test_prescription_modes.py (309 lines, 15 tests; 13 KEEP)

- `test_all_three_modes_are_returned_so_the_toggle_has_something_real_to_offer` -- SHAPE-ONLY --
  `set(A["modes"]) == set(PA.MODES)`, `A["recommended"] in PA.MODES`,
  `A["recommendation"].get("recommended_because")` truthy; which mode is recommended is never checked.
- `test_one_mode_failing_does_not_lose_the_others` -- SHAPE-ONLY -- `set(A["modes"]) == set(PA.MODES)`
  and `isinstance(pr, PR.Prescription)`; and nothing in the body makes a mode fail, so the name's
  condition is not created either.

Whole-file hazard: line 13, `PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")`,
skips all 15 tests silently if that import ever fails; the conftest puts `BRAVO/modules` on the path
so it imports today, but a green run with 15 skips would look the same as a green run.

### test_protocol.py (360 lines, 28 tests; 27 KEEP)

- `test_every_step_carries_a_purpose_in_full_sentences` -- SHAPE-ONLY -- `st["purpose"].strip().endswith(".")
  and len(st["purpose"]) > 40`; prose length and a full stop.

### test_stability.py (293 lines, 21 tests; 20 KEEP)

- `test_a_test_that_raises_is_reported_not_propagated` -- DEAD-TARGET -- `stability.assess_band_stability`
  has 0 callers outside tests (definition at `stability.py:276`; the only other mention is a docstring at
  `:215`). Decision 67 chose the other route (`finding_from_stability_result`, called from
  `adapter.py` and `Biomarkers/bravo_service.py`), and `WIRING_stability_into_the_report.md` line 76
  shows `assess_band_stability` only as the route not taken. The catch-and-report-"not tested"
  behaviour it checks does not exist on the live route, which is worth the PI knowing separately.

### test_three_source_response.py (430 lines, 26 tests; 25 KEEP)

- `test_the_payload_says_which_piece_was_missing_when_there_is_no_streaming_at_all` -- SHAPE-ONLY --
  hands `report_payload` a dict with `absent_reason` set and asserts `payload["absent_reason"]` is
  truthy and `payload["comparisons"] == []`; a pass-through of its own input.

### test_track_d_grid_stability_translation.py (225 lines, 7 tests; 6 KEEP)

- `test_d2b_the_documented_disagreement_case_translates_to_cannot_tell` -- MISNAMED -- the name says
  the documented live case (ONE_THREE_LEFT at 17.5 Hz) translates to "cannot tell"; the body hands the
  translator a hand-typed dictionary and ends with `assert raw["lrt_p"] >= 0.05`, a check of the
  fixture against itself. Its own docstring says so ("it builds its raw result by hand rather than
  from live data, so it proved the translation rule and never the example"), and decision 99 accepted
  that; the name is still the untrue part. The translation rule it does check is also checked by the
  test above it in the file.

### Files with nothing to report (every test KEEP)

test_amplitude_effect.py, test_bootstrap.py, test_bravo_service.py, test_direction_consistency.py,
test_grid_matches_biomarkers_settings.py, test_pooled_e1.py, test_programmed_settings_from_epochs.py,
test_reliable_change.py, test_replay.py, test_report_contract.py, test_run_points_store.py,
test_session_report_summary_store.py, test_simulation.py.

Three notes on these. `test_bootstrap.py` tests code that now lives in
`Biomarkers/routines/analytics.py` and is re-exported by `edges.py` (lines 55-71); no test in
`Biomarkers/tests` covers it, so these are the only tests of the bootstrap and are not duplicates.
`test_session_report_summary_store.py::test_scan_documents_reads_the_d32_group...` contains one
assertion on `session_report_facts.programmed_pairs_table`, which has 0 callers outside tests
(definition at `session_report_facts.py:358`, one mention in a comment at `:352`); the rest of that
test checks live values, so the test stays. `test_report_contract.py` is entirely made of source-tree
guards (decisions 100 and 101) and is classed KEEP because each guard reads the live module's own
code and would fail on a real regression.

---

## Safe to delete now

Only DEAD-TARGET tests whose target has 0 callers outside tests and is protected by no decision,
plus the DUPLICATEs and the one SUPERSEDED-RULE whose replacement is explicit. Deleting a test here
does not delete the function it tested; that is a separate call. 20 tests.

**test_adapter_caching.py** (the `amplitude_response_cached` family, 0 callers; decisions 85/100/101
name it as uncalled and do not protect it):
`test_the_same_clinic_sheet_twice_fits_nothing_the_second_time`,
`test_an_edited_clinic_sheet_makes_the_figures_be_worked_out_again`,
`test_a_new_visit_appended_to_the_sheet_also_invalidates`,
`test_re_decoded_recordings_invalidate_even_though_the_sheet_is_untouched`,
`test_nothing_else_invalidates_the_figures`, `test_the_figures_memo_stays_bounded`,
`test_force_refresh_recomputes_even_though_nothing_changed`,
`test_a_second_process_finds_what_the_first_one_built`,
`test_a_corrupt_shared_file_is_a_miss_and_not_an_error`,
`test_clearing_this_process_does_not_by_default_clear_the_shared_files`;
and the two DUPLICATEs `test_a_file_whose_stored_key_does_not_match_is_ignored`,
`test_an_oversized_entry_is_refused_rather_than_filling_the_disk` (both pinned in
`CacheStore/tests/test_store.py`).

**test_clinic_steps.py**: `test_settled_window_takes_the_intersection_of_nominal_and_observed`,
`test_a_thirty_second_step_has_no_settled_time_at_all`, `test_one_missing_duration_does_not_void_the_step`
(`settled_window`, 0 callers, no decision);
`test_the_degeneracy_guard_records_a_stricter_cluster_floor_than_the_run_used` (two constants read
by nothing; their comments, not this test, carry the lesson).

**test_constraints.py**: `test_d30_makes_the_frequency_search_and_the_closed_loop_sequential`
(SUPERSEDED; its one surviving check is already in `test_d30_asks_a_per_attempt_question_not_a_permanent_one`).

**test_core.py**: `test_max_statistic_permutation_permutes_whole_epochs` (0 callers, no decision);
`test_registry_is_append_only_and_detects_tampering` and `test_registry_refuses_an_unexplained_amendment`
(0 importers of `registry.py`; decision 109 records that fact and decides nothing about the module,
so deleting these tests should go with a decision on `registry.py` itself).

**test_stability.py**: `test_a_test_that_raises_is_reported_not_propagated` (`assess_band_stability`,
0 callers; decision 67 took the other route).

## Rewrite, do not delete

**SHAPE-ONLY (12)**, each needs one value assertion added or a real condition created:

- `test_calibrated_join.py::test_the_pipeline_runs_end_to_end_on_a_calibrated_frame_and_returns_three_edges`
  -- assert an actual E1 or E2 estimate from the constructed frame.
- `test_constraints.py::test_every_rule_carries_its_citation_and_a_plain_english_reason` and
  `test_every_failure_row_carries_the_page_that_forbids_it` -- fold into one test that checks one
  known rule's page and source against the documents, or accept them as prose guards and say so in
  the name.
- `test_core.py::test_capture_amplitudes_exclude_zero_because_both_must_be_therapeutic` -- run the
  pipeline on a table whose smallest current is 0 mA and assert the chosen lower capture amplitude
  is above zero, instead of searching the source text.
- `test_d19_point_signs_and_d30_active_group.py::test_d19_human_text_records_the_pi_decision_and_its_date`
  and `test_d30_human_text_records_the_pi_decision_and_its_date` -- prose only; either drop or rename
  as documentation guards.
- `test_ground_truth.py::test_table_from_build_has_every_column_and_tolerates_an_empty_build` --
  add one row and check a value, or merge into `test_the_precedence_and_the_fold_ratio`.
- `test_pooled_shape_store.py::test_the_stored_row_carries_every_field_the_check_reads` -- merge into
  `test_pooled_row_matches_on_contact_and_centre_together`, which already reads the values.
- `test_prescription_modes.py::test_all_three_modes_are_returned_so_the_toggle_has_something_real_to_offer`
  -- assert which mode is recommended for the RCS08 plan; `test_one_mode_failing_does_not_lose_the_others`
  -- make one mode actually fail (the body passes `None` for everything and nothing fails).
- `test_protocol.py::test_every_step_carries_a_purpose_in_full_sentences` -- prose only.
- `test_three_source_response.py::test_the_payload_says_which_piece_was_missing_when_there_is_no_streaming_at_all`
  -- build the empty case through `build_for_participant`'s own absent path rather than passing the
  reason in and reading it back.

**MISNAMED (3)**, rename to what the body checks:

- `test_constraints.py::test_the_remaining_unknown_blocks_on_the_record_as_it_stands` -- rename to
  "an unread D04 blocks even when every other rule passes", and correct the `rcs08_participant`
  fixture docstring, which still says D04 is unread on the live record.
- `test_constraints.py::test_the_two_unknowns_are_distinguishable_from_an_undeclared_input` -- rename
  to "an unread device value and an undeclared input are labelled differently".
- `test_track_d_grid_stability_translation.py::test_d2b_the_documented_disagreement_case_translates_to_cannot_tell`
  -- rename to "a result where the interaction test does not reject and the interval is wider than the
  margin translates to cannot tell", and drop the `assert raw["lrt_p"] >= 0.05` line, which tests the
  fixture.

**LIVE-DATA (1)**:

- `test_core.py::test_pocket_adaptor_stays_unknown_rather_than_assumed_absent` -- give it the
  `temp_store` and `launcher_on` fixtures from `test_session_report_summary_store.py` (store on a
  temporary directory, launcher counted rather than spawned) and a stubbed file set, so it cannot reach
  the database or start a process; then assert `f.get("has_pocket_adaptor") is None` directly.

**DEAD-TARGET, rewrite rather than delete (2)**:

- `test_clinic_steps.py::test_settled_medians_exclude_the_ramp_and_stop_at_the_window_end` and
  `test_a_step_with_too_few_settled_tiles_is_dropped_not_imputed` -- point them at
  `within_visit.step_settled_stats` (the live function) and move them to `StimOptimizer/tests`.

## DEAD-TARGET but kept on purpose: the PI's call (5)

These test the branch of the joined table that accepts the pre-2026-09-05 one-spectrum-per-row
frame. The code is deliberately retained ("still accepted", `StimOptimizer/routines/lfp_evidence.py`
docstring at line 842) and decision 45 is what made the calibrated frame the live one. If the old
frame kind is retired, these go with it; if it stays accepted, these are its only tests.

- `test_core.py::test_linear_band_power_is_the_arithmetic_mean_not_the_exponentiated_mean_of_logs`
- `test_core.py::test_band_powers_rejects_a_mismatched_frequency_axis`
- `test_core.py::test_fingerprint_tracks_array_valued_spectra_and_not_merely_the_timestamps`
- `test_adapter_caching.py::test_a_column_of_arrays_is_hashed_over_its_bytes_and_not_given_up_on`
- `test_adapter_caching.py::test_arrays_of_differing_lengths_are_still_hashed_value_by_value`
