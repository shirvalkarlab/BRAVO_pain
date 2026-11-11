"""Does the surface the current-map card draws predict a stretch it has not seen?

WHY THIS EXISTS. `OBJECTIVE_SPEC.md` §6 pre-registered three criteria for the surrogate -- it must
beat a precision-weighted mean of the training fold on held-out epochs, twice (leaving out one epoch
at a time, and leaving out a whole block of time at a time), and its intervals must cover what they
claim. `routines/validation.py` implements them and **nothing on the live path has ever run them**:
measured on 2026-09-22, the check is imported nowhere outside its own module, and its warm-start
helper raises on the hard-infeasible epochs the objective has flagged since, so it cannot have run
in a long time. Run by hand that night on the live per-rate strata, it FAILS on both fitted rates.

So the check now runs where the surface is fitted, and its answer travels with the stratum.

THE PI'S RULING (2026-09-22, ruling 6 of decision 233): **a warning, never blocking.** The spec's own
consequence -- "any single failure -> surrogate may not select settings" -- is not adopted. A failed
check changes no recommendation, refuses nothing, and is reported.

WHAT IS ASSERTED: that the check runs and lands on the stratum; that it says "not computable" rather
than a number where a fold has too little to train on (a rate with one or three epochs, which this
record has); that it never refuses anything; and that its wording says the consequence.

Merged here 2026-10-05: test_calibration_diagnosis.py, test_loo_parallel_folds.py (each under its own heading below).
"""
import numpy as np
import pytest

from StimOptimizer import stage1_openloop as S1


from StimOptimizer.tests.test_stage1 import _matrix       # the fixture Stage 1 is already tested on
import pandas as pd

from StimOptimizer.routines import surrogate as SUR


def _fitted_strata(res):
    """Every fitted per-rate surface, reached the way the page's own serialiser reaches them
    (`bravo_service._rate_stratum_index`): one joint stratum per pulse-width pair under `.slices`,
    and each of those holds one `RateStratum` per rate."""
    out = []
    for _key, sl in (getattr(res, "slices", None) or {}).items():
        for _rate, rs in (getattr(sl, "rate_strata", None) or {}).items():
            if getattr(rs, "fitted", False):
                out.append(rs)
    return out


@pytest.fixture(scope="module")
def checked():
    """The fit with the check computed, shared by the two tests that read it (2026-10-02; each
    made this identical fit itself before)."""
    return S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                         data_horizon="2026-12-31")


def test_every_fitted_surface_carries_the_pre_registered_check_and_it_blocks_nothing(checked):
    res = checked
    strata = _fitted_strata(res)
    assert strata, "the fixture must fit at least one per-rate surface"
    for rs in strata:
        cal = rs.meta.get("calibration")
        assert cal is not None, "every fitted surface reports the check"
        assert set(cal) >= {"checks", "summary", "passes", "blocking", "consequence"}
        assert cal["blocking"] is False, "the PI, 2026-09-22: a warning, never blocking"
        assert "warning" in cal["consequence"].lower()
        assert "refuses nothing" in cal["consequence"].lower()
        # the three pre-registered criteria are named, whatever their answers
        assert set(cal["checks"]) == {"C1_loeo_skill", "C2_loera_skill", "C3_calibration"}
        for k, v in cal["checks"].items():
            assert v in (True, False, None), (k, v)


