"""Each heat-map cell's correlation, split by where each pain report's band power came from (handoff
item P-19; the PI's ruling of 2026-09-25: text only, no separate heat map).

On the Biomarkers page's two heat maps each pain report takes its band power from ONE of two
sources: TD, the time-domain recording cut into 3 s pieces (whenever any of it falls inside the
match window), or PSD, the device's own 30 s snapshots (only when no TD does). The page counted
the PSD-read reports per cell (decision 106) but never showed each source's own correlation, and on
RCS08 the two can disagree where the pooled cell reads near zero (the P-19 analysis:
L 1-3+ 24.5 Hz at 30 s, TD -0.05 on 76 reports, PSD -0.37 on 86, the cell -0.04).

Pinned on the values:
  * every cell of the grid carries the same Pearson correlation computed on the TD-read reports
    alone and on the PSD-read reports alone, from the SAME band-power matrix the cell used (after
    the outlier rule), so the two counts add up to the cell's own count;
  * each has the cell's own interval method (whole reports resampled in blocks sized by the
    p-value's rule) from its own generator, reproducible from the seed and the column;
  * a source with fewer than the minimum reports carries its count and no interval;
  * asking for the split moves nothing else: the plain grid, every headline row, its interval, its
    q and its verdict are the same with the flags supplied or withheld;
  * without the per-report flag the split says it could not be made, rather than printing zeros.

Run inside the container:
    python3 -W ignore modules/Biomarkers/tests/test_correlation_by_recording_source.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines.stats_utils import block_bootstrap_picks
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines.stats_utils import block_bootstrap_picks

CENTERS = [12.5, 20.5, 24.5]
LENGTHS = (1.0, 5.0, 30.0)


def _grid(n=140, n_psd=60, seed=7):
    """Two groups of reports: TD-read ones where band power falls with pain, PSD-read ones where
    it rises, so a split that mixed them up could not reproduce either group's value."""
    rng = np.random.default_rng(seed)
    pain = np.clip(np.round(5 + rng.normal(0, 2, n)), 0, 10)
    flags = np.zeros(n, dtype=bool)
    flags[rng.choice(n, n_psd, replace=False)] = True
    sign = np.where(flags, +1.0, -1.0)
    power = {}
    for L in LENGTHS:
        x = 200 + 6 * sign[:, None] * pain[:, None] + rng.normal(0, 12, (n, len(CENTERS)))
        x[rng.random(x.shape) < 0.08] = np.nan
        power[L] = x
    # One absurd value on a PSD-read report: the outlier rule (5 MAD here, no ceiling table for a
    # constructed channel) drops it, and the split must use the matrix AFTER that drop.
    first_psd = int(np.flatnonzero(flags)[0])
    power[5.0][first_psd, 1] = 1e7
    return power, pain, [bool(v) for v in flags]


def _sweep(flags, **kw):
    power, pain, _ = _grid(**kw)
    return A.band_time_sweep_from_power(power, pain, center_freqs_hz=CENTERS, n_perm=60,
                                        n_boot=200, seed=3, from_device_spectrum=flags)


def _r(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[m], y[m])[0, 1]), int(m.sum())


def test_every_cell_carries_the_td_and_psd_correlations_of_its_own_reports():
    power, pain, flags = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=CENTERS, n_perm=60,
                                      n_boot=200, seed=3, from_device_spectrum=flags)
    split = sw.get("correlation_by_recording_source")
    assert split is not None, sorted(sw)
    assert split["available"] is True, split
    f = np.asarray(flags)
    # The matrix the cell used, after the outlier rule: rebuilt exactly as the sweep does it.
    X = np.stack([np.asarray(power[L], dtype=float) for L in LENGTHS])
    T, P, C = X.shape
    drop = A.mad_outlier_columns(X.copy(), n_mad=A.OUTLIER_N_MAD, scale=A.OUTLIER_SCALE)
    assert drop.any(), "the planted outlier must be dropped by the plain rule"
    X[drop] = np.nan
    n_grid = np.asarray(sw["n_grid"])
    for t in range(T):
        for c in range(C):
            r_td, n_td = _r(X[t, ~f, c], pain[~f])
            r_psd, n_psd = _r(X[t, f, c], pain[f])
            assert split["td"]["n_grid"][t][c] == n_td
            assert split["psd"]["n_grid"][t][c] == n_psd
            # the two sources together are exactly the cell's own reports
            assert n_td + n_psd == int(n_grid[t, c]), (t, c)
            assert abs(split["td"]["r_grid"][t][c] - r_td) < 1e-12, (t, c)
            assert abs(split["psd"]["r_grid"][t][c] - r_psd) < 1e-12, (t, c)
            assert split["td"]["r_grid"][t][c] < 0 < split["psd"]["r_grid"][t][c], (t, c)
    assert split["min_reports"] == A.SOURCE_SPLIT_MIN_REPORTS == 8
    print(f"OK {T * C} cells split; e.g. TD {split['td']['r_grid'][2][2]:+.3f} "
          f"(n {split['td']['n_grid'][2][2]}), PSD {split['psd']['r_grid'][2][2]:+.3f} "
          f"(n {split['psd']['n_grid'][2][2]})")


