"""Regression tests for the StimOptimizer core. Run with `pytest BRAVO/modules/StimOptimizer`.

Each test pins a behaviour that a real defect already violated during development, so these are
regressions in the literal sense rather than coverage decoration.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines.preference import PreferenceGP
from StimOptimizer.routines.surrogate import ObjectiveGP, ParameterGrid, SafetyGP

FREQS = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165]
AMPS = np.round(np.arange(0.8, 4.01, 0.1), 2)


@pytest.fixture
def grid():
    return ParameterGrid(FREQS, AMPS)


@pytest.fixture
def epochs():
    """Six synthetic epochs spanning the heteroscedastic extremes of the real warm start."""
    return pd.DataFrame({
        "epoch": [1, 2, 3, 4, 5, 6],
        "freq_hz": [55.0, 55.0, 10.0, 110.0, 130.0, 55.0],
        "amp_mA_Left": [1.6, 1.8, 1.6, 4.0, 2.9, 1.4],
        "amp_mA_Right": [1.2, 1.2, 1.2, 3.0, 3.1, 1.2],
        "pw_us_Left": [60.0] * 6,
        "n": [155, 5, 26, 63, 34, 1],
        "t0": pd.to_datetime(["2026-03-04", "2026-06-11", "2026-01-05",
                              "2025-09-14", "2025-07-17", "2026-02-06"], utc=True),
        "dur_h": [2035.0, 160.0, 358.0, 646.0, 308.0, 40.0],
        "nrs": [7.28, 6.60, 7.08, 7.81, 8.59, 8.00],
        "nrs_sd": [1.24, 0.55, 0.84, 0.76, 0.50, np.nan],
        # Left leg is the PI-designated primary site and the module default, so the fixture
        # carries it and the tests exercise the default path. Values are on the REAL chronic
        # scale: left_leg_vas is a 0-100 VAS, ten times the 0-10 nrs column above. After
        # build_objective rescales to the common 0-10 reference these reproduce the nrs numbers
        # exactly, which is what makes the two paths comparable.
        "left_leg_vas": [72.8, 66.0, 70.8, 78.1, 85.9, 80.0],
        "left_leg_vas_sd": [12.4, 5.5, 8.4, 7.6, 5.0, np.nan],
    })


# --- objective -------------------------------------------------------------------------
def test_J_is_zero_at_the_incumbent(epochs):
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    assert d.loc[d.epoch == 1, "J"].iloc[0] == pytest.approx(0.0)
    # negative J means better than status quo, which is the whole sign convention
    assert d.loc[d.epoch == 2, "J"].iloc[0] < 0


def test_observation_variance_orders_by_evidence(epochs):
    """A 155-report/85-day epoch must be trusted far more than a 1-report/40-hour epoch."""
    d = OBJ.build_objective(epochs, incumbent_epoch=1).set_index("epoch")
    assert d.loc[1, "obs_var"] < d.loc[2, "obs_var"] < d.loc[6, "obs_var"]
    assert d.loc[6, "obs_var"] / d.loc[1, "obs_var"] > 10


def test_single_report_epoch_is_kept_not_dropped(epochs):
    """The spec forbids discarding thin epochs; SD must be imputed from the pooled variance."""
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    assert len(d) == len(epochs)
    assert np.isfinite(d.loc[d.epoch == 6, "obs_var"].iloc[0])


def test_se_ladder_calibration_and_unreported_flag(epochs):
    assert OBJ.side_effect_penalty("mild") == 1.0        # cancels exactly 1.0 NRS point
    assert OBJ.side_effect_penalty(None) == 0.0
    with pytest.raises(ValueError):
        OBJ.side_effect_penalty("a bit")
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    assert not d["se_observed"].any()  # absence of a report is not absence of a side effect
    assert d["feasible"].all()


def test_moderate_and_severe_are_hard_infeasible(epochs):
    """A finite penalty would be beaten by a large enough pain benefit; +inf cannot be."""
    e = epochs.copy()
    e["se_severity"] = ["none", "moderate", "none", "severe", "mild", "none"]
    # epoch 2 and 4 get a huge apparent benefit; they must still be rejected
    e.loc[e.epoch.isin([2, 4]), "nrs"] = 1.0
    d = OBJ.build_objective(e, incumbent_epoch=1).set_index("epoch")
    assert np.isinf(d.loc[2, "J"]) and np.isinf(d.loc[4, "J"])
    assert not d.loc[2, "feasible"] and not d.loc[4, "feasible"]
    assert d.loc[5, "feasible"]                      # mild stays a finite trade-off
    assert d.loc[5, "J"] == pytest.approx(d.loc[5, "J_pain"] + 1.0)
    assert d["se_observed"].all()


def test_objective_gp_refuses_infeasible_rows(epochs, grid):
    e = epochs.copy()
    e["se_severity"] = ["none", "moderate", "none", "none", "none", "none"]
    d = OBJ.build_objective(e, incumbent_epoch=1)
    X = d[["freq_hz", "amp_mA_Left"]].to_numpy(float)
    with pytest.raises(ValueError, match="hard-infeasible"):
        ObjectiveGP(grid).fit(X, d["J"].to_numpy(float), d["obs_var"].to_numpy(float))
    ok = d[d["feasible"]]
    ObjectiveGP(grid, fixed_length_scale=[0.823, 0.72]).fit(
        ok[["freq_hz", "amp_mA_Left"]].to_numpy(float),
        ok["J"].to_numpy(float), ok["obs_var"].to_numpy(float))


def test_incumbent_must_exist(epochs):
    with pytest.raises(ValueError):
        OBJ.build_objective(epochs, incumbent_epoch=999)


# --- grid ------------------------------------------------------------------------------
def test_grid_snap_and_index_roundtrip(grid):
    X = np.array([[57.0, 1.63], [10.4, 3.98]])
    snapped = grid.snap(X)
    assert snapped[0].tolist() == [55.0, 1.6]
    idx = grid.index_of(X)
    assert np.allclose(grid.grid_X()[idx], snapped)


def test_nonpositive_frequency_rejected(grid):
    with pytest.raises(ValueError):
        grid.transform(np.array([[0.0, 1.6]]))


# --- objective GP ----------------------------------------------------------------------
def test_objective_gp_respects_observation_weights(epochs, grid):
    """The high-evidence incumbent must be fit more closely than the 1-report epoch."""
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    X = d[["freq_hz", "amp_mA_Left"]].to_numpy(float)
    gp = ObjectiveGP(grid, fixed_length_scale=[0.823, 0.72]).fit(
        X, d["J"].to_numpy(float), d["obs_var"].to_numpy(float))
    mu, sd = gp.predict(X)
    resid = np.abs(mu - d["J"].to_numpy(float))
    assert resid[0] < resid[5]
    assert np.all(sd > 0)


def test_objective_gp_rejects_bad_variance(epochs, grid):
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    X = d[["freq_hz", "amp_mA_Left"]].to_numpy(float)
    with pytest.raises(ValueError):
        ObjectiveGP(grid).fit(X, d["J"].to_numpy(float), np.zeros(len(d)))


# --- safety GP -------------------------------------------------------------------------
def test_limits_only_seeding_is_refused(grid):
    """Regression: seeding from limits alone empties the safe set for any beta > 0."""
    with pytest.raises(ValueError):
        SafetyGP.seed_from_history(np.empty((0, 2)), np.array([[55.0, 2.0]]))


def test_safe_set_shrinks_monotonically_in_beta(grid):
    deliv = np.array([[55.0, 1.6], [110.0, 4.0], [10.0, 1.6], [130.0, 2.9]])
    lims = np.array([[55.0, 2.0], [110.0, 4.0], [10.0, 1.9], [130.0, 3.2]])
    X, s, v = SafetyGP.seed_from_history(deliv, lims)
    sgp = SafetyGP(grid).fit(X, s, v)
    counts = [sgp.safe_mask(beta=b).sum() for b in (0.0, 1.0, 2.0, 3.0)]
    assert counts == sorted(counts, reverse=True)


def test_expansion_cap_bounds_the_step(grid):
    deliv = np.array([[55.0, 1.6], [110.0, 4.0], [10.0, 1.6]])
    lims = np.array([[55.0, 2.0], [110.0, 4.0], [10.0, 1.9]])
    X, s, v = SafetyGP.seed_from_history(deliv, lims)
    sgp = SafetyGP(grid).fit(X, s, v)
    capped = sgp.expansion_capped_mask(worst_severity="none", prev_max_amp=1.6, beta=2.0)
    assert sgp.max_safe_amplitude(mask=capped) <= 1.6 + 0.4 + 1e-9
    halted = sgp.expansion_capped_mask(worst_severity="moderate", prev_max_amp=1.6, beta=2.0)
    assert sgp.max_safe_amplitude(mask=halted) <= 1.6 + 1e-9
    with pytest.raises(ValueError):
        sgp.expansion_capped_mask(worst_severity="terrible", prev_max_amp=1.6)


def test_monotone_prior_mean_never_decreases(grid):
    """Severity must not be modelled as falling with amplitude, whatever the fit wants."""
    deliv = np.array([[55.0, 1.0], [55.0, 1.5], [55.0, 2.0]])
    lims = np.array([[55.0, 2.5], [55.0, 3.0]])
    X, s, v = SafetyGP.seed_from_history(deliv, lims)
    sgp = SafetyGP(grid).fit(X, s, v)
    a = np.linspace(0.8, 4.0, 64)
    assert np.all(np.diff(sgp.prior_(a)) >= -1e-9)


# --- preference GP ---------------------------------------------------------------------
def test_preference_recovers_a_known_ranking(grid):
    X = np.array([[55.0, 1.4], [55.0, 1.6], [55.0, 1.8], [110.0, 3.3]])
    truth = np.array([0.0, 1.0, 2.0, -1.0])          # higher = more preferred
    pairs = [(i, j) for i in range(4) for j in range(4) if truth[i] > truth[j]]
    pg = PreferenceGP(grid).fit(X, pairs)
    mu, sd = pg.predict(X)
    assert np.argmax(mu) == 2
    assert np.argmin(mu) == 3
    assert np.all(sd > 0)


def test_preference_rejects_ties_and_self_comparisons(grid):
    X = np.array([[55.0, 1.6], [55.0, 1.8]])
    with pytest.raises(ValueError):
        PreferenceGP(grid).fit(X, [(0, 0)])
    with pytest.raises(ValueError):
        PreferenceGP(grid).fit(X, [])


def test_prob_prefer_is_symmetric_and_bounded(grid):
    X = np.array([[55.0, 1.4], [55.0, 1.6], [55.0, 1.8]])
    pairs = [(2, 0), (2, 1), (1, 0)]
    pg = PreferenceGP(grid).fit(X, pairs)
    a, b = np.array([[55.0, 1.8]]), np.array([[55.0, 1.4]])
    p, q = pg.prob_prefer(a, b)[0], pg.prob_prefer(b, a)[0]
    assert p + q == pytest.approx(1.0, abs=1e-6)
    assert 0.5 < p < 1.0


# --- configurable pain metric (section 2.2) ----------------------------------------------
def test_default_metric_is_left_leg_not_overall():
    """PI direction: the left leg is the primary site. The Overall rating does not detect the
    on/off effect the site scores do, so defaulting to it would optimize the wrong quantity."""
    assert OBJ.DEFAULTS["primary_item"] == "left_leg"
    assert OBJ.DEFAULTS["metric"] == "left_leg"
    assert OBJ.PAIN_METRICS["left_leg"].items == {"left_leg": +1.0}


def test_head_is_excluded_with_a_reason():
    assert "head" in OBJ.EXCLUDED_ITEMS and OBJ.EXCLUDED_ITEMS["head"]


def test_metric_resolves_across_chronic_and_acute_column_names():
    chronic = pd.DataFrame({"left_leg_vas": [4.0, 6.0], "back_vas": [5.0, 7.0]})
    acute = pd.DataFrame({"pain_Left_Leg": [4.0, 6.0], "pain_Back": [5.0, 7.0]})
    assert OBJ.resolve_items(chronic, "left_leg") == {"left_leg_vas": 1.0}
    assert OBJ.resolve_items(acute, "left_leg") == {"pain_Left_Leg": 1.0}
    assert OBJ.resolve_items(acute, "back") == {"pain_Back": 1.0}


def test_single_item_metric_is_not_z_scored():
    """A single-item metric must stay on the NRS scale so J_pain is in NRS points."""
    df = pd.DataFrame({"pain_Left_Leg": [4.0, 6.0, 8.0]})
    assert list(OBJ.composite_z(df, metric="left_leg")) == [4.0, 6.0, 8.0]
    assert OBJ.PAIN_METRICS["left_leg"].standardize is False
    assert OBJ.PAIN_METRICS["legacy_composite"].standardize is True


def test_missing_metric_item_raises_rather_than_narrowing():
    """A silently-narrowed objective is a wrong objective that still runs."""
    with pytest.raises(KeyError, match="left_leg"):
        OBJ.resolve_items(pd.DataFrame({"pain_Back": [1.0]}), "left_leg")


def test_build_objective_refuses_a_frame_without_the_primary_item(epochs):
    with pytest.raises(KeyError, match="primary item"):
        OBJ.build_objective(epochs.drop(columns=["left_leg_vas", "left_leg_vas_sd"]),
                            incumbent_epoch=1)


def test_legacy_nrs_primary_item_still_works(epochs):
    d = OBJ.build_objective(epochs, incumbent_epoch=1, cfg={"primary_item": "nrs"})
    assert d.loc[d.epoch == 1, "J"].iloc[0] == pytest.approx(0.0)


def test_chronic_vas_and_acute_nrs_land_on_the_same_scale():
    """left_leg_vas is 0-100, pain_Left_Leg is 0-10. The same metric must not mean two things."""
    chronic = pd.DataFrame({"left_leg_vas": [0.0, 50.0, 100.0]})
    acute = pd.DataFrame({"pain_Left_Leg": [0.0, 5.0, 10.0]})
    assert list(OBJ.composite_z(chronic, metric="left_leg")) == [0.0, 5.0, 10.0]
    assert list(OBJ.composite_z(acute, metric="left_leg")) == [0.0, 5.0, 10.0]


def test_build_objective_rescales_a_0_100_primary_item(epochs):
    """A 0-100 VAS primary item must yield J_pain in NRS points, not VAS points, or the
    side-effect ladder (1 mild == 1.0 NRS point) is ten times too weak."""
    e = epochs.drop(columns=["left_leg_vas", "left_leg_vas_sd"]).copy()
    e["pain_Left_Leg"] = epochs["left_leg_vas"] / 10.0        # same pain, expressed 0-10
    e["pain_Left_Leg_sd"] = epochs["left_leg_vas_sd"] / 10.0
    d_vas = OBJ.build_objective(epochs, incumbent_epoch=1)    # 0-100 source
    d_nrs = OBJ.build_objective(e, incumbent_epoch=1)         # 0-10 source
    assert np.allclose(d_vas["J_pain"], d_nrs["J_pain"])
    assert abs(d_vas["J_pain"]).max() <= 10.0
    # and it agrees with the legacy nrs path, which is the same pain on the same scale
    d_legacy = OBJ.build_objective(epochs, incumbent_epoch=1, cfg={"primary_item": "nrs"})
    assert np.allclose(d_vas["J_pain"], d_legacy["J_pain"])


def test_scale_factor_defaults_to_identity_for_unknown_columns():
    assert OBJ.scale_factor("some_hand_built_column") == 1.0
    assert OBJ.scale_factor("left_leg_vas") == 0.1
    assert OBJ.scale_factor("pain_Left_Leg") == 1.0


def test_output_records_which_item_and_scale_were_used(epochs):
    """The rescale is in place, so a column named `left_leg_vas` ends up holding 0-10 values.
    The frame must say so, or a later reader will rescale it a second time."""
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    assert d["primary_item"].iloc[0] == "left_leg_vas"
    assert d["primary_scale_factor"].iloc[0] == pytest.approx(0.1)
    assert d["left_leg_vas"].max() <= 10.0
    d_nrs = OBJ.build_objective(epochs, incumbent_epoch=1, cfg={"primary_item": "nrs"})
    assert d_nrs["primary_scale_factor"].iloc[0] == pytest.approx(1.0)
