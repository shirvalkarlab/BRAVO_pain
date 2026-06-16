"""Regression tests for the pipeline-level statistics helpers added in the rigor review.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_pipeline_stats.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers import pipeline  # noqa: E402
from Biomarkers.routines import stats_utils as su  # noqa: E402


def test_maxabs_corr_pairwise_nan():
    """_maxabs_corr must equal the max over columns of the per-column PAIRWISE-NaN-deleted Pearson r,
    so feature cells with zero->NaN gaps still contribute on their own finite rows (matching the
    per-cell selection/FDR space the permutation null is compared against)."""
    rng = np.random.default_rng(0)
    N, M = 200, 40
    X = rng.normal(size=(N, M))
    y = 0.5 * X[:, 3] + rng.normal(size=N)        # planted signal in column 3
    X[::4, 3] = np.nan                            # gaps in the signal column
    X[10:30, 7] = np.nan                          # gaps elsewhere
    ref = []
    for j in range(M):
        v = np.isfinite(X[:, j]) & np.isfinite(y)
        if v.sum() >= 4 and np.std(X[v, j]) > 0:
            ref.append(abs(np.corrcoef(X[v, j], y[v])[0, 1]))
    assert abs(pipeline._maxabs_corr(X, y) - max(ref)) < 1e-9


def test_maxabs_corr_degenerate():
    rng = np.random.default_rng(1)
    X = np.full((50, 5), np.nan)
    y = rng.normal(size=50)
    assert np.isnan(pipeline._maxabs_corr(X, y))                 # all-NaN -> nan, not a crash
    Xc = np.ones((50, 3)); Xc[:, 1] = rng.normal(size=50)
    r = pipeline._maxabs_corr(Xc, y)
    assert np.isfinite(r) and 0 <= r <= 1                        # constant columns ignored


def test_maxabs_corr_matches_full_when_no_nan():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(120, 30)); y = rng.normal(size=120)
    cols = np.array([abs(np.corrcoef(X[:, j], y)[0, 1]) for j in range(X.shape[1])])
    assert abs(pipeline._maxabs_corr(X, y) - cols.max()) < 1e-9


def test_vectorized_perm_matches_loop_statistic():
    """The VECTORIZED batched family-max statistic must be FLOATING-POINT IDENTICAL to looping
    _maxabs_corr over the same circular-block permutations (with feature NaN gaps present)."""
    rng = np.random.default_rng(3)
    N, K = 200, 80
    X = rng.normal(size=(N, K))
    X[rng.random((N, K)) < 0.25] = np.nan                 # zero->NaN-style gaps
    y = rng.normal(size=N)
    block = su.block_length_for(y, N)
    Pm = su.circular_block_perm_matrix(N, block, 250, np.random.default_rng(9))
    loop = np.array([pipeline._maxabs_corr(X, y[Pm[i]]) for i in range(Pm.shape[0])])
    # mirror the batched internals on the SAME permutation matrix
    M = np.isfinite(X).astype(float); Xm = np.where(M > 0, X, 0.0)
    nj = M.sum(0); sx = Xm.sum(0); sxx = (Xm * Xm).sum(0)
    vx = sxx - sx * sx / nj
    Yp = y[Pm]; cov = (Yp @ Xm) - (Yp @ M) * sx[None, :] / nj[None, :]
    vy = ((Yp * Yp) @ M) - (Yp @ M) ** 2 / nj[None, :]
    rr = cov / np.sqrt(vx[None, :] * vy)
    rr = np.where((nj >= 4)[None, :] & np.isfinite(rr), np.abs(rr), -np.inf)
    batch = rr.max(1)
    assert np.nanmax(np.abs(loop - batch)) < 1e-9


def test_block_perm_maxcorr_pvalue_behavior():
    """Vectorized p-value: tiny with a planted strong association; averaged over several independent
    null draws it sits well above the floor (a single null draw's p is Uniform, hence not asserted)."""
    rng = np.random.default_rng(4)
    N, K = 150, 40
    X = rng.normal(size=(N, K))
    y_real = X[:, 0] + 0.1 * rng.normal(size=N)
    p_real, used = pipeline._block_perm_maxcorr_pvalue(X, y_real, n_perm=300, seed=1)
    assert used > 0 and p_real < 0.02                       # strong planted signal -> tiny p
    null_ps = [pipeline._block_perm_maxcorr_pvalue(X, rng.normal(size=N), n_perm=300, seed=s)[0]
               for s in range(8)]
    assert np.mean(null_ps) > 0.1 and np.mean(null_ps) > p_real   # nulls average well above the floor


if __name__ == "__main__":
    test_maxabs_corr_pairwise_nan()
    test_maxabs_corr_degenerate()
    test_maxabs_corr_matches_full_when_no_nan()
    test_vectorized_perm_matches_loop_statistic()
    test_block_perm_maxcorr_pvalue_behavior()
    print("All pipeline_stats tests passed.")
