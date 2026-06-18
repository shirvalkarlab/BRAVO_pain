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


def test_select_biomarker_band_enforces_50hz_cap():
    """The 50 Hz biomarker cap: even when the globally strongest |R| sits at/above 50 Hz, the
    selector must NEVER pick it — it returns the strongest band strictly below 50 Hz. A grid whose
    only finite cells are >=50 Hz returns None (nothing selectable)."""
    rng = np.random.default_rng(0)
    N = 60
    f_set = np.array([10.0, 20.0, 40.0, 55.0, 60.0])
    labels = np.linspace(0, 10, N) + rng.normal(0, 0.3, N)
    feat = rng.normal(0, 1, (N, 1, f_set.size))
    feat[:, 0, 4] = labels * 2 + rng.normal(0, 0.05, N)   # 60 Hz: near-perfect, strongest GLOBALLY
    feat[:, 0, 1] = labels + rng.normal(0, 0.6, N)         # 20 Hz: strong but weaker, < 50
    corr = np.array([[np.corrcoef(feat[:, 0, j], labels)[0, 1] for j in range(f_set.size)]])
    result = {"corr": corr, "f_set": f_set, "feature": feat, "labels": labels,
              "pval": np.full((1, f_set.size), 0.001)}
    # The global argmax |R| is the 60 Hz cell -- the cap must override it.
    assert f_set[int(np.argmax(np.abs(corr[0])))] >= 50.0
    sel = pipeline.select_biomarker_band(result, q_threshold=0.05)
    assert sel is not None
    assert sel[4] < pipeline.MAX_BIOMARKER_FREQ_HZ, f"selected band {sel[4]} Hz violates the 50 Hz cap"
    assert sel[4] == 20.0
    # When every finite cell is >= 50 Hz, NOTHING is selectable.
    res_all_high = dict(result, f_set=np.array([50.0, 55.0, 60.0, 70.0, 80.0]))
    assert pipeline.select_biomarker_band(res_all_high) is None


def test_band_inference_mad_rejection_and_50hz_perm_family():
    """_band_inference must (a) apply MAD>=3 rejection on the selected band's feature AND label, so a
    single artifact session is excluded from the reported n / partial r / CI, and (b) restrict the
    family-max permutation null to cells STRICTLY below the 50 Hz cap — a planted dominant
    correlation at a >=50 Hz bin must NOT inflate perm_obs."""
    from Biomarkers.routines import streaming_psd
    f = streaming_psd.F_SET
    Ff = len(f)
    rng = np.random.default_rng(11)
    E = 40
    labels = np.linspace(0, 10, E)
    lo = int(np.argmin(np.abs(f - 20.0)))                 # a genuine sub-50 Hz signal bin
    feat = rng.normal(0, 1, (E, 2, Ff))
    feat[:, 0, lo] = labels + rng.normal(0, 0.3, E)
    corr = np.array([[(np.corrcoef(feat[:, c, j], labels)[0, 1] if np.std(feat[:, c, j]) > 0 else 0.0)
                      for j in range(Ff)] for c in range(2)])
    base = {"f_set": f, "corr": corr, "pval": np.full((2, Ff), 0.001), "feature": feat,
            "labels": labels, "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "transform": "log"}

    # (a) MAD rejection: plant a label spike, n must drop below E (the spike session is excluded).
    labels_spk = labels.copy(); labels_spk[E // 2] = 1e6
    inf = pipeline._band_inference(dict(base, labels=labels_spk), 0, lo, corr[0, lo], 0.001,
                                   float(f[lo]), 0.01, True, stim=None, n_perm=200)
    assert inf["n"] < E, "MAD>=3 did not drop the artifact-label session from the band's n"
    assert inf["perm_n"] > 0

    # (b) Plant a near-perfect correlation at a >=50 Hz bin and (artificially) select it; the
    # family-max null is computed over <50 Hz cells ONLY, so perm_obs must stay modest, not ~1.0.
    hi = int(np.argmin(np.abs(f - 70.0)))
    feat2 = rng.normal(0, 1, (E, 2, Ff))
    feat2[:, 0, hi] = labels * 5.0                         # corr ~1.0 at 70 Hz
    corr2 = np.array([[(np.corrcoef(feat2[:, c, j], labels)[0, 1] if np.std(feat2[:, c, j]) > 0 else 0.0)
                       for j in range(Ff)] for c in range(2)])
    inf2 = pipeline._band_inference(dict(base, feature=feat2, corr=corr2), 0, hi, corr2[0, hi],
                                    0.001, float(f[hi]), 0.01, True, stim=None, n_perm=300)
    assert inf2["perm_obs"] is None or inf2["perm_obs"] < 0.9, \
        f"perm family included the >=50 Hz cell (perm_obs={inf2['perm_obs']})"


if __name__ == "__main__":
    test_maxabs_corr_pairwise_nan()
    test_maxabs_corr_degenerate()
    test_maxabs_corr_matches_full_when_no_nan()
    test_vectorized_perm_matches_loop_statistic()
    test_block_perm_maxcorr_pvalue_behavior()
    test_select_biomarker_band_enforces_50hz_cap()
    test_band_inference_mad_rejection_and_50hz_perm_family()
    print("All pipeline_stats tests passed.")
