"""Layer 1 of the shared matching design: `matched_samples`'s three directions and its
per-(group, rating) refractory-gap independence cap.

`test_direction_handling_matches_the_source_function_exactly` cross-imports
`Biomarkers.routines.streaming_psd._match_to_pro`, the function this module's direction handling
was ported from -- both spellings, the same pattern `test_decode_common.py` already uses to
cross-check the decoded form against Biomarkers, proven on both runners (decision 42; Biomarkers
is importable via plain PYTHONPATH on the host even though the host suite does not collect its own
tests). The refractory-gap cap is verified separately, against hand-computed fixtures below,
because it is a smaller, self-contained block read directly from
`build_pooled_detail_from_matrix` rather than a whole function that can be called side by side.
"""
import numpy as np

try:
    from modules.DecodeCommon import matching
except ImportError:
    from DecodeCommon import matching

try:
    from modules.Biomarkers.routines import streaming_psd
except ImportError:
    from Biomarkers.routines import streaming_psd


def test_nearest_matches_symmetrically_within_tolerance():
    sample_times = [0.0, 100.0, 1000.0]
    pro_times = [50.0, 5000.0]
    pro_values = [3.0, 7.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=1.0, direction="nearest")
    assert out["matched_value"][0] == 3.0   # 50 s away, within the 60 s tolerance
    assert out["matched_value"][1] == 3.0   # also nearest to the same report
    assert np.isnan(out["matched_value"][2])  # 1000 s from the nearer report, outside tolerance
    assert abs(out["dt_min"][0] - 50.0 / 60.0) < 1e-9
    assert out["rating_cluster_id"][0] == 0


def test_direction_handling_matches_the_source_function_exactly():
    """The core claim this module makes about itself: its three-direction matching is the same
    algorithm as `_match_to_pro`, not a fresh reimplementation that happens to look similar.
    Compared on 200 constructed cases per direction, random sample/report times and a random
    per-sample channel, field for field (matched value, signed offset, matched-report index).
    """
    rng = np.random.RandomState(7)
    for direction in ("nearest", "prior", "pro_first"):
        for trial in range(200):
            n_samples = rng.randint(1, 12)
            n_pro = rng.randint(1, 6)
            sample_times = rng.uniform(0, 3600, n_samples)
            pro_times = rng.uniform(0, 3600, n_pro)
            pro_values = rng.uniform(-5, 5, n_pro)
            tol_min = rng.uniform(0.5, 10.0)
            channels = rng.choice(["A", "B"], size=n_samples)
            max_per_rating = int(rng.randint(1, 4)) if direction == "pro_first" else None

            ours = matching.matched_samples(
                sample_times, sample_times, pro_times, pro_values, tolerance_min=tol_min,
                direction=direction, group_keys=channels, max_per_rating=max_per_rating)
            theirs_label, theirs_dt, theirs_idx = streaming_psd._match_to_pro(
                sample_times, pro_times, pro_values, tol_min, direction=direction,
                channels=channels, max_per_rating=max_per_rating)

            np.testing.assert_array_equal(
                np.isnan(ours["matched_value"]), np.isnan(theirs_label),
                err_msg=f"{direction} trial {trial}: which samples matched disagrees")
            ok = ~np.isnan(theirs_label)
            np.testing.assert_allclose(ours["matched_value"][ok], theirs_label[ok])
            np.testing.assert_allclose(ours["dt_min"][ok], theirs_dt[ok])
            np.testing.assert_array_equal(ours["rating_cluster_id"][ok], theirs_idx[ok])


def test_prior_only_matches_reports_at_or_after_the_sample():
    sample_times = [0.0, 200.0]
    pro_times = [100.0, -50.0]  # report 1 is BEFORE sample 0; must never match under "prior"
    pro_values = [5.0, 9.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=10.0, direction="prior")
    assert out["matched_value"][0] == 5.0   # only the report at t=100 qualifies (t >= sample time)
    assert out["dt_min"][0] >= 0
    assert np.isnan(out["matched_value"][1])  # no report at or after t=200 within tolerance


