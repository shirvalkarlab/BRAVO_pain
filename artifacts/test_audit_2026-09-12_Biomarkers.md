# Test audit, 2026-09-12: the Biomarkers module's tests

**Scope.** All 32 files under `BRAVO/modules/Biomarkers/tests/` (12,260 lines, 519 tests). Every
test body was read, and every production function a test calls was searched for callers across
`BRAVO/modules` and `BRAVO/Server`, excluding the tests themselves and `BRAVO/_agent_bridge`.
Nothing was run. Nothing outside this file was edited.

**How the counts were made.** "Tests" means functions named `test_*` at the top of a file, which
is exactly what the container runner (`BRAVO/_agent_bridge/run_tests.py`) collects. No test in
this module takes an argument, so none would be silently skipped by that runner for lacking pytest.
One file (`test_process_redcap.py`) has its only check in a function called `main`, which the
runner never calls -- see that file's entry.

**How a test was classified.** One class per test, using the brief's definitions. Where a test
reads the production code as TEXT (searching a function's source for a string) rather than calling
it, I counted it as KEEP but listed it separately under "Source-text guards", because the project
uses that technique on purpose (decision 96 introduced one; decision 131 records one catching a
real slip) and the principal investigator should decide about the technique as a whole, not test
by test.

---

## 1. Summary table

| File | Lines | Tests | KEEP | DEAD-TARGET | SUPERSEDED | SHAPE-ONLY | MISNAMED | DUPLICATE | LIVE-DATA |
|---|---|---|---|---|---|---|---|---|---|
| test_adapter.py | 1176 | 58 | 52 | 1 | 0 | 4 | 1 | 0 | 0 |
| test_analytics.py | 3392 | 150 | 121 | 10 | 1 | 5 | 8 | 0 | 5 |
| test_availability.py | 845 | 48 | 45 | 1 | 0 | 0 | 2 | 0 | 0 |
| test_band_candidate.py | 172 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_band_results_tables.py | 115 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_band_sweep_store.py | 222 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_band_time_sweep.py | 689 | 20 | 18 | 2 | 0 | 0 | 0 | 0 | 0 |
| test_band_time_sweep_cell.py | 112 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_channel_canon.py | 59 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_chunk_ceiling_exclusion.py | 207 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_device_spectrum_mark.py | 296 | 12 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_event_psd_taxonomy.py | 130 | 8 | 2 | 4 | 0 | 0 | 2 | 0 | 0 |
| test_live_match_vectorised.py | 344 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_match_direction.py | 126 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_match_to_pro.py | 183 | 7 | 0 | 6 | 0 | 0 | 1 | 0 | 0 |
| test_metric_precompute.py | 213 | 10 | 8 | 0 | 0 | 0 | 0 | 0 | 2 |
| test_per_pro_lsb.py | 324 | 16 | 14 | 1 | 0 | 0 | 0 | 1 | 0 |
| test_pipeline_stats.py | 221 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_process_redcap.py | 71 | 0 | 0 | 0 | 0 | 0 | (1, see note) | 0 | 0 |
| test_psd_lsb_model.py | 155 | 11 | 3 | 7 | 0 | 1 | 0 | 0 | 0 |
| test_psd_rows_manifest.py | 165 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_recording_memos_follow_the_recording_set.py | 128 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_redcap_request_scope.py | 364 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_redcap_snapshot.py | 213 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_shared_raw_lsb_cache.py | 679 | 27 | 26 | 1 | 0 | 0 | 0 | 0 | 0 |
| test_stability_background_launch.py | 414 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_stats_utils.py | 199 | 11 | 9 | 1 | 0 | 0 | 0 | 1 | 0 |
| test_sweep_match_direction.py | 166 | 11 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_sweep_statistics_exact.py | 460 | 7 | 5 | 0 | 0 | 0 | 2 | 0 | 0 |
| test_track_d_grid_export.py | 183 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_welch_missing_aware.py | 98 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| test_welch_rating_centered.py | 139 | 8 | 7 | 0 | 0 | 0 | 1 | 0 | 0 |
| **Total** | **12260** | **519** | **448** | **34** | **1** | **10** | **17** | **2** | **7** |

Of the 34 DEAD-TARGET tests, 15 test something a decision or an architecture note says to keep
(listed in §3 as "protected"); 19 test something with no caller and no protection.

---

## 2. Every non-KEEP test, file by file

Format: `test_name -- CLASS -- reason, with the evidence`. "0 callers" always means: no call
found in `BRAVO/modules` or `BRAVO/Server` outside the tests and the scratch area.

### test_adapter.py (1176 lines, 58 tests)

- `test_compute_psd_pain_correlation_runs` -- SHAPE-ONLY -- asserts only `out["psd"].shape == (5, C, F)`, `out["corr"].shape == (C, F)`, `out["pval"].shape == (C, F)`; no value is checked. (The same routine's values ARE checked by `test_compute_psd_pain_correlation_rejects_a_mostly_missing_epoch`.)
- `test_sliding_window_skips_one_class_test_folds` -- MISNAMED -- the name says a one-class fold is skipped, but the only assertion about skipping is `assert out["summary"]["n_skipped_test_one_class"] >= 0`, which cannot fail; the later `test_sliding_window_test_fold_expansion_fires_and_categorizes_skips` asserts `>= 1` and is the real check.
- `test_run_streaming_biomarker_backcompat` -- DEAD-TARGET -- `pipeline.run_streaming_biomarker` has 0 callers (the only other mention is inside an error string at `pipeline.py:498`); the body also checks only `{"result","band","combined"} <= set(out)` and `isinstance(out["combined"], pd.DataFrame)`. Not named in the decision log.
- `test_run_biomarker_both_unified_timeline` -- SHAPE-ONLY -- asserts `out["source"] == "both"`, two `is not None`, two column names present, and `n_windows >= 1`; no computed value.
- `test_merge_timelines_handles_nat_time` -- SHAPE-ONLY -- asserts `len(merged) == 5` and a column name is present; its docstring says the point is "must not crash".
- `test_return_shape_is_invariant_including_the_degenerate_path` -- SHAPE-ONLY -- asserts `len(ok) == 5 and len(tiny) == 5` and `isinstance(tiny[4], dict)`. Here the tuple length WAS the defect it guards (a 4-tuple on the early-return path), so this is low priority to rewrite.

### test_analytics.py (3392 lines, 150 tests)

- `test_cluster_scatter_two_features` -- SHAPE-ONLY -- asserts two label strings and `len(cs["x"]) == len(cs["y"]) == len(cs["pain_level"])`; no computed value.
- `test_band_mixedmodel_inference_emits_or_ci` -- SHAPE-ONLY -- if the R fit is unavailable it returns silently (`if not out.get("available"): ... return`); when it runs it asserts key names (`"odds_ratio" in out and "or_lo" in out ...`) and a bracket check that is itself conditional on all three being non-None. Also needs R (slow).
- `test_band_stim_stability_shape_and_no_stim_degrades` -- SHAPE-ONLY -- same pattern: silent return if unavailable, then `for k in (...): assert k in out` and two `set(keys) == {...}` checks. Needs R.
- `test_deployment_summary_gate_states_and_necessary_blocking` -- MISNAMED -- calls no production code at all: it defines its own `_gate` helper, builds a list of six dicts, and asserts Python arithmetic on that list (`n_passed == 4 and ready is False`). `deployment_summary` is never called.
- `test_deployment_summary_identity_is_json_serializable` -- MISNAMED -- calls no production code: it `json.dumps` a dict it built itself, with a fake class it defined itself. The real identity block is never produced.
- `test_deployment_summary_real_payload_json_serializable` -- LIVE-DATA -- runs `deployment_summary` on RCS08; returns silently in three places (`Server` not importable, participant absent, any exception in the lookup); the only unconditional assertion is `len(s) > 0`. Takes the full report's time.
- `test_deployment_summary_carries_temporal_validity_block` -- SUPERSEDED-RULE -- asserts `tv.get("threshold_drift") in ("not_assessed",)` with the comment "not yet computed (audit [18])", but `deployment_summary` computes it now: `bravo_service.py:6759` calls `analytics.threshold_drift_by_week` and `bravo_service.py:7204` writes its status (`"stable"` / `"drift_detected"` / `"not_assessed"`). The test can only pass by returning early (participant absent or `available` False) or because RCS08 happens to give `"not_assessed"` at that band. Also LIVE-DATA with two silent returns. Not an explicit decision-log entry, so it goes to the rewrite list, not the delete list.
- `test_k_cancels_in_correlation_and_auc` -- MISNAMED -- no production function is called; it proves an arithmetic identity with scipy/sklearn on arrays built in the test. The only production reference is the constant `LSB_PER_UV2_TRANSFORM`.
- `test_modeled_excluded_from_native_correlation_path` -- MISNAMED -- parts (1) and (2) are arithmetic on test arrays; part (3), "the bravo_service native-only mask", is re-implemented inside the test (`keep = ~np.array([...])`) rather than called.
- `test_deployment_summary_survives_unestimable_power_requirement` -- LIVE-DATA -- runs `deployment_summary` on RCS08; returns silently if the participant is absent or the summary is unavailable. Slow (full report).
- `test_auc_power_return_shape_is_invariant_across_all_paths` -- SHAPE-ONLY -- by name and body: compares key sets across four calls and asserts seven key names are present.
- `test_ci_crosses_chance_present_on_every_return_path` -- SHAPE-ONLY -- `assert len(shapes) == 1` and `"ci_crosses_chance" in shapes.pop()`.
- `test_one_exclusion_set_blanks_every_array_identically` -- DEAD-TARGET -- `analytics.apply_outlier_exclusion` has 0 callers; the only other mention is a docstring at `analytics.py:1247` recommending it. Not named in the decision log.
- `test_folded_auc_null_reference_formula_matches_direct_simulation` -- MISNAMED -- no production function is called: the closed form `0.5 + s*sqrt(2/pi)` is typed into the test and compared with a simulation also in the test. The production value (`null_reference_auc`, `analytics.py:1927`) is never read.
- `test_folding_reference_is_above_half_and_grows_with_noise` -- MISNAMED -- `assert 0.5 < lo < hi` on two numbers computed in the test; no production code.
- `test_rating_equal_weighting_makes_every_rating_count_once` -- MISNAMED -- no production code: the weights and the `roc_auc_score` call are both in the test.
- `test_deployment_reports_both_weightings_and_their_difference` -- LIVE-DATA -- calls `band_deployment_roc` on RCS08; returns silently unless `available`. Slow.
- `test_exploration_publishes_an_outlier_sensitivity_block` -- LIVE-DATA -- calls `run_for_participant` on RCS08 (the whole Biomarkers page compute, about 40 s); it has NO skip, so on a machine without RCS08 it fails rather than skipping; and `if blk is None: return` skips the value checks silently when the block is empty.
- `test_family_guard_passes_on_the_reconciled_left_leg_outcome` -- LIVE-DATA -- its own docstring says "each live run costs about two minutes"; `if flag is None: return` skips the value checks silently.
- `test_block_length_for_returns_one_on_both_real_dependence_regimes` -- MISNAMED -- the name says the block length is one; the body asserts only `assert L >= 1`, which any valid output satisfies.
- `test_the_exported_table_covers_every_contact_pair_and_every_band_centre_from_8_to_30_hz` -- DEAD-TARGET -- `analytics.band_pain_auc_export` has 0 callers. (The closed-loop module's `edges.state_edge` accepts such a table, but its one production caller, `ClosedLoopDeployment/pipeline.py:185`, hands in the module's own spectral-sample table, so the exported-table branch never runs.) Not named in the decision log; what shipped instead is the calibrated grid of decision 38.
- `test_the_exported_table_says_not_assessed_for_a_contact_pair_that_is_not_there` -- DEAD-TARGET -- same function, 0 callers.
- `test_the_correlation_table_covers_the_same_rows_and_is_measured_against_zero_not_half` -- DEAD-TARGET -- `band_pain_auc_export` and `band_pain_correlation_export`, both 0 callers.
- `test_the_correlation_says_none_where_the_other_table_says_how_pain_was_split` -- DEAD-TARGET -- `analytics.band_pain_correlation` is called only from `band_pain_correlation_export` (`analytics.py:4854`, `:4859`), itself 0 callers.
- `test_the_correlation_moves_with_the_power_scale_and_the_other_number_does_not` -- DEAD-TARGET -- half of it tests `band_pain_correlation` (dead, above); the AUC half is live (`band_pain_auc` is reached through `band_pain_auc_from_table`, called by `ClosedLoopDeployment/edges.py:253`).
- `test_the_correlation_table_also_reports_the_value_with_the_logarithm_undone` -- DEAD-TARGET -- `band_pain_correlation_export`, 0 callers.
- `test_reading_a_band_that_is_not_in_the_exported_table_says_not_assessed_and_carries_no_value` -- DEAD-TARGET -- `read_band_pain_auc_from_export` is called only on the `from_export` branch of `edges.state_edge` (`edges.py:249`), which the one production caller never reaches (see above).
- `test_pooled_psd_detail_is_per_channel_and_matches_pro` -- DEAD-TARGET -- `streaming_psd.build_pooled_psd_detail` has 0 callers; the live path is `build_pooled_detail_from_matrix` (`bravo_service.py:3265`, `:4661`). Not named in the decision log.
- `test_cv_logistic_auc_oriented_and_guards_small_n` -- DEAD-TARGET -- `analytics._cv_logistic_auc` has 0 callers; the only mention is a comment at `pipeline.py:681`. Not named in the decision log.

### test_availability.py (845 lines, 48 tests)

- `test_lsb_series_indexed_path_matches_scan_on_the_four_existing_fixtures` -- MISNAMED -- the name says four fixtures; the body's `cases` list has two, and its own print says "both of the simpler existing fixtures".
- `test_montage_event_dedup_against_psd_times` -- MISNAMED -- calls no production code: the bisect-based duplicate check is written out inside the test ("mirrors the dedup in bravo_service._load_montage_psd_events") and tested against itself; `_load_montage_psd_events` (`bravo_service.py:1680`) is never called.
- `test_modeled_lsb_at_center_psd_tier_band_gated_and_freq_first` -- DEAD-TARGET (protected) -- the branch it tests is `modeled_lsb_at_center(..., psd_recordings=...)`; both production call sites pass `psd_recordings=None` (`bravo_service.py:6507`, `:6812`). Decision 71 says this tier was deliberately left as its own scan because no live data reaches it. Keep unless that decision changes.

### test_band_time_sweep.py (689 lines, 20 tests)

- `test_the_two_matrices_and_the_full_grid_come_out_readable` -- DEAD-TARGET -- `analytics.band_time_sweep_tables` has 0 callers; the tables that are actually stored come from `band_results_tables.correlation_table` / `discrimination_table` (`bravo_service.py:8072-8073`, decision 38). Not named in the decision log.
- `test_colour_scales_are_centred_on_the_right_no_relationship_value` -- DEAD-TARGET (protected) -- it tests the server-drawn figures (`band_time_sweep_figures`). The server still builds them on every sweep (`bravo_service.py:7487`) and puts them in the response, but the only page code that ever read them, `Client/src/views/Reports/Biomarkers/BandTimeSweepPanel.js`, is imported by nothing (the only mention is a comment at `Biomarkers/index.js:23`); the heat maps on screen are drawn in the browser from the grids (decisions 66, 87). Decision 80 records the panel file as "deliberately kept", so this is the principal investigator's call: delete the server figure build and this test together, or keep both. Rule 13: this field is on no page today.

### test_event_psd_taxonomy.py (130 lines, 8 tests)

The dictionary `bravo_service.PSD_SOURCE_TAXONOMY` (`bravo_service.py:99`) is read by nothing in production: the only mentions repo-wide are its definition and this test file. Its own comment ("Consumed by the event loaders, the timeline assembler, and the CS-3 bridge") is not true today. Not named in the decision log.

- `test_streaming_and_labeled_share_pooling_source_but_differ_in_display` -- DEAD-TARGET -- reads only `PSD_SOURCE_TAXONOMY`.
- `test_taxonomy_lsb_routing_rule_matches_td_presence` -- DEAD-TARGET -- reads only `PSD_SOURCE_TAXONOMY`.
- `test_taxonomy_three_sources_have_distinct_display_categories` -- DEAD-TARGET -- reads only `PSD_SOURCE_TAXONOMY` (`assert len(disp) == 3`).
- `test_event_units_described_as_linear_not_log_after_cs3` -- DEAD-TARGET -- reads only the `"units"` text inside `PSD_SOURCE_TAXONOMY`.
- `test_labeled_streaming_split_for_diamond_row_and_count` -- MISNAMED -- the name and docstring say the assembler's split is pinned; the split is performed inside the test body ("the exact split the assembler performs") and the assembler (`bravo_service.py:3770-3773`) is never called; only `availability.event_markers` on the hand-split list is.
- `test_event_psd_lsb_blocks_only_consumes_psd_only_events` -- MISNAMED -- the builder is never called: `assert hasattr(bs, "_event_psd_lsb_blocks")`, then a constant identity (which `test_bridge_constants_compose_from_transform_and_td_psd_ratio` in test_analytics already pins) and two taxonomy reads.

### test_match_to_pro.py (183 lines, 7 tests)

`streaming_psd._match_to_pro` has 0 production callers since decision 117 moved the pooled-detail builder onto `DecodeCommon.matching.matched_samples` (`streaming_psd.py:865`). Decision 117 says it "stays as the reference implementation" that `DecodeCommon/tests/test_matching.py` proves the shared matcher against, so these are protected.

- `test_prior_direction_requires_psd_before_pro` -- DEAD-TARGET (protected, decision 117).
- `test_nearest_direction_matches_either_side` -- DEAD-TARGET (protected, decision 117).
- `test_pro_first_maximizes_pro_coverage_over_psd_first` -- DEAD-TARGET (protected, decision 117).
- `test_pro_first_enforces_per_channel_cap` -- DEAD-TARGET (protected, decision 117).
- `test_pro_first_falls_back_to_nearest_on_misuse` -- DEAD-TARGET (protected, decision 117).
- `test_pro_first_dt_sign_convention_unchanged` -- DEAD-TARGET (protected, decision 117).
- `test_prior_no_lookahead_invariant_survives_full_pooled_pipeline` -- MISNAMED -- the name says the no-look-ahead property survives the pooled pipeline; the `dt` values it checks come from a separate `_match_to_pro` call made inside the test, which the pipeline no longer uses; the pipeline's own output is checked only by `assert np.isfinite(pooled_labels).any()`.

### test_metric_precompute.py (213 lines, 10 tests)

- `test_the_launcher_asks_for_every_score_except_the_one_just_built` -- LIVE-DATA -- needs `manage.py` beside the module (container layout); `if argv is None: return` makes it pass silently anywhere else.
- `test_the_settings_carried_to_the_background_run_are_a_whitelist_and_exclude_the_score` -- LIVE-DATA -- same silent `return` on `argv is None`.

### test_per_pro_lsb.py (324 lines, 16 tests)

- `test_agg_none_returns_per_window_and_median_matches` -- DEAD-TARGET (protected) -- `td_transform_band_power(agg="none")` has 0 production callers since decision 110 deleted the per-rating trace; the note at `availability.py:2173` says the mode "stays, since it is a general capability". Keep unless that note is reversed.
- `test_live_match_per_modality_independence` -- DUPLICATE of `test_live_match_strict_no_reuse_default` -- same fixture (`_raw_cache_fixture`), same call (`live_lsb_spectrum_match(pro, raw, extent_s=30.0)`), and its three assertions (`recs[0]["tier"] == TD`, `recs[1]["tier"] == BRIDGE`, the two differ) are a subset of what the first test already asserts.
- File note: the docstring still promises a "sliding-window overlay" test; that overlay was deleted (decision 110) and no such test remains.

### test_process_redcap.py (71 lines, 0 tests)

- `main` -- MISNAMED (never collected) -- this is a real, value-checking test of `redcap_client.process_redcap` (which IS live: `bravo_service.py:3201`), but it is named `main`, so the container runner never calls it and it has not run in the container since it was written. Rename to `test_process_redcap`. It also imports with the host spelling (`from Biomarkers.routines import redcap_client`) after inserting `BRAVO/modules` on the path, which works but is the second spelling of that module in one process.

### test_psd_lsb_model.py (155 lines, 11 tests)

`psd_lsb_model.estimate_lsb` has 0 production callers. The comment at `bravo_service.py:6408-6418` records that the path which fed it was removed on 2026-06-28 (decision 21: the switching value is never converted), and the only other mentions (`availability.py:933`, `analytics.py:2966`) are docstrings. The frozen model file itself (`data/psd_lsb_models/RCS08.json`) is still read by the live `model_plot_payload` (`bravo_service.py:6335`), so the file and `load_model` stay.

- `test_tier2_exact_band` -- DEAD-TARGET -- `estimate_lsb`, 0 callers.
- `test_tier2_power_dependent_gain` -- DEAD-TARGET -- same.
- `test_tier3_nearest_frequency` -- DEAD-TARGET -- same.
- `test_tier4_channel_pooled` -- DEAD-TARGET -- same.
- `test_none_when_unmodelable` -- DEAD-TARGET -- same.
- `test_array_input_mirrors_shape` -- DEAD-TARGET -- same.
- `test_highgamma_estimate_flagged_extrapolated` -- DEAD-TARGET -- same (the shared extrapolation rule it also touches is pinned live by `test_freq_extrapolated_guard_agrees_with_frozen_model` in test_analytics).
- `test_plot_payload_shape` -- SHAPE-ONLY -- `assert len(fittable) >= 2`, `is not None`, `len(c["bands"]) >= 2`, and a key-subset check; no value from the payload.

### test_shared_raw_lsb_cache.py (679 lines, 27 tests)

- `test_the_reported_numbers_describe_what_the_files_did` -- DEAD-TARGET (protected) -- `bravo_service.shared_cache_stats` has 0 production callers; `ARCHITECTURE_cache_store.md` §3 says the name is kept "because their own tests and three bridge scripts call them". Keep unless that note changes.
- File hazard (not a per-test class): the bench replaces the recording-identity function with `_Bench._identity`, described as "the real function's body with the query removed" -- a hand copy of `_raw_lsb_recording_identity`. If the real function changes (decision 130 added a separate identity helper the same week), this copy drifts silently and the key tests keep passing. This is the shape of decision 96's finding.

### test_stats_utils.py (199 lines, 11 tests)

- `test_bh_fdr` -- DUPLICATE of `test_bh_fdr_matches_statsmodels_independent_implementation` -- the second test compares `bh_fdr` with statsmodels on the identical array `[0.001, 0.04, 0.30, 0.50, 0.90]` and on a NaN-carrying array; agreement with the reference implies every assertion in the first (bounds, monotone after sorting, which entries survive, NaN preserved).
- `test_block_perm_pvalue` -- DEAD-TARGET -- `stats_utils.block_perm_pvalue` has 0 callers; `pipeline.py:854` records that it was replaced by the vectorised `_block_perm_maxcorr_pvalue`. Not named in the decision log.

### test_sweep_statistics_exact.py (460 lines, 7 tests)

- `test_resampled_correlation_with_reused_buffers_is_identical` -- MISNAMED -- no production code is called: both routes (`_plain_bootstrap_correlations` and `_reused_buffer_bootstrap_correlations`, "the form the sweep uses now") are functions defined in the test file, so it compares a copy against a copy.
- `test_a_wide_matrix_product_gives_the_same_numbers_as_narrow_ones` -- MISNAMED -- no production code is called; it checks a property of numpy's matrix product. Its docstring is honest about that and explains why the guard exists (the sweep's shuffled reference relies on it), so this is a deliberate library guard rather than a mistake; it is listed here only because nothing of the project's own is under test.

### test_welch_rating_centered.py (139 lines, 8 tests)

- `test_partial_floor_drop_keeps_only_surviving_ratings` -- MISNAMED -- the name says some ratings fall below the minimum-length floor; the body asserts `kept.tolist() == [True, True]` and `psd.shape[0] == 2`, so nothing is dropped (its own comment says the clipped window is 15.2 s, above the 10 s floor).

### Files with every test KEEP

test_band_candidate.py, test_band_results_tables.py, test_band_sweep_store.py,
test_band_time_sweep_cell.py, test_channel_canon.py, test_chunk_ceiling_exclusion.py,
test_device_spectrum_mark.py, test_live_match_vectorised.py, test_match_direction.py,
test_pipeline_stats.py, test_psd_rows_manifest.py, test_recording_memos_follow_the_recording_set.py,
test_redcap_request_scope.py, test_redcap_snapshot.py, test_stability_background_launch.py,
test_sweep_match_direction.py, test_track_d_grid_export.py, test_welch_missing_aware.py.

Two rule-13 notes on KEEP files, because the tests are sound but the things they pin are on no
page:

- `test_device_spectrum_mark.py`: the per-cell share fields (`device_spectrum_share_grid`,
  `device_spectrum_n_grid`, the `_auc` trio, and the headline row's `device_spectrum_share`) are
  computed on every sweep but, since decision 121 removed the per-cell dash markers, the page reads
  only the count and the total (`BiomarkerHeatmapGrids.js:129`, `:582-584`) for its caption.
- `test_adapter.py`: `compute_psd_pain_correlation` is reached in production (`pipeline.py:622`)
  but decision 77 records it has no frontend consumer; its tests are correct, its output is drawn
  nowhere.

---

## 3. Safe to delete now

Only DEAD-TARGET tests with 0 callers and no decision or architecture note protecting them, plus
the two DUPLICATEs. Deleting a DEAD-TARGET test leaves its function untested but also uncalled;
whether the function goes with it is the principal investigator's call (the pattern in CLAUDE.md
§2 principle 4 applies -- several things here were built ahead of a page that never came).

1. `test_adapter.py::test_run_streaming_biomarker_backcompat` -- `pipeline.run_streaming_biomarker`, 0 callers.
2. `test_analytics.py::test_one_exclusion_set_blanks_every_array_identically` -- `analytics.apply_outlier_exclusion`, 0 callers (a docstring at `analytics.py:1247` recommends it; if the function stays, keep this test).
3. `test_analytics.py::test_the_exported_table_covers_every_contact_pair_and_every_band_centre_from_8_to_30_hz` -- `band_pain_auc_export`, 0 callers.
4. `test_analytics.py::test_the_exported_table_says_not_assessed_for_a_contact_pair_that_is_not_there` -- same.
5. `test_analytics.py::test_the_correlation_table_covers_the_same_rows_and_is_measured_against_zero_not_half` -- both export functions, 0 callers.
6. `test_analytics.py::test_the_correlation_says_none_where_the_other_table_says_how_pain_was_split` -- `band_pain_correlation`, reached only from the dead export.
7. `test_analytics.py::test_the_correlation_moves_with_the_power_scale_and_the_other_number_does_not` -- half dead (correlation); keep the AUC half if the export goes.
8. `test_analytics.py::test_the_correlation_table_also_reports_the_value_with_the_logarithm_undone` -- `band_pain_correlation_export`, 0 callers.
9. `test_analytics.py::test_reading_a_band_that_is_not_in_the_exported_table_says_not_assessed_and_carries_no_value` -- `read_band_pain_auc_from_export`, reached only on a branch no production caller takes.
10. `test_analytics.py::test_pooled_psd_detail_is_per_channel_and_matches_pro` -- `build_pooled_psd_detail`, 0 callers.
11. `test_analytics.py::test_cv_logistic_auc_oriented_and_guards_small_n` -- `_cv_logistic_auc`, 0 callers.
12. `test_band_time_sweep.py::test_the_two_matrices_and_the_full_grid_come_out_readable` -- `band_time_sweep_tables`, 0 callers.
13. `test_event_psd_taxonomy.py::test_streaming_and_labeled_share_pooling_source_but_differ_in_display` -- `PSD_SOURCE_TAXONOMY`, read by nothing.
14. `test_event_psd_taxonomy.py::test_taxonomy_lsb_routing_rule_matches_td_presence` -- same.
15. `test_event_psd_taxonomy.py::test_taxonomy_three_sources_have_distinct_display_categories` -- same.
16. `test_event_psd_taxonomy.py::test_event_units_described_as_linear_not_log_after_cs3` -- same.
17. `test_psd_lsb_model.py::test_tier2_exact_band` -- `estimate_lsb`, 0 callers (decision 21 removed its only path).
18. `test_psd_lsb_model.py::test_tier2_power_dependent_gain` -- same.
19. `test_psd_lsb_model.py::test_tier3_nearest_frequency` -- same.
20. `test_psd_lsb_model.py::test_tier4_channel_pooled` -- same.
21. `test_psd_lsb_model.py::test_none_when_unmodelable` -- same.
22. `test_psd_lsb_model.py::test_array_input_mirrors_shape` -- same.
23. `test_psd_lsb_model.py::test_highgamma_estimate_flagged_extrapolated` -- same.
24. `test_stats_utils.py::test_block_perm_pvalue` -- `stats_utils.block_perm_pvalue`, 0 callers.
25. `test_stats_utils.py::test_bh_fdr` -- DUPLICATE of the statsmodels comparison.
26. `test_per_pro_lsb.py::test_live_match_per_modality_independence` -- DUPLICATE of `test_live_match_strict_no_reuse_default`.

**Protected DEAD-TARGETs, NOT safe to delete** (a decision or note says the target stays):
the six `_match_to_pro` tests in `test_match_to_pro.py` (decision 117: reference implementation);
`test_per_pro_lsb.py::test_agg_none_returns_per_window_and_median_matches` (note at
`availability.py:2173`, decision 110); `test_shared_raw_lsb_cache.py::test_the_reported_numbers_describe_what_the_files_did`
(`ARCHITECTURE_cache_store.md` §3); `test_availability.py::test_modeled_lsb_at_center_psd_tier_band_gated_and_freq_first`
(decision 71); `test_band_time_sweep.py::test_colour_scales_are_centred_on_the_right_no_relationship_value`
(decision 80 keeps the panel file the figures were built for).

---

## 4. Rewrite, do not delete

MISNAMED and SHAPE-ONLY tests, plus the one SUPERSEDED-RULE and the uncollected `main`. For each,
what the rewrite is.

- `test_adapter.py::test_compute_psd_pain_correlation_runs` -- add one value: e.g. the planted increasing-pain labels give a positive correlation at the 20 Hz bin on channel 0.
- `test_adapter.py::test_sliding_window_skips_one_class_test_folds` -- either assert `n_skipped_test_one_class >= 1` on a fixture that really produces a skip, or delete it as a weaker copy of `test_sliding_window_test_fold_expansion_fires_and_categorizes_skips`.
- `test_adapter.py::test_run_biomarker_both_unified_timeline` -- assert one number from each branch (the chronic threshold lies between the two planted power levels; the time-domain band is the planted one).
- `test_adapter.py::test_merge_timelines_handles_nat_time` -- assert which rows matched and which did not (the NaT row must not join any chronic row).
- `test_adapter.py::test_return_shape_is_invariant_including_the_degenerate_path` -- low priority; add that `tiny[4]["reason"]` names the input as too small.
- `test_analytics.py::test_cluster_scatter_two_features` -- assert the de-duplicated point set against the unique (vas, mpq) pairs of the fixture.
- `test_analytics.py::test_band_mixedmodel_inference_emits_or_ci` -- in the container R is present, so drop the silent return and assert the planted positive relationship gives an odds ratio above 1 with a bracketing interval.
- `test_analytics.py::test_band_stim_stability_shape_and_no_stim_degrades` -- same: assert the era counts equal the thirds the fixture built, and the verdict on a planted stable band.
- `test_analytics.py::test_deployment_summary_gate_states_and_necessary_blocking` -- call the real gate assembly (`_deployment_summary_stim_stable_gate`, `_deployment_summary_adaptive_band_gate` are already pinned in test_band_candidate); either point this test at `deployment_summary` on a stub, or delete it as testing nothing.
- `test_analytics.py::test_deployment_summary_identity_is_json_serializable` -- covered live by `test_deployment_summary_real_payload_json_serializable`; either delete, or make it call `deployment_summary` with the participant lookup stubbed.
- `test_analytics.py::test_deployment_summary_carries_temporal_validity_block` -- change the assertion to the current three values (`"stable"`, `"drift_detected"`, `"not_assessed"`), and remove the stale "not yet computed" comment; consider stubbing the participant so it does not skip.
- `test_analytics.py::test_k_cancels_in_correlation_and_auc` -- make it call `deployment_roc` or `band_pain_auc` twice with the power multiplied by two constants and assert the AUC and correlation are byte-identical; that is the claim as it applies to this code.
- `test_analytics.py::test_modeled_excluded_from_native_correlation_path` -- call the real masking code (`_modeled_lsb_threshold_estimate` or the native-only selection in `bravo_service`) rather than re-typing the mask.
- `test_analytics.py::test_auc_power_return_shape_is_invariant_across_all_paths` and `test_ci_crosses_chance_present_on_every_return_path` -- keep the key-set check but add the `status` and `reason` values each path must give.
- `test_analytics.py::test_folded_auc_null_reference_formula_matches_direct_simulation` -- read `null_reference_auc` off a real `deployment_roc` result and compare it with the simulation at that result's bootstrap spread.
- `test_analytics.py::test_folding_reference_is_above_half_and_grows_with_noise` -- fold into the test above or delete; as written it cannot fail.
- `test_analytics.py::test_rating_equal_weighting_makes_every_rating_count_once` -- call `band_pain_auc` on the fixture and assert `auc` differs from `auc_per_sample` in the documented direction (that is what `test_a_pain_report_covered_by_many_recordings_does_not_get_more_say_than_one_covered_by_few` already does; delete if that suffices).
- `test_analytics.py::test_block_length_for_returns_one_on_both_real_dependence_regimes` -- assert `L == 1`, which is what the name and docstring claim.
- `test_availability.py::test_lsb_series_indexed_path_matches_scan_on_the_four_existing_fixtures` -- rename to "two", or add the two missing fixtures (the montage-TD and the ring-name cases from the tests above it).
- `test_availability.py::test_montage_event_dedup_against_psd_times` -- call `_load_montage_psd_events` with the database stubbed, or delete; today it tests only itself.
- `test_event_psd_taxonomy.py::test_labeled_streaming_split_for_diamond_row_and_count` -- call the assembler (`_build_availability`) with the event loader stubbed and read `events["n"]` and `streaming_count` off its output.
- `test_event_psd_taxonomy.py::test_event_psd_lsb_blocks_only_consumes_psd_only_events` -- call `_event_psd_lsb_blocks` on a stubbed event row set that mixes a montage record in, and assert the montage record is not in the output.
- `test_match_to_pro.py::test_prior_no_lookahead_invariant_survives_full_pooled_pipeline` -- read the offsets off the pooled detail's own `dt_min` (it is returned) and assert every retained row has `dt_min >= 0`.
- `test_process_redcap.py::main` -- rename to `test_process_redcap` so the container runner collects it.
- `test_psd_lsb_model.py::test_plot_payload_shape` -- assert one number from the payload against the frozen JSON (e.g. the 8.8 Hz intercept already pinned in `test_8p8hz_cut_is_current_config_not_changepoint_date`).
- `test_sweep_statistics_exact.py::test_resampled_correlation_with_reused_buffers_is_identical` -- call the sweep's own bootstrap (the function inside `band_time_sweep_from_power` that produces `pearson_r_low/high`) against the plain form, instead of two test-local copies.
- `test_sweep_statistics_exact.py::test_a_wide_matrix_product_gives_the_same_numbers_as_narrow_ones` -- acceptable as a deliberate library guard; if kept, say so in the name (e.g. `test_numpy_wide_matmul_equals_narrow_...`).
- `test_welch_rating_centered.py::test_partial_floor_drop_keeps_only_surviving_ratings` -- put one rating close enough to the edge to fall below the 10 s floor (e.g. a 6 s session) and assert `kept == [True, False]` and `psd.shape[0] == 1`; or rename.

---

## 5. Source-text guards (counted as KEEP; one decision for the whole set)

These read a function's source (or the file's syntax tree) and assert a string is or is not in
it. They check no runtime value. The project uses them on purpose and one caught a real slip
(decision 131), so they are counted KEEP here and listed for a single decision:

