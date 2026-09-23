"""The heat-map cell carries the EFFECTIVE count of independent ratings beside the raw count (panel A
item 4, 2026-09-22).

WHY. Pain ratings filed close together are close to one observation, not two (decision 111 measured
two ratings an hour apart differ by 0.37 points), and band power drifts slowly too. A cell that says
"59 reports" when the two series' own persistence makes them worth about 49 invites a reader to
trust its correlation more than the record allows. The count already used for this elsewhere is
`stats_utils.effective_n` (the lag-1 Bartlett approximation); no count of this kind existed on the
sweep's rows under any name. Measured by the panel on the live record: the L 1-3+ 24.5 Hz 60 s cell,
59 reports, effective 49.0 (lag-1 autocorrelation of power 0.43, of pain 0.22).

Pinned on the values: the row's number is exactly `effective_n` of the pairs the cell correlated;
it is at most the raw count; it falls well below the raw count when both series persist; it equals
the raw count (to rounding) when neither does. Nothing reads it to decide anything.

Run inside the container:
    python3 -W ignore modules/Biomarkers/tests/test_sweep_effective_count.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import analytics as A
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                        # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A
    from Biomarkers.routines import stats_utils as SU


def _grid(rho, n=160, seed=3):
    """One band at one length: band power and pain share a slow AR(1) drift of persistence `rho`."""
    rng = np.random.default_rng(seed)
    z = np.zeros(n)
    for i in range(1, n):
        z[i] = rho * z[i - 1] + rng.normal(0, np.sqrt(1 - rho * rho))
    pain = np.clip(np.round(5 + 2 * z + rng.normal(0, 0.8, n)), 0, 10)
    x = 100 + 20 * z + rng.normal(0, 8, n)
    return {5.0: x[:, None]}, pain, [12.5], x, pain


def test_the_row_carries_exactly_the_effective_count_of_the_pairs_it_correlated():
    power, pain, centers, x, y = _grid(rho=0.9)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20, n_boot=50)
    row = sw["best_correlation_rows"][0]
    m = np.isfinite(x) & np.isfinite(y)
    want = SU.effective_n(x[m], y[m])
    assert "n_pain_reports_effective" in row, sorted(row)
    assert abs(row["n_pain_reports_effective"] - round(want, 1)) < 1e-9, (row["n_pain_reports_effective"], want)
    assert row["n_pain_reports_effective"] <= row["n_pain_reports"]
    print(f"OK {row['n_pain_reports']} reports, effective {row['n_pain_reports_effective']}")


def test_persistence_in_both_series_lowers_the_effective_count_well_below_the_raw_count():
    power, pain, centers, _x, _y = _grid(rho=0.9)
    row = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20,
                                       n_boot=50)["best_correlation_rows"][0]
    assert row["n_pain_reports_effective"] < 0.5 * row["n_pain_reports"], row


def test_no_persistence_leaves_the_effective_count_close_to_the_raw_count():
    power, pain, centers, _x, _y = _grid(rho=0.0, seed=11)
    row = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=20,
                                       n_boot=50)["best_correlation_rows"][0]
    assert row["n_pain_reports_effective"] > 0.85 * row["n_pain_reports"], row


if __name__ == "__main__":
    for fn in (test_the_row_carries_exactly_the_effective_count_of_the_pairs_it_correlated,
               test_persistence_in_both_series_lowers_the_effective_count_well_below_the_raw_count,
               test_no_persistence_leaves_the_effective_count_close_to_the_raw_count):
        fn()
    print("All effective-count tests passed.")
