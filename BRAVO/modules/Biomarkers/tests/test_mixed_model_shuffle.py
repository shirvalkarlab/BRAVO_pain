"""The mixed model's chance test with every shuffle at once (`routines/mixed_model_shuffle.py`,
decision 477): each piece checked against a slow, written-out version of the same calculation.

Run:  python3 modules/Biomarkers/tests/test_mixed_model_shuffle.py   (no R needed)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import mixed_model_shuffle as M
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import mixed_model_shuffle as M


def _layout(seed=0, n_weeks=12, per_week=(3, 14)):
    rng = np.random.default_rng(seed)
    sizes = rng.integers(per_week[0], per_week[1], n_weeks)
    cl = np.repeat(np.arange(n_weeks), sizes)
    return rng, cl, len(cl)


def _dense_sigma(w, tau, cl):
    Z = (cl[:, None] == np.unique(cl)[None, :]).astype(float)
    return np.diag(1.0 / w) + tau * Z @ Z.T


def _binomial_null(seed=0, tau=0.7, covariate=False):
    rng, cl, n = _layout(seed)
    b = rng.normal(0, np.sqrt(tau), cl.max() + 1)
    X0 = np.column_stack([np.ones(n)] + ([rng.normal(size=n)] if covariate else []))
    eta = X0 @ np.r_[-0.3, 0.8][:X0.shape[1]] + b[cl]
    y = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(float)
    return M.NullModel(y=y, eta=eta, tau=tau, cluster=cl, X0=X0), rng


def test_sigma_inverse_matches_the_dense_inverse():
    rng, cl, n = _layout(1)
    w = rng.uniform(0.05, 0.25, n)
    Mx = rng.normal(size=(n, 7))
    for tau in (0.0, 0.3, 4.0):
        dense = np.linalg.solve(_dense_sigma(w, tau, cl), Mx)
        fast = M.sigma_inverse_times(Mx, w, tau, cl, cl.max() + 1)
        assert np.max(np.abs(fast - dense)) < 1e-9 * np.max(np.abs(dense)), tau


def test_score_z_matches_the_dense_formula():
    null, rng = _binomial_null(2, covariate=True)
    x = rng.normal(size=len(null.y))
    Sinv = np.linalg.inv(_dense_sigma(null.w, null.tau, null.cl))
    X0 = null.X0
    P = Sinv - Sinv @ X0 @ np.linalg.inv(X0.T @ Sinv @ X0) @ X0.T @ Sinv
    z_dense = (x @ P @ null.y_work) / np.sqrt(x @ P @ x)
    assert abs(null.score_z(x) - z_dense) < 1e-10 * max(1.0, abs(z_dense))


def test_the_null_fixed_effects_leave_the_statistic_unchanged():
    null, rng = _binomial_null(3, covariate=True)
    x = rng.normal(size=len(null.y))
    shifted = x + null.X0 @ np.array([5.0, -2.5])
    assert abs(null.score_z(x) - null.score_z(shifted)) < 1e-9
    assert np.max(np.abs(null.X0.T @ null.r)) < 1e-9


def test_with_no_week_variance_it_is_the_ordinary_logistic_score_test():
    rng, cl, n = _layout(4)
    y = (rng.random(n) < 0.4).astype(float)
    mu = np.full(n, y.mean())                                    # the intercept-only fit
    null = M.NullModel(y=y, eta=np.log(mu / (1 - mu)), tau=0.0, cluster=cl)
    x = rng.normal(size=n)
    xc = x - x.mean()
    z_hand = (x @ (y - mu)) / np.sqrt(mu[0] * (1 - mu[0]) * (xc @ xc))
    assert abs(null.score_z(x) - z_hand) < 1e-10


def test_gaussian_matches_the_dense_gls_score():
    rng, cl, n = _layout(5)
    tau, s2 = 0.9, 1.7
    y = rng.normal(size=n) + rng.normal(0, 1, cl.max() + 1)[cl]
    null = M.NullModel(y=y, eta=np.full(n, y.mean()), tau=tau, cluster=cl, family="gaussian",
                       residual_var=s2)
    x = rng.normal(size=n)
    Sinv = np.linalg.inv(s2 * np.eye(n) + tau * (cl[:, None] == cl[None, :]))
    one = np.ones(n)
    P = Sinv - np.outer(Sinv @ one, one @ Sinv) / (one @ Sinv @ one)
    z_dense = (x @ P @ y) / np.sqrt(x @ P @ x)
    assert abs(null.score_z(x) - z_dense) < 1e-10 * max(1.0, abs(z_dense))


def test_every_rotation_once_observed_first():
    x = np.arange(7.0)
    R = M.rotation_matrix(x)
    assert R.shape == (7, 7)
    assert np.array_equal(R[:, 0], x)
    assert len({tuple(c) for c in R.T}) == 7
    for k in range(7):
        assert np.array_equal(R[:, k], np.roll(x, -k))


def test_the_rotation_p_is_exact_and_its_smallest_value_is_one_over_n():
    null, rng = _binomial_null(6)
    n = len(null.y)
    x = rng.normal(size=n)
    out = M.shuffle_test(null, x)
    assert out["n_orders"] == n and out["p_floor"] == 1.0 / n
    assert abs(out["p"] * n - round(out["p"] * n)) < 1e-9          # a whole number of orders over n
    z = M.shuffle_test(null, x, keep_null=True)["z_all"]
    assert out["p"] == (np.sum(np.abs(z[1:]) >= abs(z[0]) - 1e-10 * max(1, abs(z[0]))) + 1) / n
    # the statistic for every order equals the statistic of that order computed on its own
    for k in (1, 5, n - 1):
        assert abs(z[k] - null.score_z(np.roll(x, -k))) < 1e-10


def test_sorting_by_time_rotates_in_time_order():
    null, rng = _binomial_null(7)
    n = len(null.y)
    x = rng.normal(size=n)
    t = rng.permutation(n).astype(float)                          # the rows are not in time order
    a = M.shuffle_test(null, x, order=t, keep_null=True)
    srt = np.argsort(t)
    for k in (1, 9):
        xr = np.empty(n); xr[srt] = np.roll(x[srt], -k)
        assert np.any(np.isclose(a["z_all"], null.score_z(xr), rtol=0, atol=1e-10))


def test_a_tie_counts_as_extreme():
    assert M.shuffle_p(np.array([2.0, 2.0 + 1e-13, 0.1, -3.0])) == 3 / 4
    assert M.shuffle_p(np.array([2.0, 1.0, 0.1, -1.0]), "greater") == 1 / 4
    assert M.shuffle_p(np.array([-2.0, 1.0, 0.1, -1.0]), "less") == 1 / 4
    assert np.isnan(M.shuffle_p(np.array([np.nan, 1.0])))


def test_within_cluster_shuffles_stay_inside_their_week():
    null, rng = _binomial_null(8)
    x = rng.normal(size=len(null.y))
    X = M.within_cluster_matrix(x, null.cl, 50, rng)
    assert np.array_equal(X[:, 0], x)
    for j in range(null.G):
        g = null.cl == j
        for k in range(1, 51):
            assert np.array_equal(np.sort(X[g, k]), np.sort(x[g]))


def test_a_band_tied_to_pain_is_found_and_an_unrelated_one_is_not():
    rng, cl, n = _layout(9, n_weeks=20, per_week=(6, 10))
    x = np.cumsum(rng.normal(size=n)) * 0.2 + rng.normal(size=n)    # drifts, like band power
    b = rng.normal(0, 0.6, cl.max() + 1)
    eta = -0.2 + 1.5 * (x - x.mean()) / x.std() + b[cl]
    y = (rng.random(n) < 1 / (1 + np.exp(-eta))).astype(float)
    mu0 = np.clip(np.array([y[cl == j].mean() for j in range(cl.max() + 1)])[cl], 0.05, 0.95)
    null = M.NullModel(y=y, eta=np.log(mu0 / (1 - mu0)), tau=0.36, cluster=cl)
    assert M.shuffle_test(null, x)["p"] <= 0.01
    other = np.cumsum(rng.normal(size=n)) * 0.2 + rng.normal(size=n)
    assert M.shuffle_test(null, other)["p"] > 0.01


def test_the_rotation_test_holds_its_false_positive_rate():
    """An unrelated band that drifts, against pain with week effects and its own drift: p <= 0.05 in
    about 5% of 400 made-up records (binomial 99.9% range for 400 at 5%: 2.0% to 9.0%)."""
    rng, cl, n = _layout(10, n_weeks=25, per_week=(4, 9))
    hits = 0
    for _ in range(400):
        b = rng.normal(0, 0.8, cl.max() + 1)
        y = (rng.random(n) < 1 / (1 + np.exp(-(b[cl])))).astype(float)
        mu0 = np.clip(np.array([y[cl == j].mean() for j in range(cl.max() + 1)])[cl], 0.05, 0.95)
        null = M.NullModel(y=y, eta=np.log(mu0 / (1 - mu0)), tau=0.64, cluster=cl)
        e = rng.normal(size=n); x = np.empty(n); x[0] = e[0]
        for i in range(1, n):
            x[i] = 0.8 * x[i - 1] + e[i]
        hits += M.shuffle_test(null, x)["p"] <= 0.05
    assert 0.020 <= hits / 400 <= 0.090, hits


def test_refuses_what_it_cannot_score():
    null, rng = _binomial_null(11)
    for bad in (np.r_[np.nan, rng.normal(size=len(null.y) - 1)], rng.normal(size=3)):
        try:
            M.shuffle_test(null, bad)
        except ValueError:
            continue
        raise AssertionError("accepted an x it cannot score")
    try:
        M.NullModel(y=[0, 1], eta=[0.0, 0.0], tau=0, cluster=[0, 0], family="poisson")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted an unknown family")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
