"""Tests for the ordinal Gaussian-process safety model.

The tests are organised around the claims the model makes rather than around its methods,
because the claims are what a reviewer will challenge. Several of them exist specifically to
pin behaviour that a plausible-looking refactor would break silently: that an unvisited region
is reported as unknown and not as safe, that an uncoded severity label is never read as
"none", and that no monotone relationship between amplitude and severity is imposed anywhere.

Every test that fits a model uses synthetic data with a known answer. The real RCS08 record is
analysed in BOTORCH_REFACTOR.md, not here; a unit test that depends on a data file is a test
that fails for the wrong reason.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import safety_ordinal as so

torch_missing = not so.ordinal_torch_available()
needs_torch = pytest.mark.skipif(torch_missing, reason="torch/gpytorch not installed")


# --- label handling, which needs no torch ---------------------------------------------------
def test_encode_severity_maps_the_ordered_scale_to_ascending_integers():
    y = so.encode_severity(["none", "mild", "moderate", "severe"])
    assert y.tolist() == [0, 1, 2, 3]


def test_encode_severity_marks_every_flavour_of_missing_as_minus_one_not_as_none():
    """A step nobody could code must never enter the model as evidence of no side effect."""
    y = so.encode_severity([None, float("nan"), "", "unknown", "NONE", " Mild "])
    assert y[:4].tolist() == [-1, -1, -1, -1]
    # the last two show that recognised labels are still matched case- and space-insensitively
    assert y[4] == 0 and y[5] == 1


def _toy_frame():
    """A small acute-step table exercising every branch of prepare_coded_steps."""
    return pd.DataFrame({
        "rate_hz": [100.0, 100.0, 130.0, 130.0, 100.0, 100.0, 100.0, 100.0],
        "amp_L": [1.0, 2.0, 3.0, 3.0, 0.0, 2.0, 2.0, np.nan],
        "pw_L": [60.0, 60.0, 60.0, 60.0, 60.0, 60.0, 60.0, 60.0],
        "se_severity": ["none", "mild", "moderate", None, "moderate", "none", "none", "none"],
        "coded": [True, True, True, False, True, None, True, True],
        "procedural": [False, False, False, False, False, False, True, False],
    })


def test_prepare_drops_uncoded_procedural_and_incomplete_rows_and_says_so():
    out = so.prepare_coded_steps(_toy_frame())
    a = out["audit"]
    assert a["n_input_rows"] == 8
    assert a["n_procedural_dropped"] == 1
    assert a["n_severity_unknown_dropped"] == 1
    assert a["n_incomplete_features_dropped"] == 1
    assert a["n_amplitude_zero"] == 1
    # what survives: rows 0, 1, 2, 5 -- stim on, non-procedural, coded, complete
    assert a["n_fitted"] == 4
    assert out["X"].shape == (4, 3)
    assert len(out["y"]) == 4


def test_prepare_never_turns_a_missing_severity_into_none():
    out = so.prepare_coded_steps(_toy_frame())
    # the toy frame has exactly one "none", one "mild" and one "moderate" among survivors, plus
    # the never-coded row which the file already labels "none"
    assert out["audit"]["label_counts"]["none"] == 2
    assert out["audit"]["label_counts"]["mild"] == 1
    assert out["audit"]["label_counts"]["moderate"] == 1
    assert out["audit"]["label_counts"]["severe"] == 0
    # and the row whose severity was None is simply absent, not present as a zero
    assert len(out["y"]) == 4


def test_prepare_separates_never_coded_rows_from_explicitly_coded_ones():
    """The distinction that turns out to matter on the real record: an absent note is not a
    recorded observation of no side effect."""
    out = so.prepare_coded_steps(_toy_frame())
    assert out["audit"]["n_never_presented_to_coder"] == 1
    assert out["audit"]["n_none_from_never_coded"] == 1
    strict = so.prepare_coded_steps(_toy_frame(), explicit_only=True)
    assert strict["audit"]["n_fitted"] < out["audit"]["n_fitted"]


def test_prepare_reports_the_adverse_rate_at_zero_amplitude_separately():
    """Zero-amplitude steps are excluded from the fit but their adverse rate is the comparison
    that says whether adverse events are attributable to stimulation at all."""
    a = so.prepare_coded_steps(_toy_frame())["audit"]
    assert a["n_amplitude_zero"] == 1
    assert a["adverse_rate_at_zero_amplitude"] == 1.0


# --- the model ------------------------------------------------------------------------------
def _rate_driven_data(n=240, seed=0):
    """Severity that depends on RATE and not at all on amplitude.

    This is the shape of the real record, so a model that cannot recover it here cannot be
    trusted on the real record either. Amplitude is spread over the full clinical range and is
    independent of the outcome by construction.
    """
    rng = np.random.default_rng(seed)
    rate = rng.choice([60.0, 90.0, 130.0, 160.0], size=n)
    amp = rng.uniform(0.5, 3.5, size=n)
    pw = np.full(n, 60.0)
    p_adverse = np.where(rate >= 130.0, 0.45, 0.02)
    y = np.where(rng.random(n) < p_adverse, 2, 0)
    return np.column_stack([rate, amp, pw]), y


@pytest.fixture(scope="module")
def rate_model():
    if torch_missing:
        pytest.skip("torch/gpytorch not installed")
    X, y = _rate_driven_data()
    return so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(X, y, n_iter=400), X, y


@needs_torch
def test_cutpoints_are_ascending_with_the_first_pinned_at_zero(rate_model):
    """The identifiability convention taken from aepsych/likelihoods/ordinal.py."""
    m, _, _ = rate_model
    c = m.cutpoints
    assert c.shape == (len(so.SEVERITY_LEVELS) - 1,)
    assert c[0] == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.diff(c) > 0)


@needs_torch
def test_category_probabilities_are_a_proper_distribution(rate_model):
    m, X, _ = rate_model
    P = m.predict_proba(X[:40])
    assert P.shape == (40, len(so.SEVERITY_LEVELS))
    assert np.all(P >= 0)
    assert np.allclose(P.sum(axis=1), 1.0, atol=1e-9)


@needs_torch
def test_the_model_recovers_a_rate_effect_without_being_told_to_look_for_one(rate_model):
    m, _, _ = rate_model
    low = m.p_at_least([[60.0, 2.0, 60.0]])["mean"][0]
    high = m.p_at_least([[130.0, 2.0, 60.0]])["mean"][0]
    assert high > low + 0.15, (low, high)


@needs_torch
def test_no_monotone_amplitude_relationship_is_imposed(rate_model):
    """The central scientific requirement. With severity independent of amplitude in the data,
    the fitted probability must stay flat in amplitude rather than rising, which is what the
    monotone polynomial prior mean of the scikit-learn SafetyGP would force it to do."""
    m, _, _ = rate_model
    amps = np.arange(0.6, 3.5, 0.2)
    p = m.p_at_least(np.column_stack([np.full(len(amps), 90.0), amps,
                                      np.full(len(amps), 60.0)]))["mean"]
    assert p.max() - p.min() < 0.10, p.tolist()
    # and specifically: the surface is not forced upward
    assert not np.all(np.diff(p) >= -1e-12), "the fit came out monotone non-decreasing"


@pytest.fixture(scope="module")
def rare_event_model():
    """A model fitted where adverse events are RARE, which is the real situation.

    This fixture is separate from ``rate_model`` because the unknown-is-not-safe behaviour can
    only be tested honestly when the overall base rate sits below the tolerance. With a high
    base rate an unvisited cell is flagged by the probability alone and the evidence
    requirement is never exercised, which would make the test pass for the wrong reason. In the
    RCS08 record the observed rate of moderate-or-worse events is under 5 percent, so 3 percent
    here is the realistic setting.
    """
    if torch_missing:
        pytest.skip("torch/gpytorch not installed")
    rng = np.random.default_rng(3)
    n = 300
    rate = rng.choice([60.0, 90.0, 130.0], size=n)
    amp = rng.uniform(0.5, 3.0, size=n)
    pw = np.full(n, 60.0)
    y = np.where(rng.random(n) < 0.03, 2, 0)
    X = np.column_stack([rate, amp, pw])
    return so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(X, y, n_iter=400), X, y


@needs_torch
def test_a_region_with_no_data_is_unknown_and_never_safe(rare_event_model):
    """The behaviour the whole module exists for.

    Far from any observation the latent posterior reverts to the fitted constant, which
    corresponds to the low overall base rate, so a reading of the mean probability alone would
    call the region safe. The evidence requirement is what stops it, and this test pins that by
    checking the same cells under both settings of that requirement.
    """
    m, X, _ = rare_event_model
    far = np.array([[60.0, 4.8, 250.0], [130.0, 4.9, 20.0]])
    near = np.array([[60.0, 1.5, 60.0], [90.0, 2.0, 60.0]])
    c_far, c_near = m.classify(far), m.classify(near)

    assert list(c_far["label"]) == ["unknown", "unknown"], c_far

    # The mean probability carries almost no signal about which of these is which. It is within
    # a factor of three of the value at well-sampled cells, so a reading of the mean alone would
    # not distinguish an unvisited corner of the space from a setting delivered many times.
    assert c_far["p_mean"].max() < 3.0 * c_near["p_mean"].max(), (
        c_far["p_mean"], c_near["p_mean"])

    # Two things do carry the signal, and both are required. First the credible interval, which
    # is far wider outside the data and reaches well above the tolerance.
    assert np.all(c_far["p_upper"] > so.DEFAULT_P_ADVERSE_MAX), c_far["p_upper"]
    assert c_far["ci_width"].min() > c_near["ci_width"].max(), (
        c_far["ci_width"], c_near["ci_width"])
    assert c_far["latent_sd"].min() > c_near["latent_sd"].max(), (
        c_far["latent_sd"], c_near["latent_sd"])
    assert np.all(c_far["latent_sd"] > 0.9), c_far["latent_sd"]

    # Second the evidence requirement, isolated here by raising the probability tolerance high
    # enough that the interval condition is satisfied at these cells. With the requirement
    # switched off they would be called safe; with it on they stay unknown.
    assert np.all(c_far["n_eff"] < so.DEFAULT_MIN_EVIDENCE), c_far["n_eff"]
    lax = m.classify(far, p_max=0.6, min_evidence=0.0)
    gated = m.classify(far, p_max=0.6, min_evidence=so.DEFAULT_MIN_EVIDENCE)
    assert list(lax["label"]) == ["safe", "safe"], lax["label"].tolist()
    assert list(gated["label"]) == ["unknown", "unknown"], gated["label"].tolist()


@needs_torch
def test_uncertainty_is_larger_where_there_are_fewer_observations(rate_model):
    m, X, _ = rate_model
    inside = m.p_at_least(np.column_stack([np.full(9, 90.0), np.linspace(1.0, 3.0, 9),
                                           np.full(9, 60.0)]))
    outside = m.p_at_least(np.column_stack([np.full(9, 90.0), np.linspace(4.2, 4.9, 9),
                                            np.full(9, 60.0)]))
    assert np.median(outside["latent_sd"]) > np.median(inside["latent_sd"])
    assert np.median(outside["width"]) > np.median(inside["width"])


@needs_torch
def test_evidence_is_on_the_scale_of_a_count_of_observations(rate_model):
    """n_eff is the summed kernel correlation, and the kernel has no output scale, so a point
    sitting on the training data returns something of the order of the number of nearby steps
    and a point far away returns approximately zero."""
    m, X, _ = rate_model
    on_data = m.evidence(X[:5])
    far = m.evidence([[60.0, 4.9, 250.0]])
    assert np.all(on_data > 1.0)
    assert far[0] < 1.0
    assert np.all(m.evidence(X) <= len(X) + 1e-6)


@needs_torch
def test_credible_interval_brackets_the_mean_and_widens_with_credible_mass(rate_model):
    m, X, _ = rate_model
    q = X[:25]
    narrow = m.p_at_least(q, credible_mass=0.50)
    wide = m.p_at_least(q, credible_mass=0.95)
    assert np.all(narrow["lower"] <= narrow["upper"])
    assert np.all(wide["width"] >= narrow["width"] - 1e-12)
    assert np.all((narrow["mean"] >= 0.0) & (narrow["mean"] <= 1.0))


@needs_torch
def test_a_confidently_dangerous_region_is_labelled_elevated_not_unknown(rate_model):
    m, _, _ = rate_model
    c = m.classify([[130.0, 2.0, 60.0], [160.0, 2.0, 60.0]])
    assert set(c["label"]) == {"elevated"}, c["label"].tolist()


@needs_torch
def test_classify_requires_both_conditions_before_calling_a_cell_safe(rate_model):
    """Raising the evidence bar can only ever move cells out of the safe set, never into it."""
    m, X, _ = rate_model
    grid = np.column_stack([np.full(30, 60.0), np.linspace(0.6, 3.4, 30), np.full(30, 60.0)])
    lax = m.classify(grid, min_evidence=0.0)
    strict = m.classify(grid, min_evidence=25.0)
    lax_safe = lax["label"] == "safe"
    strict_safe = strict["label"] == "safe"
    assert strict_safe.sum() <= lax_safe.sum()
    assert np.all(strict_safe <= lax_safe)


@needs_torch
def test_fit_refuses_an_unlabelled_row_rather_than_treating_it_as_none():
    X, y = _rate_driven_data(n=40)
    y = y.copy()
    y[0] = -1
    with pytest.raises(ValueError, match="must be dropped, not recoded"):
        so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(X, y, n_iter=5)


@needs_torch
def test_fit_refuses_a_rank_outside_the_declared_scale():
    X, y = _rate_driven_data(n=40)
    y = y.copy()
    y[0] = 9
    with pytest.raises(ValueError, match="exceeds n_levels"):
        so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(X, y, n_iter=5)


@needs_torch
def test_a_non_positive_value_on_a_log_axis_is_refused():
    X, y = _rate_driven_data(n=40)
    X = X.copy()
    X[0, 0] = 0.0
    with pytest.raises(ValueError, match="log2 axis"):
        so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L")).fit(X, y, n_iter=5)


@needs_torch
def test_predicting_before_fitting_raises_rather_than_returning_something_plausible():
    m = so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L"))
    with pytest.raises(RuntimeError, match="not fitted"):
        m.predict_latent([[100.0, 1.0, 60.0]])


@needs_torch
def test_fitting_is_reproducible_for_a_given_seed():
    X, y = _rate_driven_data(n=120)
    q = np.array([[90.0, 2.0, 60.0], [130.0, 2.0, 60.0]])
    a = so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L"), random_state=7).fit(X, y, n_iter=150)
    b = so.OrdinalSeverityGP(("rate_hz", "amp_L", "pw_L"), random_state=7).fit(X, y, n_iter=150)
    assert np.allclose(a.p_at_least(q)["mean"], b.p_at_least(q)["mean"])


@needs_torch
def test_p_at_least_rejects_a_level_outside_the_scale(rate_model):
    m, _, _ = rate_model
    with pytest.raises(ValueError, match="level must be between"):
        m.p_at_least([[100.0, 1.0, 60.0]], level=0)


# --- safe-set bookkeeping, which needs no torch ---------------------------------------------
def _amp_grid():
    amps = np.arange(0.5, 3.1, 0.5)
    return np.array([[f, a, 60.0] for f in (60.0, 130.0) for a in amps], float)


def test_recomputed_set_follows_the_latest_classification():
    G = _amp_grid()
    t = so.SafeSetTracker(mode="recomputed")
    lab = np.where(G[:, 1] <= 2.0, "safe", "unknown")
    assert t.update(lab).sum() == int((G[:, 1] <= 2.0).sum())
    lab2 = np.where(G[:, 1] <= 1.0, "safe", "unknown")
    assert t.update(lab2).sum() == int((G[:, 1] <= 1.0).sum())


def test_cumulative_set_never_shrinks_which_is_its_whole_point_and_its_whole_risk():
    """The SAFE-OPT update rule from safe_opt_update_ND.m. A cell that has ever qualified stays
    in, so the set is stable across iterations but an admission can never be withdrawn."""
    G = _amp_grid()
    t = so.SafeSetTracker(mode="cumulative")
    n_eff = np.full(len(G), 10.0)
    first = t.update(np.where(G[:, 1] <= 2.0, "safe", "unknown"), n_eff)
    second = t.update(np.where(G[:, 1] <= 1.0, "safe", "unknown"), n_eff)
    assert second.sum() == first.sum()
    assert np.all(second >= first)


def test_cumulative_admission_is_gated_on_evidence_not_on_probability_alone():
    G = _amp_grid()
    t = so.SafeSetTracker(mode="cumulative")
    lab = np.full(len(G), "safe")
    thin = np.full(len(G), 0.5)
    assert t.update(lab, thin, min_evidence=3.0).sum() == 0


def test_cumulative_mode_refuses_to_run_without_evidence_counts():
    t = so.SafeSetTracker(mode="cumulative")
    with pytest.raises(ValueError, match="gated on evidence"):
        t.update(np.array(["safe", "safe"]))


def test_an_unknown_mode_is_rejected_at_construction():
    with pytest.raises(ValueError, match="recomputed"):
        so.SafeSetTracker(mode="optimistic")


def test_contiguity_violations_finds_a_gap_a_clinician_could_not_ramp_through():
    G = _amp_grid()
    mask = (G[:, 1] <= 1.0) | (G[:, 1] >= 2.5)
    bad = so.SafeSetTracker.contiguity_violations(mask, G)
    assert len(bad) == 2                       # one per frequency
    for entry in bad:
        assert 1.5 in entry["unsafe_amplitudes_below_a_safe_one"]
        assert entry["highest_safe_amplitude"] == 3.0


def test_a_lower_interval_mask_has_no_contiguity_violations():
    G = _amp_grid()
    assert so.SafeSetTracker.contiguity_violations(G[:, 1] <= 2.0, G) == []


def test_lower_interval_projection_removes_only_unreachable_cells():
    G = _amp_grid()
    mask = (G[:, 1] <= 1.0) | (G[:, 1] >= 2.5)
    proj = so.SafeSetTracker.lower_interval(mask, G)
    assert np.all(proj <= mask), "the projection must never add a cell"
    assert so.SafeSetTracker.contiguity_violations(proj, G) == []
    assert proj.sum() == int((G[:, 1] <= 1.0).sum())


def test_lower_interval_leaves_an_already_contiguous_mask_alone():
    G = _amp_grid()
    mask = G[:, 1] <= 2.0
    assert np.array_equal(so.SafeSetTracker.lower_interval(mask, G), mask)


@needs_torch
def test_the_two_update_rules_agree_when_the_model_never_changes(rate_model):
    """A degenerate case worth pinning: with one fitted model classifying the same grid twice,
    nothing can be withdrawn, so cumulative and recomputed must coincide. A disagreement here
    would mean the evidence gate is doing something other than what it claims."""
    m, _, _ = rate_model
    G = _amp_grid()
    out = so.compare_safe_set_rules(m, [G, G, G])
    assert out["n_only_in_cumulative"] == 0
    assert out["n_recomputed_final"] == out["n_cumulative_final"]
