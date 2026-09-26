"""The sign-flip bootstrap never builds a samples-by-samples matrix (P-12, section 5 item 3).

`_BootstrapPlan` formed the restricted residuals through the projection matrix
`Xr @ pinv(Xr)`, which has one row and one column per sample. The band-power cells on the
Closed-Loop evidence hold 43,835 to 64,510 samples, so that matrix is 15 to 33 GB; for R 0-3+ it
exceeded the container's 42 GB and the process was killed, which is why that pair's P-12 cells
were never measured (`artifacts/analysis_2026-09-25_P12_two_uncertainty_methods.md`). The same
residuals come from projecting each vector directly, `Xr @ (pinv(Xr) @ v)`, which needs memory in
proportion to the samples, not their square.
"""
import pathlib
import sys
import tracemalloc

import numpy as np

MODULES_DIR = pathlib.Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from Biomarkers.routines import analytics as E


def _design(n, n_clusters, seed=0):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_clusters), n // n_clusters)
    x = rng.normal(size=groups.size)
    X = np.column_stack([np.ones_like(x), x, rng.normal(size=groups.size)])
    y = 0.2 * x + rng.normal(size=groups.size) + rng.normal(size=n_clusters)[groups]
    return y, X, groups


def test_the_plan_needs_memory_in_proportion_to_the_samples_not_their_square():
    """5,000 samples: the old projection matrix alone is 200 MB; the plan must peak far below."""
    y, X, groups = _design(5000, 50)
    tracemalloc.start()
    try:
        plan = E._BootstrapPlan(y, X, groups, coef_index=1, n_boot=99, seed=0, impose_null=True,
                                chunk=16)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert plan.available
    assert peak < 60e6, f"peak {peak / 1e6:.0f} MB: a samples-by-samples matrix is being built"


def test_the_restricted_residuals_are_the_projection_residuals():
    """The residuals the plan uses equal the textbook ones, M_r y and M_r x_j, computed here with
    the explicit projection matrix on a small design (the arithmetic order differs, so this
    compares to a rounding tolerance; the p-values themselves are compared exactly below)."""
    y, X, groups = _design(400, 20, seed=3)
    order = np.argsort(groups, kind="stable")
    Xs, ys = X[order], y[order]
    Xr = Xs[:, [0, 2]]
    P = Xr @ np.linalg.pinv(Xr)
    plan = E._BootstrapPlan(y, X, groups, coef_index=1, n_boot=99, seed=0, impose_null=True)
    Aj = (np.linalg.inv(Xs.T @ Xs) @ Xs.T)[1]
    W, _, _ = E._rademacher_weights(20, 99, 0)
    Wb = np.repeat(W, np.unique(groups, return_counts=True)[1], axis=1)
    np.testing.assert_allclose(plan.num0, (Wb * (ys - P @ ys)[None, :]) @ Aj, rtol=0, atol=1e-10)
    np.testing.assert_allclose(plan.num1, (Wb * (Xs[:, 1] - P @ Xs[:, 1])[None, :]) @ Aj,
                               rtol=0, atol=1e-10)
