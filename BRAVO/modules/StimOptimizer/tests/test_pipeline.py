"""Regression tests for the arm runner and the hemisphere/incumbent parameterisation."""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import plots as PLT


def _matrix():
    """Minimal two-hemisphere design matrix with a clear most-recent epoch."""
    n = 14
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "epoch": np.arange(1, n + 1, dtype=float),
        "t0": pd.date_range("2026-01-01", periods=n, freq="7D", tz="UTC"),
        "freq_hz": np.tile([10.0, 55.0, 110.0, 165.0], 4)[:n],
        "amp_mA_Left": np.round(np.linspace(1.0, 2.5, n), 1),
        "amp_mA_Right": np.round(np.linspace(0.8, 2.0, n), 1),
        "pw_us_Left": np.full(n, 60.0),
        "n": np.full(n, 6.0),
        "dur_h": np.full(n, 120.0),
        "left_leg_vas": np.round(50 + 10 * rng.standard_normal(n), 1),
        "left_leg_vas_sd": np.full(n, 12.0),
    })


def test_incumbent_is_derived_from_the_most_recent_epoch():
    """A hardcoded incumbent went stale and inconsistent once; it must come from the data."""
    es = _matrix()
    ctx = PLT.build_context(es, data_horizon="test", washin_min=1.0, n_batches=1, q=2)
    last = es.sort_values("t0").iloc[-1]
    assert ctx.meta["incumbent_epoch"] == float(last["epoch"])
    assert ctx.meta["incumbent_xy"] == [float(last["freq_hz"]), float(last["amp_mA_Left"])]
    # and it must NOT be the stale pair the module used to hardcode
    assert ctx.meta["incumbent_xy"] != [55.0, 1.6]


def test_right_hemisphere_reads_its_own_amplitude_column():
    es = _matrix()
    left = PLT.build_context(es, hemisphere="Left", data_horizon="t", washin_min=1.0,
                            n_batches=1, q=2)
    right = PLT.build_context(es, hemisphere="Right", data_horizon="t", washin_min=1.0,
                             n_batches=1, q=2)
    assert left.meta["amp_col"] == "amp_mA_Left"
    assert right.meta["amp_col"] == "amp_mA_Right"
    # the incumbent amplitude must follow the hemisphere, not stay on the left
    last = es.sort_values("t0").iloc[-1]
    assert right.meta["incumbent_xy"][1] == float(last["amp_mA_Right"])
    assert left.meta["incumbent_xy"][1] == float(last["amp_mA_Left"])
    assert left.meta["incumbent_xy"][1] != right.meta["incumbent_xy"][1]


def test_unknown_hemisphere_is_refused():
    with pytest.raises(ValueError, match="hemisphere"):
        PLT.build_context(_matrix(), hemisphere="Both")


def test_missing_hemisphere_column_is_refused_not_silently_substituted():
    es = _matrix().drop(columns=["amp_mA_Right"])
    with pytest.raises(KeyError, match="amp_mA_Right"):
        PLT.build_context(es, hemisphere="Right")


def test_amp_grid_covers_the_delivered_escalation():
    """The old 0.8-4.0 grid could not represent the 4.8 mA settings actually delivered."""
    assert min(PLT.AMP_GRID) <= 0.0 and max(PLT.AMP_GRID) >= 4.8


def test_provenance_defaults_are_labelled_not_stale():
    assert "UNDECLARED" in PLT.DATA_HORIZON
    assert PLT.WASHIN_MIN == pytest.approx(1.0)
    assert PLT.INCUMBENT_EPOCH is None and PLT.INCUMBENT_XY is None


def test_pipeline_runs_both_hemispheres_and_flags_unresolved_optima():
    from StimOptimizer import pipeline
    rep = pipeline.run(_matrix(), sites=("left_leg",), hemispheres=("Left", "Right"),
                       outdir="/tmp/stimopt_test", render_figures=False,
                       data_horizon="test", washin_min=1.0, n_batches=1, q=2)
    # both arms must be ATTEMPTED; any that cannot fit is recorded, never silently dropped
    assert set(rep.arms) | set(rep.manifest["skipped"]) == {"left_leg__Left", "left_leg__Right"}
    assert rep.arms, f"no arm fitted; skips were {rep.manifest['skipped']}"
    for label, arm in rep.arms.items():
        assert arm.meta["amp_col"] == f"amp_mA_{arm.hemisphere}"
    assert rep.manifest["washin_min"] == 1.0
    assert set(rep.summary["arm"]) == set(rep.arms)