- `test_analytics.py`: `test_design_effect_clamp_is_reported`, `test_iid_ci_is_suppressed_under_the_same_floor_as_the_headline_ci`, `test_the_burn_in_exclusion_does_not_leak_into_the_era_stability_test`, `test_all_deployment_binarizations_pass_rating_group` (syntax tree), `test_the_old_straight_line_calculation_is_gone_from_this_page` (`hasattr` absence).
- `test_event_psd_taxonomy.py`: `test_streaming_is_no_longer_globally_excluded` (`hasattr` absence).
- `test_recording_memos_follow_the_recording_set.py`: `test_the_timeline_result_key_carries_the_recording_set`.
- `test_stability_background_launch.py`: `test_the_setting_whitelist_covers_every_request_field_the_sweep_reads`, `test_the_whitelist_carries_nothing_the_sweep_does_not_read`, `test_the_computation_takes_the_sweeps_key_and_never_derives_one_of_its_own`, `test_the_key_tuple_has_exactly_one_definition`, `test_both_of_the_sweeps_return_paths_start_the_background_run`, and one assertion inside `test_the_points_of_a_grid_are_read_the_same_way_everywhere`.
- `test_sweep_match_direction.py`: `test_run_for_participant_and_validate_band_core_both_use_the_shared_forecast_helper`, `test_the_grid_endpoint_and_the_cell_endpoint_call_the_one_shared_helper`.

