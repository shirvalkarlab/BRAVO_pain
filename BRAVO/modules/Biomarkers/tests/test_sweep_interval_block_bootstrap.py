"""B6 of the 2026-09-15 review (decision 183): the interval on a grid cell's headline statistic is a
BLOCK bootstrap of the pain reports, sized by the same block length the p-value's shuffle uses.

Until this, the p-value shuffled whole blocks of reports (autocorrelation preserved) while the
interval resampled single reports as if independent -- two answers about one cell resting on
opposite assumptions, and the interval narrower than the evidence supports (decision 111 measured
two ratings an hour apart differ by 0.37 points: close to one observation, not two).
"""
import numpy as np

try:
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines import stats_utils as SU


def _ar1_grid(rho, n=160, seed=3):
    """One band, two lengths: band power and pain share a slow AR(1) drift, so consecutive reports
    are near-duplicates when `rho` is high and independent when `rho` is 0."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = rho * z[i - 1] + rng.normal(0, np.sqrt(1 - rho * rho))
    pain = np.clip(np.round(5 + 2 * z + rng.normal(0, 0.8, n)), 0, 10)
    x = 100 + 20 * z + rng.normal(0, 8, n)
    x2 = 100 + 20 * z + rng.normal(0, 8, n)
    power = {1.0: x[:, None], 5.0: x2[:, None]}
    return power, pain, [12.5]


def _widths(sw):
    r = sw["best_correlation_rows"][0]
    a = sw["best_auc_rows"][0]
    return (r["pearson_r_high"] - r["pearson_r_low"], a["auc_high"] - a["auc_low"],
            r["interval_block_length"], a["interval_block_length"])


def test_block_bootstrap_picks_are_the_plain_draw_at_block_one_and_whole_blocks_above():
    rng1, rng2 = np.random.default_rng(7), np.random.default_rng(7)
    plain = rng1.integers(0, 50, size=(4, 50))
    picks = SU.block_bootstrap_picks(50, 1, 4, rng2)
    assert np.array_equal(plain, picks), "block 1 must be the identical i.i.d. draw"
    picks = SU.block_bootstrap_picks(50, 5, 4, np.random.default_rng(1))
    assert picks.shape == (4, 50)
    # every run of five is consecutive modulo n
    for row in picks:
        for b in range(0, 50, 5):
            seg = row[b:b + 5]
            assert np.all((seg[1:] - seg[:-1]) % 50 == 1), seg


def test_the_interval_widens_under_strong_autocorrelation_and_reports_its_block_length():
    power, pain, centers = _ar1_grid(rho=0.92)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=400)
    w_r, w_a, b_r, b_a = _widths(sw)
    assert b_r > 1 and b_a > 1, (b_r, b_a)
    # the plain i.i.d. interval, for the comparison only
    A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = False
    try:
        sw0 = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=400)
    finally:
        A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = True
    w_r0, w_a0, b_r0, b_a0 = _widths(sw0)
    assert b_r0 == 1 and b_a0 == 1
    assert w_r > w_r0 * 1.15, (w_r, w_r0)
    assert w_a > w_a0 * 1.15, (w_a, w_a0)
    print(f"OK block interval r {w_r:.3f} vs iid {w_r0:.3f} (block {b_r}); "
          f"auc {w_a:.3f} vs {w_a0:.3f} (block {b_a})")


def test_with_no_autocorrelation_the_interval_is_the_draw_it_always_was():
    power, pain, centers = _ar1_grid(rho=0.0, seed=11)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=300)
    A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = False
    try:
        sw0 = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=50, n_boot=300)
    finally:
        A.BAND_SWEEP_INTERVAL_BLOCK_BOOTSTRAP = True
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r1, r0 in zip(sw[key], sw0[key]):
            assert r1["interval_block_length"] == 1
            for f in ("pearson_r_low", "pearson_r_high", "auc_low", "auc_high"):
                if f in r1:
                    assert r1[f] == r0[f], (f, r1[f], r0[f])
    print("OK block length 1 reproduces the i.i.d. interval bit for bit")
