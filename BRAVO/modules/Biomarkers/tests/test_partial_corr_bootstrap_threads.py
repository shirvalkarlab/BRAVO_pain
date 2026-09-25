"""Speed-up item 5 (the PI, 2026-09-25): the partial-correlation interval behind E2 with the current
taken out runs its least-squares fits on ONE linear-algebra thread, and gives the same numbers.

Measured on RCS08 (53,246 samples, two columns): the 1,003 fits took 9.6 s on the container's 16
threads, and 40 of them took 0.36 s against 0.03 s on one -- spreading a two-column fit over 16
threads costs more than the fit. The fits returned identical coefficients at 1, 2, 4, 8 and 16
threads. This test holds the interval to the same values with the cap as without it. Container suite.
"""
import numpy as np

from modules.Biomarkers.routines import analytics as A


def _data(seed=0, n_reports=40, per=60):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_reports), per)
    cov_r = rng.choice([0.0, 1.0, 1.6, 2.5, 3.0], n_reports)
    cov = cov_r[groups]
    pain = (7 - 0.4 * cov_r + rng.normal(0, 1, n_reports))[groups]
    x = 50 + 5 * cov + rng.normal(0, 3, groups.size)
    return x, pain, cov, groups


def test_the_interval_is_the_same_on_one_thread_as_on_the_default():
    x, pain, cov, groups = _data()
    for shape in ("line", "spline"):
        capped = A._partial_corr_report_bootstrap(x, pain, cov, groups, shape=shape, n_boot=200, seed=0, alpha=0.05)
        free = A._partial_corr_report_bootstrap(x, pain, cov, groups, shape=shape, n_boot=200, seed=0, alpha=0.05,
                                                blas_threads=None)
        assert capped == free and capped[0] is not None, (shape, capped, free)
