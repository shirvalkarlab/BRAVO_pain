"""The fast routine run's exclusions (the PI, 2026-10-05, decision 451: a quick run for routine
checks, the full run before every commit). Read by `conftest.py` (pytest marks them `slow`) and by
`_agent_bridge/run_tests.py --fast`. A name that no longer exists simply stops being skipped.

Chosen from measured run times (pytest --durations, 2026-10-05): every test of 8 s or more, and the
ControlAnalyses package (offline analyses, about 36 s of computing per run)."""

SLOW_PACKAGES = {"ControlAnalyses"}

SLOW_TESTS = {
    "test_worker_warmup.py::test_a_failing_step_is_reported_and_never_raised",
    "test_worker_warmup.py::test_the_controller_loop_and_the_replay_load_from_the_disk_cache_with_identical_results",
    "test_worker_warmup.py::test_the_warm_up_compiles_every_numba_loop_for_the_argument_types_a_request_passes",
    "test_titration_plan.py::test_the_ramp_reading_takes_the_current_out_and_keeps_the_plain_value_beside_it",
    "test_two_stage_wiring.py::test_a_clinic_sheet_sync_is_not_served_the_response_built_before_it",
    "test_two_stage_wiring.py::test_the_block_equals_a_direct_call_of_run_two_stage_live_field_for_field",
    "test_two_stage_wiring.py::test_a_flag_on_response_is_served_from_the_store_with_its_block_and_a_flag_off_one_without",
    "test_two_stage_wiring.py::test_without_the_flag_every_field_equals_the_flag_on_response_outside_the_new_block",
    "test_two_stage_wiring.py::test_the_frozen_configuration_names_the_left_contact_in_force_and_the_per_contact_table",
    "test_two_stage_wiring.py::test_a_second_site_gets_its_own_stage_one_fit_and_the_gate_stays_on_the_first",
    "test_two_stage_wiring.py::test_one_site_asked_for_means_no_parallel_block_at_all",
    "test_two_stage_wiring.py::test_a_gate_refusal_is_reported_with_its_reasons_and_stage_2_is_absent",
    "test_left_contact_groups.py::test_when_ring_2_is_truly_better_most_of_the_variation_is_the_contact",
    "test_left_contact_groups.py::test_when_the_contacts_are_identical_the_contact_share_is_small_and_not_significant",
    "test_left_contact_groups.py::test_partial_pooling_predicts_held_out_days_better_than_ignoring_the_contact",
    "test_stratum_calibration.py::test_several_fold_structures_in_one_dispatch_equal_each_asked_alone",
    "test_stratum_calibration.py::test_folds_in_worker_processes_give_the_serial_answer_bit_for_bit",
    "test_stratum_calibration.py::test_the_answer_does_not_depend_on_the_calling_process_thread_pool",
    "test_stratum_calibration.py::test_the_check_never_changes_what_the_search_recommends",
    "test_stratum_calibration.py::test_every_fitted_surface_carries_the_pre_registered_check_and_it_blocks_nothing",
    "test_stratum_calibration.py::test_with_the_setting_at_one_no_worker_process_is_asked_for",
    "test_stratum_calibration.py::test_the_check_asks_for_both_folds_in_one_dispatch_and_reports_what_it_did_before",
    "test_two_stage_adaptive_envelope.py::test_the_service_override_key_with_a_reason_returns_the_out_of_envelope_rate_with_the_reason",
    "test_two_stage_adaptive_envelope.py::test_the_service_block_excludes_the_out_of_envelope_stratum_by_default",
    "test_two_stage_adaptive_envelope.py::test_the_gate_reads_a_nan_rate_as_a_refusal_not_a_pass",
    "test_bootstrap.py::test_cr0_over_rejects_a_true_null_and_the_bootstrap_does_not",
    "test_clinic_pain.py::test_clinic_stream_fit_resolves_only_a_real_current_effect",
    "test_clinic_pain.py::test_clinic_rate_strata_rows_carry_source_clinic_sheets",
    "test_pulse_width_pooling.py::test_the_pooled_maps_check_names_the_pulse_widths_of_its_reference_setting",
    "test_pulse_width_pooling.py::test_every_fitted_pooled_map_carries_the_check_and_its_diagnosis",
    "test_pulse_width_pooling.py::test_pooling_is_skipped_with_a_reason_when_the_pairing_in_force_is_unknown",
    "test_stage2.py::test_lfp_may_be_a_factory_that_receives_the_frozen_configuration",
    "test_stage2.py::test_the_two_stage_run_reports_honestly_that_it_cannot_proceed",
    "test_stage2.py::test_supplying_the_same_gate_argument_by_both_routes_is_an_explicit_error",
    "test_stage1.py::test_the_same_matrix_with_no_current_effect_does_not_resolve_and_carries_no_current",
}


def is_slow(path, name):
    """True when the test `name` in file `path` is left out of the fast run."""
    import os
    parts = os.path.normpath(str(path)).split(os.sep)
    if any(p in SLOW_PACKAGES for p in parts):
        return True
    return f"{os.path.basename(str(path))}::{name.split('[')[0]}" in SLOW_TESTS
