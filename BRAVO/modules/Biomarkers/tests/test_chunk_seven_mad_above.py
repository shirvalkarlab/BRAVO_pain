"""Single 3-second chunks: dropped only when more than 7 MAD ABOVE the median (the PI, 2026-10-03,
decision 410, replacing decision 408's 3 MAD on both sides). Every other outlier rule stays at 5 MAD.

Per contact and band, a chunk's value is dropped before averaging when it sits more than 7 median
absolute deviations above that contact's own median at that band (median and MAD as in the project's
rule, `stats_utils.mad_outlier_flags`: raw values, strict inequality, no rescaling, nothing removed
when the MAD is zero), with the next clean chunk taken in its place. A low chunk is never dropped.
The rule applies to every contact of every participant, not only to RCS08's six.
"""
import numpy as np

from ..routines import analytics as A, availability as av, stats_utils as SU
from .test_chunk_ceiling_exclusion import CENTERS, T0, _cache, _row


def test_the_chunk_rule_is_seven_mad_and_the_plate_rule_stays_five():
    assert A.CHUNK_N_MAD == 7.0
    assert SU.MAD_N_DEFAULT == 5.0 and A.OUTLIER_N_MAD == 5.0


def test_the_bound_is_median_plus_seven_mad_and_drops_only_the_high_side():
    rng = np.random.default_rng(0)
    lsb = [_row(float(v)) for v in rng.lognormal(5.0, 1.0, size=400)]
    cache = _cache([T0 + 3.0 * k for k in range(400)], lsb)
    hi = A.chunk_upper_bounds(cache, CENTERS)
    for j in range(len(CENTERS)):
        col = np.array([r[j] for r in lsb], float)
        flags, info = SU.mad_outlier_flags(col, n_mad=7.0)
        assert np.isclose(hi[j], info["median"] + 7.0 * info["mad"])
        # exactly the project's 7-MAD flags on the high side, none on the low side
        assert np.array_equal(col > hi[j], flags & (col > info["median"]))
        assert (col > hi[j]).sum() > 0, "this draw has values above the bound"


def test_a_chunk_far_below_the_median_is_kept():
    td_t = [T0 + 3.0 * k for k in range(30)]
    lsb = [_row(100.0 + (k % 3)) for k in range(30)]
    lsb[0] = _row(-500.0)                               # far below the median
    cache = _cache(td_t, lsb)
    hi = A.chunk_upper_bounds(cache, CENTERS)
    _p, info, _s = av.live_lsb_band_medians_by_length(
        [T0 + 1.0], cache, tol_s=600.0, lengths_s=[3.0], centers_hz=CENTERS,
        band_ceilings=list(hi), allow_window_reuse=True)
    assert info["n_chunk_band_values_excluded"] == 0


def test_a_chunk_far_above_the_median_is_dropped_and_replaced():
    td_t = [T0 + 3.0 * k for k in range(30)]
    lsb = [_row(100.0 + (k % 3)) for k in range(30)]
    lsb[0] = _row(5000.0)                               # the chunk nearest the report, far above
    cache = _cache(td_t, lsb)
    hi = A.chunk_upper_bounds(cache, CENTERS)
    power, info, _s = av.live_lsb_band_medians_by_length(
        [T0 + 1.0], cache, tol_s=600.0, lengths_s=[3.0], centers_hz=CENTERS,
        band_ceilings=list(hi), allow_window_reuse=True)
    assert info["n_chunk_band_values_excluded"] == len(CENTERS)
    assert np.all(power[3.0][0] < 200.0), power[3.0][0]   # the next clean chunk, not the spike


def test_zero_mad_drops_nothing():
    cache = _cache([T0 + 3.0 * k for k in range(20)], [_row(50.0) for _ in range(20)])
    assert np.all(np.isinf(A.chunk_upper_bounds(cache, CENTERS)))


def test_every_participant_and_contact_takes_the_chunk_rule():
    from .test_device_spectrum_mark import _sweep_power
    for uid in ("2e3c75c00d7f4f37b53a048d195f11da", "another-participant", None):
        for channel in ("ZERO_THREE_RIGHT", "A_CONTACT_WITH_NO_CEILING_TABLE"):
            *_rest, chunk_excl, _flags = _sweep_power(channel, participant_uid=uid)
            assert isinstance(chunk_excl, dict), (uid, channel)


def test_the_sweep_route_reads_the_seven_mad_bound_and_no_ceiling_table():
    import inspect
    from .. import bravo_service as BS
    src = inspect.getsource(BS._band_time_sweep_power_by_seconds)
    assert "chunk_upper_bounds(" in src
    assert "band_sweep_ceiling_table(" not in src and "live_lsb_spectrum_match(" not in src.split('"""')[2]


# ---- PSD snapshots get their own bound (the PI, 2026-10-03, decision 411) ----------------------
# A rating with no voltage trace in its window is answered from the device's own 30 s PSD
# snapshots. Until 411 those were judged against the bound built from the TD chunks, a different
# measurement on its own scale; now each family is judged against median + 7 MAD of its own values.

def _psd_cache(psd_vals):
    """One TD chunk far from the report (so the report is served from PSD) and PSD snapshots."""
    td_t = [T0 + 50_000.0 + 3.0 * k for k in range(20)]
    td_lsb = [_row(100.0 + (k % 3)) for k in range(20)]
    psd_t = [T0 + 30.0 * k for k in range(len(psd_vals))]
    return _cache(td_t, td_lsb, psd_t=psd_t, psd_lsb=[_row(v) for v in psd_vals])


def test_the_psd_bound_comes_from_the_psd_snapshots():
    vals = [1000.0 + 10.0 * (k % 5) for k in range(20)]
    cache = _psd_cache(vals)
    hi_psd = A.chunk_upper_bounds(cache, CENTERS, family="psd")
    hi_td = A.chunk_upper_bounds(cache, CENTERS)
    for j in range(len(CENTERS)):
        col = np.array([v + j for v in vals])
        _f, info = SU.mad_outlier_flags(col, n_mad=7.0)
        assert np.isclose(hi_psd[j], info["median"] + 7.0 * info["mad"])
        assert hi_td[j] < 200.0 < hi_psd[j]            # two different scales, two bounds


def test_psd_snapshots_on_their_own_scale_are_kept_and_a_psd_spike_is_dropped():
    vals = [1000.0 + 10.0 * (k % 5) for k in range(20)]
    vals[0] = 90_000.0                                 # the snapshot nearest the report
    cache = _psd_cache(vals)
    power, info, _s = av.live_lsb_band_medians_by_length(
        [T0 + 1.0], cache, tol_s=600.0, lengths_s=[30.0], centers_hz=CENTERS,
        band_ceilings=list(A.chunk_upper_bounds(cache, CENTERS)),
        psd_band_ceilings=list(A.chunk_upper_bounds(cache, CENTERS, family="psd")),
        allow_window_reuse=True)
    assert info["n_psd_band_values_excluded"] == len(CENTERS)   # the spike, at every band
    row = power[30.0][0]
    assert np.all((row > 900.0) & (row < 1100.0)), row          # the next snapshot, not dropped


def test_the_sweep_passes_the_psd_bound():
    import inspect
    from .. import bravo_service as BS
    src = inspect.getsource(BS._band_time_sweep_power_by_seconds).split('"""')[2]
    assert 'family="psd"' in src and "psd_band_ceilings=" in src