def test_a_fold_that_cannot_be_trained_on_says_not_computable_rather_than_passing_or_failing():
    """A fold with nothing to hold out is not a pass and not a failure.

    (The first version of this test tried to reach that state through a small `run_stage1` fit and
    could not: at nine epochs the block fold splits three ways and IS computable. The state belongs
    to the fold, so it is tested at the fold.)
    """
    res = S1.run_stage1(_matrix(n_per_cell=9, pw_pairs=((60.0, 160.0),), rates=(55.0,)),
                        hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31")
    rs = _fitted_strata(res)[0]
    gp = rs.gp
    y, v = np.asarray(gp.y_, float), np.asarray(gp.y_var_, float)

    one_block, ratio = S1._one_calibration_fold(gp, y, v, np.zeros(len(y), dtype=int),
                                                name="leave-one-block-out")
    assert ratio is None and one_block["mae_ratio"] is None
    assert "not computable" in one_block["reason"].lower() and "one group" in one_block["reason"]

    # and a fold whose held-out epochs mostly cannot be predicted comes back the same way: the
    # surrogate's own `loo_predict` skips any fold with fewer than three rows to train on, and a
    # ratio computed from the two that survived would be a number nobody should read.
    class _MostlyUnpredictable:
        y_, y_var_ = gp.y_, gp.y_var_

        @staticmethod
        def loo_predict(groups=None):
            mu = np.full(len(y), np.nan)
            mu[:2] = y[:2]
            return mu, np.full(len(y), 1.0)

    thin, ratio2 = S1._one_calibration_fold(_MostlyUnpredictable, y, v, np.arange(len(y)), name="x")
    assert ratio2 is None and "not computable" in (thin["reason"] or "").lower()
    assert "could be predicted" in thin["reason"]

    # whatever the answers are, the block never refuses anything
    cal = rs.meta["calibration"]
    assert cal["blocking"] is False and cal["checks"]["C2_loera_skill"] in (True, False, None)


def test_the_check_never_changes_what_the_search_recommends(checked):
    """The same fit, with the check computed and with it switched off, must resolve the same way.

    Since 2026-10-02 most Stage 1 tests run with the check switched off, because it is a warning
    that changes nothing and it was most of their time; this test is what licenses that, so it
    compares EVERY fitted surface (not only the first) and the frozen configuration itself."""
    res_on = checked
    res_off = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                            data_horizon="2026-12-31", calibration_check=False)
    on, off = _fitted_strata(res_on), _fitted_strata(res_off)
    assert len(on) == len(off) and on
    for a, b in zip(on, off):
        assert a.resolution.get("resolved") == b.resolution.get("resolved")
        assert a.x_star == b.x_star and np.isclose(a.mu_star, b.mu_star)
        assert b.meta.get("calibration") is None, "switched off means not computed, not a blank"
    assert res_on.frozen.describe() == res_off.frozen.describe()


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))


# ================================================================================================
# From test_calibration_diagnosis.py (merged here 2026-10-05).
# Why a pain map fails its calibration check: thin data, movement between blocks of time, or the
# wrong shape (panel C item 3; built 2026-09-23).
#
# The pre-registered check (`OBJECTIVE_SPEC.md` §6, decision 238) says only pass or fail. Panel C made
# the reason a condition on changing the model: a boundary-avoiding kernel answers thin data at the
# edges, and is useless if the surface moves between blocks of time, or if its intervals are too narrow
# everywhere. So each held-out error, in units of the model's own stated uncertainty, is split into
# the part its whole block shares (the block moved) and the rest (within the block), and the model's
# stated uncertainty is compared with the spread of what it predicts. Beside that, the reference no
# model choice can explain away: did pain at the one setting delivered most often move between the
# blocks?
#
# Each case below is constructed so its answer is known, and the diagnosis must name it.
# ================================================================================================


class _FakeGP:
    """What the diagnosis reads from a fitted surface: the targets, their noise, and held-out
    predictions per group -- set directly, so each case has a known cause."""

    def __init__(self, y, y_var, mu, sd):
        self.y_ = np.asarray(y, float)
        self.y_var_ = np.asarray(y_var, float)
        self._mu, self._sd = np.asarray(mu, float), np.asarray(sd, float)

    def loo_predict(self, groups=None):
        return self._mu.copy(), self._sd.copy()


def _sub(n, *, amps=None, J=None, obs_var=None):
    t0 = pd.date_range("2026-01-01", periods=n, freq="7D", tz="UTC")
    amps = amps if amps is not None else [(1.0 + (i % 4) * 0.5, 2.5) for i in range(n)]
    return pd.DataFrame(dict(t0=t0, amp_mA_Left=[a for a, _ in amps], amp_mA_Right=[b for _, b in amps],
                             J=(J if J is not None else np.zeros(n)),
                             obs_var=(obs_var if obs_var is not None else np.ones(n)), n=5.0))


def _blocks(n):
    return S1._fold_labels_by_time(_sub(n))