def test_each_source_carries_the_cells_own_interval_method_reproducibly():
    power, pain, flags = _grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=CENTERS, n_perm=60,
                                      n_boot=200, seed=3, from_device_spectrum=flags)
    split = sw["correlation_by_recording_source"]
    X = np.stack([np.asarray(power[L], dtype=float) for L in LENGTHS])
    drop = A.mad_outlier_columns(X.copy(), n_mad=A.OUTLIER_N_MAD, scale=A.OUTLIER_SCALE)
    X[drop] = np.nan
    f = np.asarray(flags)
    t, c = 2, 1
    # A fresh generator for each source of each cell, seeded from the sweep's seed plus the band
    # column; whole reports in blocks sized by the p-value's rule on that source's own ratings.
    for key, grp in (("td", ~f), ("psd", f)):
        rng = np.random.default_rng(3 + c)
        x = X[t, :, c]
        m = grp & np.isfinite(x) & np.isfinite(pain)
        idx = np.flatnonzero(m)
        blk = A._interval_block_length(pain[idx])
        picks = block_bootstrap_picks(idx.size, blk, 200, rng)
        xb = x[idx][picks]; yb = pain[idx][picks]
        xb = xb - xb.mean(axis=1, keepdims=True); yb = yb - yb.mean(axis=1, keepdims=True)
        rb = (xb * yb).sum(axis=1) / np.sqrt((xb * xb).sum(axis=1) * (yb * yb).sum(axis=1))
        lo, hi, _ = A._percentile_interval(rb)
        assert abs(split[key]["r_low_grid"][t][c] - lo) < 1e-12, (key, split[key]["r_low_grid"][t][c], lo)
        assert abs(split[key]["r_high_grid"][t][c] - hi) < 1e-12, (key, split[key]["r_high_grid"][t][c], hi)
        assert split[key]["r_low_grid"][t][c] <= split[key]["r_grid"][t][c] <= split[key]["r_high_grid"][t][c]


def test_a_source_with_too_few_reports_carries_its_count_and_no_interval():
    power, pain, flags = _grid(n_psd=5)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=CENTERS, n_perm=60,
                                      n_boot=200, seed=3, from_device_spectrum=flags)
    psd = sw["correlation_by_recording_source"]["psd"]
    for t in range(len(LENGTHS)):
        for c in range(len(CENTERS)):
            assert psd["n_grid"][t][c] < 8
            assert psd["r_low_grid"][t][c] is None and psd["r_high_grid"][t][c] is None
    td = sw["correlation_by_recording_source"]["td"]
    assert all(v is not None for row in td["r_low_grid"] for v in row)


def test_asking_for_the_split_moves_no_plain_value_selection_q_or_verdict():
    _, _, flags = _grid()
    with_flags = _sweep(flags)
    without = _sweep(None)
    assert with_flags["correlation_grid"] == without["correlation_grid"]
    assert with_flags["auc_grid"] == without["auc_grid"]
    assert with_flags["p_grid"] == without["p_grid"]
    # Every headline field except the snapshot counts the flag feeds (decision 106).
    skip = {"n_pain_reports_from_device_spectrum", "device_spectrum_share"}
    for kind in ("best_correlation_rows", "best_auc_rows"):
        for a, b in zip(with_flags[kind], without[kind]):
            assert {k: v for k, v in a.items() if k not in skip} == \
                   {k: v for k, v in b.items() if k not in skip}, kind


def test_without_the_per_report_flag_the_split_says_it_could_not_be_made():
    sw = _sweep(None)
    split = sw["correlation_by_recording_source"]
    assert split["available"] is False
    assert "which source" in split["reason"]
    assert "td" not in split and "psd" not in split
    blank = A._sweep_blank("nothing")
    assert blank["correlation_by_recording_source"]["available"] is False


def test_the_grid_rule_version_moved_so_no_stored_grid_without_the_split_is_served():
    try:
        from modules.Biomarkers import bravo_service as BS
    except ImportError:                                    # pragma: no cover - host spelling
        from Biomarkers import bravo_service as BS
    assert int(BS._BAND_SWEEP_RULE_VERSION.split("_")[0][1:]) >= 23, BS._BAND_SWEEP_RULE_VERSION


if __name__ == "__main__":
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            print("PASS", _n)
