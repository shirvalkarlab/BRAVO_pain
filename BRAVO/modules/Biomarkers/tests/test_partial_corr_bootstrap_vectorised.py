"""The partial correlation's bootstrap interval, vectorised (the PI, 2026-10-04, decision 422).

Each of the 500 resamples of whole pain reports used to refit two least-squares lines on tens of
thousands of rows. A resample is a vector of counts, one per report, so all of them now come from
per-report sums in one matrix product. Same draws, same order; the arithmetic is reordered, so the
interval ends agree with the loop to about 1e-12 (the PI accepted agreement to six or seven
digits for this change, 2026-10-04). Pinned against the loop, kept as
`_partial_corr_report_bootstrap_loop`, on constructed data with missing values, a resample that can
lose all spread in the covariate, and other shapes, which keep the loop.

Merged here 2026-10-05: test_partial_corr_bootstrap_threads.py.
"""
import numpy as np
from modules.Biomarkers.routines import analytics as A


def _data(seed=0, n_rep=40, per=30, cov_levels=(0.0, 1.5, 3.0), missing=0.02):
    rng = np.random.default_rng(seed)
    g = np.repeat(np.arange(n_rep), per)
    cur = rng.choice(cov_levels, n_rep)[g] + rng.normal(0, 0.01, g.size)
    pain = rng.normal(5, 2, n_rep)[g]
    x = 200 + 10 * cur + 3 * pain + rng.normal(0, 15, g.size)
    for v in (x, pain, cur):
        v[rng.random(g.size) < missing] = np.nan
    return x, pain, cur, g


def test_the_vectorised_interval_agrees_with_the_loop_to_twelve_digits():
    for seed in range(4):
        x, y, c, g = _data(seed)
        want = A._partial_corr_report_bootstrap_loop(x, y, c, g, shape="line", n_boot=300,
                                                     seed=7, alpha=0.05)
        got = A._partial_corr_report_bootstrap(x, y, c, g, shape="line", n_boot=300, seed=7,
                                               alpha=0.05)
        assert want[0] is not None and got[0] is not None
        assert np.allclose(got, want, rtol=1e-12, atol=1e-12), (seed, got, want)


def test_a_covariate_with_no_spread_in_a_resample_is_refused_as_the_loop_refuses():
    x, y, c, g = _data(seed=1, n_rep=6, per=20, cov_levels=(2.0,), missing=0.0)
    c = np.full_like(c, 2.0)                       # no spread at all: every resample is refused
    assert A._partial_corr_report_bootstrap_loop(x, y, c, g, shape="line", n_boot=100, seed=1,
                                                 alpha=0.05) == (None, None)
    assert A._partial_corr_report_bootstrap(x, y, c, g, shape="line", n_boot=100, seed=1,
                                            alpha=0.05) == (None, None)


def test_other_shapes_keep_the_loop():
    x, y, c, g = _data(seed=2)
    for shape in ("quadratic",):
        a = A._partial_corr_report_bootstrap_loop(x, y, c, g, shape=shape, n_boot=60, seed=3,
                                                  alpha=0.05)
        b = A._partial_corr_report_bootstrap(x, y, c, g, shape=shape, n_boot=60, seed=3, alpha=0.05)
        assert a == b


# --------------------------------------------------------------------------------------------------
# merged from test_partial_corr_bootstrap_threads.py
# Speed-up item 5 (the PI, 2026-09-25): the partial-correlation interval behind E2 with the current
# taken out runs its least-squares fits on ONE linear-algebra thread, and gives the same numbers.
#
# Measured on RCS08 (53,246 samples, two columns): the 1,003 fits took 9.6 s on the container's 16
# threads, and 40 of them took 0.36 s against 0.03 s on one -- spreading a two-column fit over 16
# threads costs more than the fit. The fits returned identical coefficients at 1, 2, 4, 8 and 16
# threads. This test holds the interval to the same values with the cap as without it. Container suite.


def _data_report_level(seed=0, n_reports=40, per=60):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_reports), per)
    cov_r = rng.choice([0.0, 1.0, 1.6, 2.5, 3.0], n_reports)
    cov = cov_r[groups]
    pain = (7 - 0.4 * cov_r + rng.normal(0, 1, n_reports))[groups]
    x = 50 + 5 * cov + rng.normal(0, 3, groups.size)
    return x, pain, cov, groups


def test_the_interval_is_the_same_on_one_thread_as_on_the_default():
    x, pain, cov, groups = _data_report_level()
    for shape in ("line", "spline"):
        capped = A._partial_corr_report_bootstrap(x, pain, cov, groups, shape=shape, n_boot=200, seed=0, alpha=0.05)
        free = A._partial_corr_report_bootstrap(x, pain, cov, groups, shape=shape, n_boot=200, seed=0, alpha=0.05,
                                                blas_threads=None)
        assert capped == free and capped[0] is not None, (shape, capped, free)