def test_a_surface_that_moves_between_blocks_is_named_as_such():
    rng = np.random.default_rng(0)
    n = 30
    b = _blocks(n)
    offset = np.array([2.0, 0.0, -2.0])[b]
    y = 5.0 + offset + rng.normal(0, 0.3, n)
    gp = _FakeGP(y, np.full(n, 0.09), np.full(n, 5.0), np.full(n, 0.3))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] == "moves between blocks of time", d
    assert d["between_block_share"] > 0.8
    assert d["between_block_p"] < 0.001


def test_intervals_too_narrow_everywhere_are_named_as_the_shape_or_noise_model():
    rng = np.random.default_rng(1)
    n = 30
    y = 5.0 + rng.normal(0, 2.0, n)                      # scatter the model does not admit
    gp = _FakeGP(y, np.full(n, 0.04), np.full(n, 5.0), np.full(n, 0.2))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] == "too confident within blocks: the shape or the noise model", d
    assert d["between_block_share"] < 0.5


def test_wide_honest_intervals_are_named_as_thin_data():
    rng = np.random.default_rng(2)
    n = 30
    y = 5.0 + rng.normal(0, 1.0, n)
    gp = _FakeGP(y, np.full(n, 0.25), np.full(n, 5.0), np.full(n, 1.0))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["coverage95"] >= 0.85
    assert d["verdict"] == "honest but uninformative: thin data", d


def test_pain_at_the_most_delivered_setting_is_checked_across_blocks():
    n = 30
    b = _blocks(n)
    amps = [(2.0, 2.5)] * n                              # one setting throughout
    moved = _sub(n, amps=amps, J=np.array([6.0, 5.0, 4.0])[b], obs_var=np.full(n, 0.25))
    still = _sub(n, amps=amps, J=np.full(n, 5.0) + np.tile([0.1, -0.1], n // 2), obs_var=np.full(n, 0.25))
    gp = _FakeGP(np.full(n, 5.0), np.full(n, 0.25), np.full(n, 5.0), np.full(n, 1.0))
    r1 = S1.calibration_diagnosis(gp, moved)["reference_setting"]
    r2 = S1.calibration_diagnosis(gp, still)["reference_setting"]
    assert r1["setting"] == {"amp_mA_Left": 2.0, "amp_mA_Right": 2.5}
    assert r1["moved"] is True and r1["p"] < 0.001
    assert r2["moved"] is False
    assert len(r1["by_block"]) == 3


def test_fewer_than_two_blocks_with_predictions_is_not_computable_rather_than_a_verdict():
    n = 6
    gp = _FakeGP(np.ones(n), np.ones(n), np.full(n, np.nan), np.full(n, np.nan))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] is None and d["reason"]


def test_the_calibration_block_carries_the_diagnosis_and_its_own_numbers_do_not_move():
    """The diagnosis shares the held-out predictions the calibration check already makes, so the
    check's numbers are the same with it as without it."""
    rng = np.random.default_rng(3)
    n = 24
    y = 5.0 + rng.normal(0, 1.0, n)
    gp = _FakeGP(y, np.full(n, 0.25), 5.0 + rng.normal(0, 0.5, n), np.full(n, 0.6))
    out = S1.stratum_calibration(gp, _sub(n))
    assert "diagnosis" in out and out["diagnosis"]["verdict"] is not None
    assert out["blocking"] is False
    assert out["summary"]["loera"]["coverage95"] == out["diagnosis"]["coverage95"]


# ================================================================================================
# From test_loo_parallel_folds.py (merged here 2026-10-05).
# The calibration check's held-out folds refitted side by side in worker processes (the PI,
# 2026-09-25: "there's no reason it should take five minutes ... vectorize it!").
#
# Each fold of `ObjectiveGP.loo_predict` refits the pain map from scratch on its training rows, its
# hyperparameters re-estimated from twelve random restarts seeded the same way every time, so a fold
# is a pure function of its rows. Running the folds in separate processes changes WHERE each is
# computed, never what: pinned here bit for bit (np.array_equal, never a tolerance), for single-epoch
# folds and for blocks of time, on a three-input and a five-input map, and whichever way the
# linear-algebra thread pool of the calling process is set.
# ================================================================================================


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
