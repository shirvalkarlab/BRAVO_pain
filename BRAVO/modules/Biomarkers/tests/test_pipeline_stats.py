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


if __name__ == "__main__":
    test_maxabs_corr_pairwise_nan()
    test_maxabs_corr_degenerate()
    test_maxabs_corr_matches_full_when_no_nan()
    print("All pipeline_stats tests passed.")