def test_pro_first_claims_up_to_max_per_rating_per_group_and_never_reuses_a_sample():
    sample_times = [0.0, 1.0, 2.0, 3.0, 100.0]
    groups = ["A", "A", "A", "B", "A"]
    pro_times = [1.5]
    pro_values = [4.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=1.0, direction="pro_first",
                                   group_keys=groups, max_per_rating=2)
    # group A has three candidates within tolerance (0, 1, 2); only the 2 closest are claimed
    claimed_a = [i for i in (0, 1, 2) if not np.isnan(out["matched_value"][i])]
    assert len(claimed_a) == 2
    assert 1 in claimed_a and 2 in claimed_a  # the two closest to t=1.5
    assert 0 not in claimed_a
    # group B has exactly one candidate and it is claimed
    assert out["matched_value"][3] == 4.0
    # the far sample (t=100) is outside tolerance regardless of group
    assert np.isnan(out["matched_value"][4])


def test_pro_first_without_group_keys_or_cap_falls_back_to_nearest():
    out = matching.matched_samples([0.0], [0.0], [10.0], [1.0], tolerance_min=1.0,
                                   direction="pro_first", max_per_rating=None)
    assert out["matched_value"][0] == 1.0  # behaved like "nearest" rather than matching nothing


def test_refractory_cap_keeps_the_closest_and_drops_a_burst():
    # Three samples all within tolerance of one report, but two of them (t=0, t=10) are inside a
    # 60 s refractory window of each other -- only one of that close pair should survive alongside
    # the temporally separate third.
    sample_times = [0.0, 10.0, 200.0]
    pro_times = [5.0]
    pro_values = [8.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=10.0, direction="nearest",
                                   max_per_rating=2, refractory_min=1.0)
    matched = [i for i in range(3) if not np.isnan(out["matched_value"][i])]
    assert len(matched) == 2
    assert 0 in matched  # closest to the report (|5-0|=5) always kept
    assert 10.0 not in [sample_times[i] for i in matched] or 200.0 in [sample_times[i] for i in matched]
    # exactly one of {10.0, 200.0} survives, and the refractory gap prevents 10.0 (too close to 0.0)
    assert 1 not in matched
    assert 2 in matched


def test_refractory_cap_is_scoped_per_group_not_globally():
    # Two groups, each with its own burst around the same report -- the cap must apply
    # independently within each group, not globally across both.
    sample_times = [0.0, 5.0, 0.0, 5.0]
    groups = ["A", "A", "B", "B"]
    pro_times = [2.5]
    pro_values = [6.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=10.0, direction="nearest",
                                   group_keys=groups, max_per_rating=1, refractory_min=0.0)
    matched = [i for i in range(4) if not np.isnan(out["matched_value"][i])]
    assert len(matched) == 2   # one survivor per group
    assert (0 in matched) != (1 in matched)  # exactly one of A's two candidates
    assert (2 in matched) != (3 in matched)  # exactly one of B's two candidates


def test_max_per_rating_none_reproduces_the_uncapped_behavior_of_the_two_gap_matchers():
    # decision 73's own finding: two of the four existing matchers have no independence rule at
    # all. A caller migrating one of them can reproduce that exact behavior during the port by
    # passing max_per_rating=None -- confirmed here: every sample within tolerance matches, with
    # no cap applied even when several share one report.
    sample_times = [0.0, 1.0, 2.0]
    pro_times = [1.0]
    pro_values = [9.0]
    out = matching.matched_samples(sample_times, sample_times, pro_times, pro_values,
                                   tolerance_min=1.0, direction="nearest", max_per_rating=None)
    assert np.isnan(out["matched_value"]).sum() == 0


def test_no_reports_or_no_tolerance_matches_nothing_and_does_not_raise():
    out = matching.matched_samples([0.0, 1.0], [0.0, 1.0], [], [], tolerance_min=1.0)
    assert np.isnan(out["matched_value"]).all()
    out2 = matching.matched_samples([0.0], [0.0], [0.0], [1.0], tolerance_min=None)
    assert np.isnan(out2["matched_value"]).all()
    out3 = matching.matched_samples([0.0], [0.0], [0.0], [1.0], tolerance_min=0.0)
    assert np.isnan(out3["matched_value"]).all()


def test_rating_cluster_id_points_back_to_the_callers_original_pro_ordering():
    # Reports passed out of time order -- the returned id must still name the caller's own index,
    # not the internal sorted position.
    pro_times = [100.0, 0.0]     # report 1 (value 9.0) is EARLIER than report 0 (value 3.0)
    pro_values = [3.0, 9.0]
    out = matching.matched_samples([0.0], [0.0], pro_times, pro_values, tolerance_min=100.0,
                                   direction="nearest")
    assert out["rating_cluster_id"][0] == 1
    assert out["matched_value"][0] == 9.0
