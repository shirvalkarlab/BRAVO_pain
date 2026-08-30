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