def test_pipeline_skips_an_arm_it_cannot_fit_rather_than_dying():
    from StimOptimizer import pipeline
    rep = pipeline.run(_matrix(), sites=("left_leg", "back"), hemispheres=("Left",),
                       outdir="/tmp/stimopt_test", render_figures=False,
                       data_horizon="test", washin_min=1.0, n_batches=1, q=2)
    assert "left_leg__Left" in rep.arms
    assert "back__Left" not in rep.arms          # no back_vas column in the fixture
    assert "back__Left" in rep.manifest["skipped"]


# --- the resolution gate: the single most consequential boolean in the module -------------------
def _arm(mu_star, sd_star, incumbent_mu, incumbent_sd):
    """Minimal ArmResult carrying only what the gate reads."""
    from StimOptimizer.pipeline import ArmResult
    meta = dict(mu_star=mu_star, sd_star=sd_star,
                incumbent_mu=incumbent_mu, incumbent_sd=incumbent_sd)
    return ArmResult(site="left_leg", hemisphere="Right", ctx=None, batch=None,
                     queue=None, stopping=None, meta=meta)


def test_gate_propagates_the_incumbent_sd_not_just_the_candidate():
    """Regression, 2026-08-30, with the numbers from the live RCS08 run (arm left_leg__Right).

    The old gate tested `mu_star + k*sd_star < incumbent_mu`, i.e. `gain > k*sd_star`, which clears
    the CANDIDATE's SD only. Gain 1.117 beats the candidate SD 0.989, so the old form reported the
    optimum as resolved. Propagating the incumbent's SD as well gives
    sd_diff = sqrt(0.989^2 + 0.923^2) = 1.353, which the gain does NOT clear.
    """
    import math
    arm = _arm(mu_star=-0.6881, sd_star=0.9894, incumbent_mu=0.4285, incumbent_sd=0.9227)
    gain = 0.4285 - (-0.6881)
    assert gain == pytest.approx(1.1166, abs=1e-3)
    assert gain > 0.9894                                   # old gate would have passed
    sd_diff = math.sqrt(0.9894 ** 2 + 0.9227 ** 2)
    assert sd_diff == pytest.approx(1.3527, abs=1e-3)
    assert gain < sd_diff                                  # difference is not resolved
    assert arm.surface_can_resolve_its_optimum() is False


def test_gate_is_conservative_relative_to_ignoring_the_incumbent_sd():
    """Adding a second variance can only widen the band, so the gate can withhold a recommendation
    it might have supported but can never manufacture one."""
    # gain 2.0 against sd_diff 0.707 — resolved under either form
    strict = _arm(mu_star=-2.0, sd_star=0.5, incumbent_mu=0.0, incumbent_sd=0.5)
    assert strict.surface_can_resolve_its_optimum() is True
    # The discriminating case is a gain that clears the candidate SD alone but NOT the propagated
    # difference SD: gain 0.60 > sd_star 0.50, yet sd_diff = sqrt(0.5^2+0.5^2) = 0.707 > 0.60.
    only_under_old_form = _arm(mu_star=-0.60, sd_star=0.5, incumbent_mu=0.0, incumbent_sd=0.5)
    assert 0.60 > 0.5                                             # old form would have passed
    assert only_under_old_form.surface_can_resolve_its_optimum() is False


def test_gate_returns_false_when_the_candidate_is_worse():
    worse = _arm(mu_star=0.5, sd_star=0.3, incumbent_mu=0.0, incumbent_sd=0.3)
    assert worse.surface_can_resolve_its_optimum() is False


def test_gate_missing_incumbent_sd_degrades_to_the_candidate_only():
    """A meta dict without incumbent_sd must not crash; it falls back to the candidate SD alone."""
    arm = _arm(mu_star=-2.0, sd_star=0.5, incumbent_mu=0.0, incumbent_sd=None)
    assert arm.surface_can_resolve_its_optimum() is True


def test_gate_rejects_a_degenerate_zero_variance():
    arm = _arm(mu_star=-1.0, sd_star=0.0, incumbent_mu=0.0, incumbent_sd=0.0)
    assert arm.surface_can_resolve_its_optimum() is False
