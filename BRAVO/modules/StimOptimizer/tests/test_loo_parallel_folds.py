"""The calibration check's held-out folds refitted side by side in worker processes (the PI,
2026-09-25: "there's no reason it should take five minutes ... vectorize it!").

Each fold of `ObjectiveGP.loo_predict` refits the pain map from scratch on its training rows, its
hyperparameters re-estimated from twelve random restarts seeded the same way every time, so a fold
is a pure function of its rows. Running the folds in separate processes changes WHERE each is
computed, never what: pinned here bit for bit (np.array_equal, never a tolerance), for single-epoch
folds and for blocks of time, on a three-input and a five-input map, and whichever way the
linear-algebra thread pool of the calling process is set.
"""
import numpy as np
import pytest

from StimOptimizer.routines import surrogate as SUR


def _gp3(n=14, seed=3):
    rng = np.random.default_rng(seed)
    grid = SUR.JointParameterGrid([55.0], np.arange(0.0, 5.01, 0.5), np.arange(0.0, 5.01, 0.5))
    X = np.column_stack([np.full(n, 55.0), rng.choice(grid.amps_left, n), rng.choice(grid.amps_right, n)])
    y = 5.0 - 0.4 * X[:, 1] + 0.2 * X[:, 2] + 0.5 * rng.standard_normal(n)
    v = np.full(n, 0.3) + 0.1 * rng.random(n)
    return SUR.ObjectiveGP(grid, fixed_length_scale=(0.823, None, None), random_state=0).fit(X, y, v)


def _gp5(n=16, seed=5):
    rng = np.random.default_rng(seed)
    amps = np.arange(0.0, 5.01, 0.5)
    grid = SUR.PooledPulseWidthGrid(55.0, amps, amps, pw_left_levels=[60.0, 100.0],
                                    pw_right_levels=[150.0, 160.0], pw_left_at=100.0, pw_right_at=150.0)
    X = np.column_stack([np.full(n, 55.0), rng.choice(amps, n), rng.choice(amps, n),
                         rng.choice([60.0, 100.0], n), rng.choice([150.0, 160.0], n)])
    y = 4.0 - 0.3 * X[:, 1] + 0.01 * X[:, 3] + 0.5 * rng.standard_normal(n)
    v = np.full(n, 0.25) + 0.1 * rng.random(n)
    return SUR.ObjectiveGP(grid, fixed_length_scale=(0.823, None, None, None, None),
                           random_state=0).fit(X, y, v)


@pytest.mark.parametrize("make", [_gp3, _gp5], ids=["three inputs", "five inputs"])
@pytest.mark.parametrize("fold", ["one epoch", "blocks of time"])
def test_folds_in_worker_processes_give_the_serial_answer_bit_for_bit(make, fold):
    gp = make()
    n = len(gp.y_)
    groups = None if fold == "one epoch" else np.repeat([0, 1, 2], int(np.ceil(n / 3)))[:n]
    mu1, sd1 = gp.loo_predict(groups=groups, n_jobs=1)
    mu2, sd2 = gp.loo_predict(groups=groups, n_jobs=2)
    assert np.array_equal(mu1, mu2, equal_nan=True)
    assert np.array_equal(sd1, sd2, equal_nan=True)
    assert np.isfinite(mu1).sum() == n


def test_the_default_gives_the_serial_answer_and_skips_folds_too_small_to_train_on():
    gp = _gp3(n=6)
    groups = np.array([0, 0, 0, 0, 1, 1])      # holding out group 0 leaves 2 rows: skipped, NaN
    mu1, sd1 = gp.loo_predict(groups=groups, n_jobs=1)
    mu, sd = gp.loo_predict(groups=groups)
    assert np.array_equal(mu, mu1, equal_nan=True) and np.array_equal(sd, sd1, equal_nan=True)
    assert np.isnan(mu[:4]).all() and np.isfinite(mu[4:]).all()


def test_the_answer_does_not_depend_on_the_calling_process_thread_pool():
    threadpoolctl = pytest.importorskip("threadpoolctl")
    gp = _gp5()
    ref = gp.loo_predict(n_jobs=1)
    with threadpoolctl.threadpool_limits(limits=1, user_api="blas"):
        capped = gp.loo_predict(n_jobs=2)
    for a, b in zip(ref, capped):
        assert np.array_equal(a, b, equal_nan=True)


def test_worker_count_setting(monkeypatch):
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "1")
    assert SUR._loo_n_jobs() == 1
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "0")
    assert SUR._loo_n_jobs() == 1
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "4")
    assert SUR._loo_n_jobs() == 4
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "not a number")
    assert SUR._loo_n_jobs() == SUR.LOO_DEFAULT_JOBS
    monkeypatch.delenv(SUR.LOO_JOBS_ENV)
    assert SUR._loo_n_jobs() == SUR.LOO_DEFAULT_JOBS >= 1


def test_with_the_setting_at_one_no_worker_process_is_asked_for(monkeypatch):
    """"1" is the before-this-change path: the folds refitted in the calling process."""
    import joblib
    monkeypatch.setenv(SUR.LOO_JOBS_ENV, "1")
    asked = []                        # recorded, not raised: a raise would be caught by the fallback
    monkeypatch.setattr(joblib, "Parallel", lambda *a, **k: asked.append(1))
    mu, sd = _gp3().loo_predict()
    assert asked == [] and np.isfinite(mu).all()


@pytest.mark.parametrize("n_jobs", [1, 2])
def test_several_fold_structures_in_one_dispatch_equal_each_asked_alone(n_jobs):
    """The calibration check asks for its two folds (one epoch at a time; blocks of time) in one
    dispatch; each structure's answer is the one `loo_predict` gives it alone, bit for bit."""
    gp = _gp5()
    n = len(gp.y_)
    blocks = np.repeat([0, 1, 2], int(np.ceil(n / 3)))[:n]
    many = gp.loo_predict_many([None, blocks], n_jobs=n_jobs)
    for got, groups in zip(many, (None, blocks)):
        alone = gp.loo_predict(groups=groups, n_jobs=1)
        assert np.array_equal(got[0], alone[0], equal_nan=True)
        assert np.array_equal(got[1], alone[1], equal_nan=True)


def test_the_check_asks_for_both_folds_in_one_dispatch_and_reports_what_it_did_before():
    """`stratum_calibration` on a real surface: one call to `loo_predict_many` carrying both fold
    structures, and the same numbers as the check computed from `loo_predict`, fold by fold."""
    import pandas as pd
    from StimOptimizer import stage1_openloop as S1
    gp = _gp3(n=15)
    sub = pd.DataFrame({"t0": pd.date_range("2026-01-01", periods=15, freq="5D", tz="UTC"),
                        "amp_mA_Left": gp.X_[:, 1], "amp_mA_Right": gp.X_[:, 2],
                        "J": gp.y_, "obs_var": gp.y_var_, "n": 5.0})
    calls = []
    real = type(gp).loo_predict_many
    def _spy(self, groupings, n_jobs=None):
        calls.append(len(groupings))
        return real(self, groupings, n_jobs=n_jobs)
    type(gp).loo_predict_many = _spy
    try:
        got = S1.stratum_calibration(gp, sub)
    finally:
        type(gp).loo_predict_many = real

    class _OnlyLoo:                          # the same surface, asked fold by fold, serially
        y_, y_var_ = gp.y_, gp.y_var_
        def loo_predict(self, groups=None):
            return gp.loo_predict(groups=groups, n_jobs=1)
    ref = S1.stratum_calibration(_OnlyLoo(), sub)
    assert calls == [2]
    assert got == ref
