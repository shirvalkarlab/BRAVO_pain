"""The 2026-09-12 speed work changed HOW four things are computed and not WHAT they compute.

Each test here holds the new implementation against the old one -- copied in verbatim where the old
code was replaced, or reached through the switch that keeps it -- on constructed data that covers
the cases the live record does not: missing timestamps, an era label per epoch that is not a month,
a band whose rows are partly unusable. The live equality proofs are in
`_agent_bridge/_probe_tl/probe_so_screen_equal.py` and `probe_two_stage_compare.py`; these tests
are what keeps the equalities true after that day.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR


# =================================================================================================
# 1. the tile -> epoch lookup, integer nanoseconds against Timestamp objects
# =================================================================================================
def _old_epoch_for_times(times, epochs, *, t_start="t_start", t_end="t_end"):
    """The implementation that was replaced, verbatim: comparisons on Timestamp objects."""
    ep = epochs.reset_index(drop=True)
    starts = pd.to_datetime(ep[t_start], utc=True).to_numpy()
    ends = pd.to_datetime(ep[t_end], utc=True).to_numpy()
    tv = pd.to_datetime(pd.Series(times), utc=True).to_numpy()
    idx = np.searchsorted(starts, tv, side="right") - 1
    ok = (idx >= 0) & (idx < len(ep))
    within = np.zeros(len(tv), bool)
    within[ok] = tv[ok] < ends[np.clip(idx[ok], 0, len(ep) - 1)]
    return np.where(within, idx, -1)


def _epochs_with_gaps(n=6, start=1_760_000_000.0):
    s = pd.to_datetime(start, unit="s", utc=True)
    rows = []
    for i in range(n):
        rows.append(dict(t_start=s + pd.Timedelta(seconds=100 * i),
                         t_end=s + pd.Timedelta(seconds=100 * i + 80)))      # a 20 s gap after each
    return pd.DataFrame(rows)


def test_epoch_lookup_agrees_with_the_object_implementation_including_gaps_and_edges():
    ep = _epochs_with_gaps()
    base = 1_760_000_000.0
    # Inside, in a gap, exactly on a start (inside, half-open), exactly on an end (outside),
    # before the first epoch, after the last one.
    t = np.array([base + 10, base + 90, base + 100, base + 180, base - 5, base + 10_000])
    times = pd.to_datetime(t, unit="s", utc=True)
    new = EV._epoch_for_times(pd.Series(times), ep)
    old = _old_epoch_for_times(pd.Series(times), ep)
    assert new.tolist() == old.tolist() == [0, -1, 1, -1, -1, -1]


def test_epoch_lookup_treats_a_missing_time_as_outside_every_epoch_and_its_neighbours_right():
    """A missing time is outside every epoch, and the times around it are placed correctly.

    THE OLD IMPLEMENTATION GOT THE NEIGHBOUR WRONG. Searching Timestamp objects, numpy's
    `searchsorted` assumes the keys are sorted and reuses the previous key's search window; every
    comparison against a missing value is false, so after a missing key the window was carried
    over wrongly and the next valid time (here base+210, inside epoch 2) came back as epoch 5.
    The integer form has no such shortcut to mislead. The live record carries no missing tile
    times (304,488 checked on RCS08, 2026-09-12, 0 differing), so this is a case the new code
    handles correctly and the old code did not, not a case where the two were ever compared live.
    """
    ep = _epochs_with_gaps()
    base = 1_760_000_000.0
    times = pd.to_datetime(pd.Series([base + 10, np.nan, base + 210]), unit="s", utc=True)
    new = EV._epoch_for_times(times, ep)
    assert new.tolist() == [0, -1, 2]
    old = _old_epoch_for_times(times, ep)
    assert old[0] == 0 and old[1] == -1
    assert old[2] != 2, "numpy's sorted-key shortcut no longer misplaces the neighbour; revisit"


def test_epoch_lookup_with_a_missing_epoch_end_agrees_with_the_old_code():
    ep = _epochs_with_gaps()
    ep.loc[2, "t_end"] = pd.NaT
    base = 1_760_000_000.0
    times = pd.to_datetime(pd.Series([base + 210, base + 230, base + 310]), unit="s", utc=True)
    new = EV._epoch_for_times(times, ep)
    old = _old_epoch_for_times(times, ep)
    assert new.tolist() == old.tolist()
    # An epoch with no end cannot contain anything: `t < NaT` is false either way.
    assert new[0] == -1 and new[1] == -1 and new[2] == 3


def test_epoch_lookup_on_thousands_of_random_times_agrees_with_the_old_code():
    ep = _epochs_with_gaps(n=40)
    rng = np.random.default_rng(3)
    t = 1_760_000_000.0 + rng.uniform(-200, 4_500, 5_000)
    times = pd.to_datetime(t, unit="s", utc=True)
    new = EV._epoch_for_times(pd.Series(times), ep)
    old = _old_epoch_for_times(pd.Series(times), ep)
    assert np.array_equal(new, old)
    assert (new >= 0).sum() > 1000 and (new < 0).sum() > 100    # both outcomes exercised


# =================================================================================================
# 2. the era label, one per epoch then spread over the tiles, against one per tile row
# =================================================================================================
class _Aud:
    era_source = None


def test_era_per_epoch_then_indexed_equals_era_per_tile_row_for_months_and_for_a_column():
    ep = _epochs_with_gaps(n=5)
    # Shift epochs across a month boundary so the month strings differ.
    ep["t_start"] = ep["t_start"] + pd.to_timedelta(np.arange(5) * 20, unit="D")
    ep["visit"] = ["a", "b", "b", "c", "d"]
    j = np.array([0, 0, 1, 3, 4, 4, 2, 0])
    meta = ep.reset_index(drop=True).loc[j]
    for col in (None, "visit"):
        old = EV._derive_era(meta, col, _Aud())
        new = EV._derive_era(ep.reset_index(drop=True), col, _Aud())[j]
        assert old.tolist() == new.tolist()
    assert len(set(EV._derive_era(ep, None, _Aud()).tolist())) > 1


# =================================================================================================
# 3. the regression with the design matrix cached per cell, against the formula interface
# =================================================================================================
def _cell(n_per=40, seed=0, n_eras=3):
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.5, 2.5, 3.5], n_per)
    logp = np.log(100.0) - 0.4 * (amp - 1.5) + rng.normal(0, 0.25, amp.size)
    era = np.tile(np.array(["2025-11", "2025-12", "2026-01"][:n_eras]), int(np.ceil(amp.size / n_eras)))[:amp.size]
    clus = era
    return np.exp(logp), amp, era, clus


def _fields(r):
    return {f: getattr(r, f) for f in r.__dataclass_fields__}


def _same(x, y):
    if isinstance(x, float) and isinstance(y, float):
        return (np.isnan(x) and np.isnan(y)) or x == y
    if isinstance(x, tuple):
        return len(x) == len(y) and all(_same(u, v) for u, v in zip(x, y))
    return x == y


def _both_ways(power, amp, era, clus, **kw):
    saved = LR.USE_DESIGN_CACHE
    try:
        LR.USE_DESIGN_CACHE = False
        a = LR.assess_response(power, amp, era=era, cluster=clus, **kw)
        LR.USE_DESIGN_CACHE = True
        LR._DESIGN_CACHE.clear()
        b = LR.assess_response(power, amp, era=era, cluster=clus, **kw)
        c = LR.assess_response(power, amp, era=era, cluster=clus, **kw)   # served from the cache
    finally:
        LR.USE_DESIGN_CACHE = saved
    return a, b, c


def test_cached_design_matrix_gives_every_field_the_formula_interface_gives():
    p, a, era, clus = _cell()
    old, new, again = _both_ways(p, a, era, clus)
    assert old.responds is not None and np.isfinite(old.slope_p)
    for f, v in _fields(old).items():
        assert _same(v, getattr(new, f)), f
        assert _same(v, getattr(again, f)), f
    assert len(LR._DESIGN_CACHE) == 2          # "amp" and "amp + C(era)" for this cell


def test_eighteen_bands_of_one_cell_share_one_design_matrix_and_still_agree():
    _, a, era, clus = _cell()
    rng = np.random.default_rng(7)
    LR._DESIGN_CACHE.clear()
    for k in range(18):
        p = np.exp(np.log(120.0 + k) - 0.3 * (a - 1.5) + rng.normal(0, 0.2, a.size))
        old, new, _ = _both_ways(p, a, era, clus)
        for f, v in _fields(old).items():
            assert _same(v, getattr(new, f)), (k, f)
    assert len(LR._DESIGN_CACHE) == 2


def test_a_band_with_unusable_rows_agrees_too_and_keys_the_cache_on_the_surviving_rows():
    p, a, era, clus = _cell()
    p = p.copy()
    p[::7] = np.nan                       # non-finite power rows are dropped inside assess_response
    p[3] = -1.0
    old, new, _ = _both_ways(p, a, era, clus)
    for f, v in _fields(old).items():
        assert _same(v, getattr(new, f)), f
    assert any("dropped" in n for n in new.notes)


def test_no_era_and_no_cluster_paths_agree_with_the_formula_interface():
    p, a, era, clus = _cell()
    old, new, _ = _both_ways(p, a, None, None)
    for f, v in _fields(old).items():
        assert _same(v, getattr(new, f)), f
    assert any("NOT cluster-robust" in n for n in new.notes)
    assert any("era NOT blocked" in n for n in new.notes)


def test_the_cache_is_bounded():
    LR._DESIGN_CACHE.clear()
    for seed in range(LR._DESIGN_CACHE_MAX + 5):
        p, a, era, clus = _cell(seed=seed)
        a = a + 0.001 * seed                # a different cell each time
        LR.assess_response(p, a, era=era, cluster=clus)
    assert len(LR._DESIGN_CACHE) <= LR._DESIGN_CACHE_MAX


# =================================================================================================
# 4. build_all with the per-channel preparation shared, against build_evidence cell by cell
# =================================================================================================
def test_build_all_with_shared_channel_preparation_equals_cell_by_cell_building():
    from StimOptimizer.tests.test_lfp_evidence import _cache_entry, _tile_values, _epochs, T0, CENTERS
    # Two channels, two epochs at two currents, a few device readings, and one bad tile.
    t = T0 + np.arange(30) * 10.0
    cache = {}
    for k, ch in enumerate(("ZERO_TWO_LEFT", "ONE_THREE_RIGHT")):
        ok = np.ones(30, bool); ok[4 + k] = False
        cache[ch] = _cache_entry(td_t=t, td_lsb=_tile_values(30) * (1 + k), td_ok=ok)
    psd = EV.frame_from_lsb_cache(cache)
    ep = _epochs()
    ev_all, audit_all = EV.build_all(psd, ep, era_col="visit")
    assert len(ev_all) >= 2
    rows = []
    for ch in sorted(psd["channel"].astype(str).unique()):
        for h in ("Left", "Right"):
            e, a = EV.build_evidence(psd, ep, channel=ch, hemisphere=h, rate_hz=55.0, era_col="visit")
            rows.append({**a.__dict__, "usable": e is not None, "n_amplitudes": len(a.amplitudes)})
            if e is None:
                assert (ch, h, 55.0) not in ev_all
                continue
            got = ev_all[(ch, h, 55.0)]
            assert np.array_equal(got.amplitude_mA, e.amplitude_mA)
            assert np.array_equal(got.era, e.era) and np.array_equal(got.cluster, e.cluster)
            assert list(got.band_power) == list(e.band_power)
            for key in e.band_power:
                assert np.array_equal(got.band_power[key], e.band_power[key], equal_nan=True)
    single = pd.DataFrame(rows)
    assert list(single.columns) == list(audit_all.columns)
    assert single.astype(str).values.tolist() == audit_all.astype(str).values.tolist()
