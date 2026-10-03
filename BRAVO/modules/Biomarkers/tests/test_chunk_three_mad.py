"""The 3-second chunks are judged by 3 MAD (the PI, 2026-10-03), everything else stays at 5 MAD.

Before, a chunk was dropped at a band when it sat above that contact's historical 99.5th-percentile
ceiling. Now it is dropped when it is more than 3 median absolute deviations from that contact's own
median at that band (the project's MAD rule, `stats_utils.mad_outlier_flags`: raw values, strict
inequality, no rescaling, nothing removed when the MAD is zero), on either side, before averaging,
with the next clean chunk taken in its place as before.
"""
import numpy as np

from ..routines import analytics as A, availability as av, stats_utils as SU
from .test_chunk_ceiling_exclusion import CENTERS, T0, _cache, _row


def test_the_chunk_rule_is_three_mad_and_the_plate_rule_stays_five():
    assert A.CHUNK_N_MAD == 3.0
    assert SU.MAD_N_DEFAULT == 5.0 and A.OUTLIER_N_MAD == 5.0


def test_bounds_are_the_projects_mad_rule_per_band():
    rng = np.random.default_rng(0)
    lsb = [_row(float(v)) for v in rng.gamma(2.0, 100.0, size=200)]
    cache = _cache([T0 + 3.0 * k for k in range(200)], lsb)
    lo, hi = A.chunk_mad_bounds(cache, CENTERS)
    for j in range(len(CENTERS)):
        col = np.array([r[j] for r in lsb], float)
        flags, info = SU.mad_outlier_flags(col, n_mad=3.0)
        kept = (col >= lo[j]) & (col <= hi[j])
        assert np.array_equal(~kept, flags), j          # the same chunks as the project's own rule
        assert np.isclose(hi[j], info["median"] + 3.0 * info["mad"])


def test_a_chunk_far_below_the_median_is_now_excluded_too():
    td_t = [T0 + 3.0 * k for k in range(30)]
    lsb = [_row(100.0 + (k % 3)) for k in range(30)]
    lsb[0] = _row(-500.0)                               # far below; no ceiling would ever catch it
    cache = _cache(td_t, lsb)
    lo, hi = A.chunk_mad_bounds(cache, CENTERS)
    _p, info, _s = av.live_lsb_band_medians_by_length(
        [T0 + 1.0], cache, tol_s=600.0, lengths_s=[3.0], centers_hz=CENTERS,
        band_ceilings=list(hi), band_floors=list(lo), allow_window_reuse=True)
    assert info["n_chunk_band_values_excluded"] >= len(CENTERS)


def test_zero_mad_excludes_nothing():
    cache = _cache([T0 + 3.0 * k for k in range(20)], [_row(50.0) for _ in range(20)])
    lo, hi = A.chunk_mad_bounds(cache, CENTERS)
    assert np.all(np.isinf(lo)) and np.all(np.isinf(hi))


def test_the_sweep_route_uses_the_three_mad_bounds():
    import inspect
    from .. import bravo_service as BS
    src = inspect.getsource(BS._band_time_sweep_power_by_seconds)
    assert "chunk_mad_bounds(" in src and "band_floors=" in src