---

## 6. Tests likely to take more than 5 seconds (read, not timed)

The orchestrator runs the suite; these are the ones whose bodies show why they would be slow.

- `test_analytics.py`: `test_exploration_publishes_an_outlier_sensitivity_block` (whole Biomarkers page compute on RCS08, about 40 s by decision 117's timings); `test_family_guard_passes_on_the_reconciled_left_leg_outcome` (its docstring: about two minutes); `test_deployment_summary_real_payload_json_serializable`, `test_deployment_summary_carries_temporal_validity_block`, `test_deployment_summary_survives_unestimable_power_requirement` (each runs the full sign-off summary on RCS08, including R fits); `test_deployment_reports_both_weightings_and_their_difference` (live ROC on RCS08); `test_band_mixedmodel_inference_emits_or_ci`, `test_band_stim_stability_shape_and_no_stim_degrades`, `test_validation_mixed_model_excludes_the_first_three_weeks_and_says_so` (R mixed-model fits); `test_sliding_window_emits_per_window_roc` (57,600-row frame through the sliding detector); `test_block_bootstrap_block_len_1_reproduces_iid_loop` (3,000 sklearn AUC calls in a Python loop); `test_best_threshold_balanced_auc_matches_reference` (150 trials x 140 thresholds of sklearn AUC in the reference loop); `test_bca_matches_scipy_on_iid_skewed_statistic` (scipy bootstrap with 20,000 resamples); the three `test_forward_chaining_*` with `n_boot=500`.
- `test_band_time_sweep.py`: every test that calls `band_time_sweep_from_power` on the 98-centre synthetic grid with hundreds of shuffles and resamples -- especially `test_sweep_honours_the_top_of_page_settings` (six sweeps), `test_a_value_that_does_not_beat_the_shuffled_best_of_ten_is_not_established`, `test_a_planted_relationship_is_found_at_the_right_band`, `test_a_planted_band_ranks_best_under_the_family_wise_correction_and_pure_noise_mostly_clears` (two sweeps at 500/500), and `test_fitted_logistic_is_the_ordering_or_one_minus_it_on_every_cell` (about 220 logistic fits).
- `test_sweep_statistics_exact.py`: `test_grids_match_a_plain_loop_over_lengths_and_band_centres` (five sweeps at the production default shuffle counts, then a pure-Python double loop with a pairwise Mann-Whitney count per cell); `test_the_ten_lengths_are_each_their_own_length_and_not_one_repeated` (one sweep at defaults).
- `test_adapter.py`: `test_run_biomarker_both_unified_timeline` and `test_run_streaming_biomarker_backcompat` (each runs the whole pipeline, including the 1,000-shuffle permutation test).

---

## 7. Other hazards seen while reading

1. **A stub that can leak between files.** `test_availability.py` defines its own `_import_service()` (line 632) that replaces `modules.Biomarkers.routines.redcap_client` in `sys.modules` with a `MagicMock` if it is not already loaded. In the container's single-process run it is harmless only because `test_analytics.py` (alphabetically earlier) imports the real `bravo_service`, which loads the real `redcap_client` first. Run `test_availability.py` before `test_analytics.py`, or without it, and every later REDCap test would be handed a mock. The other three files with an `_import_service` do not stub `redcap_client`.
2. **`PSD_SOURCE_TAXONOMY`'s comment is wrong** (`bravo_service.py:97-98` says loaders, assembler and bridge consume it; nothing does). Worth correcting whether or not the dictionary stays.
3. **Two docstrings out of date:** `test_per_pro_lsb.py` (promises a sliding-window overlay test that decision 110 removed) and `test_analytics.py::test_deployment_summary_carries_temporal_validity_block` ("not yet computed").
4. **Hand copies of production logic inside fixtures**, the shape decision 96 warned about: `test_shared_raw_lsb_cache.py::_Bench._identity` (a copy of the recording-identity function's body); `test_analytics.py::test_modeled_transform_point_stays_flagged_native_preferred` part (2) (a copy of the native-only mask, beside a real call in part (1)).
5. **Decision 117's dead branch is not exercised by any test**: `build_pooled_detail_from_matrix(aggregate="one_per_rating")` crashes (recorded in decision 117) and no test in this module passes that value, so nothing here will notice if it is revived.
