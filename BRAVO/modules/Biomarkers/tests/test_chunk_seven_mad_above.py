"""Single 3-second chunks: dropped only when more than 7 MAD ABOVE the median (the PI, 2026-10-03,
decision 410, replacing decision 408's 3 MAD on both sides). Every other outlier rule stays at 5 MAD.

Per contact and band, a chunk's value is dropped before averaging when it sits more than 7 median
absolute deviations above that contact's own median at that band (median and MAD as in the project's
rule, `stats_utils.mad_outlier_flags`: raw values, strict inequality, no rescaling, nothing removed
when the MAD is zero), with the next clean chunk taken in its place. A low chunk is never dropped.
The rule applies to every contact of every participant, not only to RCS08's six.

Merged here 2026-10-05: test_chunk_ceiling_exclusion.py, test_ceilings_keyed_on_participant.py.
"""
import numpy as np
from ..routines import analytics as A, availability as av, stats_utils as SU


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


# --------------------------------------------------------------------------------------------------
# merged from test_chunk_ceiling_exclusion.py
# Dropping a contaminated 3 s piece BEFORE the pieces are averaged, and backfilling behind it.
#
# `availability.live_lsb_band_medians_by_length` exists because the historical ceilings are
# percentiles of INDIVIDUAL 3 s pieces, so comparing them against a cell that already averaged up to
# a hundred pieces compares a threshold against the wrong distribution (PI, 2026-09-09).
#
# The first test is the load-bearing one: given ceilings that exclude nothing, the new function must
# reproduce `live_lsb_spectrum_match` -- the real, already-trusted matcher, imported and called, not
# a hand-written expectation -- value for value, across both reuse modes, all three match directions
# and every length of signal. That is what proves the two paths agree about which piece of recording
# belongs to which pain report, so any difference the grid shows is the exclusion and nothing else.
#
# The rest pin the three behaviours that are genuinely new: a piece is excluded only in the band it
# is contaminated in, a dropped piece is replaced by the next closest clean one rather than simply
# leaving the cell short, and a rating with no voltage trace still falls back to the device's own
# spectrum.


from ..routines import availability as av
CENTERS = [8.5, 12.5, 16.5, 20.5]
TILE_S = 3.0
T0 = 1_700_000_000.0
NO_CEILING = [np.inf] * len(CENTERS)


def _row(base, holes=()):
    return [None if j in holes else float(base + j) for j in range(len(CENTERS))]


def _cache(td_t, td_lsb, td_ok=None, psd_t=(), psd_lsb=()):
    nC = len(CENTERS)
    td_t = [float(t) for t in td_t]
    ok = [True] * len(td_t) if td_ok is None else [bool(o) for o in td_ok]
    return {"channel": "TEST_CONTACT", "centers_hz": [float(c) for c in CENTERS],
            "window_s": TILE_S, "band_half_hz": 2.5,
            "td": {"t": td_t, "lsb": td_lsb, "saturated": [False] * len(td_t),
                   "source": ["constructed"] * len(td_t),
                   "n_finite_s": [TILE_S] * len(td_t), "ok": ok},
            "psd": {"t": [float(t) for t in psd_t], "lsb": list(psd_lsb),
                    "calibrated": [[True] * nC] * len(psd_t),
                    "source": ["constructed"] * len(psd_t)},
            "n_td_windows": len(td_t), "n_psd_windows": len(psd_t)}


def _busy_cache(rng):
    """Forty pieces of recording on a 3 s grid plus four device-spectrum windows, with holes, a
    failed quality gate and a stretch of recording no rating is near."""
    td_t, td_lsb, td_ok = [], [], []
    for k in range(40):
        t = T0 + 1.5 + 3.0 * k + (0.0 if k % 7 else 600.0)     # one piece pushed far away
        holes = (k % len(CENTERS),) if k % 5 == 0 else ()
        td_t.append(t)
        td_lsb.append(_row(float(rng.integers(5, 900)), holes=holes))
        td_ok.append(k % 11 != 0)                               # some pieces fail the gate
    psd_t = [T0 + 5000.0, T0 + 5002.0, T0 + 5100.0, T0 + 9000.0]
    psd_lsb = [_row(60), _row(61, holes=(0,)), _row(62), [None] * len(CENTERS)]
    return _cache(td_t, td_lsb, td_ok, psd_t, psd_lsb)


def test_with_no_ceiling_it_reproduces_the_established_matcher_exactly():
    """Ceilings that exclude nothing -> the same numbers `live_lsb_spectrum_match` already gives,
    FOR EVERY RATING SERVED FROM THE VOLTAGE TRACE.

    Both paths are called on the identical constructed recordings, for every combination of reuse
    mode, match direction and length of signal, and compared value by value including which values
    are absent. Any disagreement here would mean the two disagree about the MATCHING itself, which
    is the one thing the ceiling change was not supposed to touch.

    Ratings served from the device's own FFT snapshots are compared on the matching summary only,
    not value for value: since 2026-09-10 (decision 121) this path counts snapshots by the length
    of signal (30 s each) where the established matcher takes the median of every snapshot in the
    window, so their values differ by design. That rule has its own tests below and in
    `test_device_spectrum_mark.py`.
    """
    rng = np.random.default_rng(20260909)
    cache = _busy_cache(rng)
    pro = [T0 + 20.0, T0 + 61.0, T0 + 95.5, T0 + 5001.0, T0 + 40000.0]
    lengths = [1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
    compared = 0
    for reuse in (False, True):
        for direction in ("nearest", "prior", "pro_first"):
            got, info, stats = av.live_lsb_band_medians_by_length(
                pro, cache, tol_s=1800.0, lengths_s=lengths, centers_hz=CENTERS,
                band_ceilings=NO_CEILING, allow_window_reuse=reuse, match_direction=direction)
            assert info["n_chunk_band_values_excluded"] == 0
            from_psd = list(info["from_device_spectrum"])
            for s in lengths:
                recs, _stats = av.live_lsb_spectrum_match(
                    pro, cache, tol_s=1800.0, td_quantity_s=s, allow_window_reuse=reuse,
                    match_direction=direction)
                for i, rec in enumerate(recs):
                    if from_psd[i]:
                        compared += len(CENTERS)
                        continue
                    for j in range(len(CENTERS)):
                        want, mine = rec["lsb"][j], got[float(s)][i, j]
                        if want is None:
                            assert not np.isfinite(mine), (reuse, direction, s, i, j, mine)
                        else:
                            assert np.isclose(mine, float(want), rtol=0, atol=0), (
                                reuse, direction, s, i, j, mine, want)
                        compared += 1
                # The per-length matching summary the page shows must survive this path too. It
                # did not in the first build -- 420 of the response's fields simply vanished,
                # found only by counting the fields on both sides of a live run.
                # `n_pro_psd` / `n_psd_used` are per length now (a snapshot-served rating counts
                # for a row only when it can fill it), so those two are checked by their own rule.
                for field, value in _stats.items():
                    if field in ("n_pro_psd", "n_psd_used", "n_pro_unmatched"):
                        continue
                    assert stats[float(s)][field] == value, (direction, s, field)
    assert compared == 2 * 3 * len(lengths) * len(pro) * len(CENTERS)


def test_a_piece_is_excluded_only_in_the_band_it_is_contaminated_in():
    """The same 3 s piece drops out at one band centre and is still used at another.

    This is the measured reason the rule is per band rather than per whole piece: on RCS08, 11,208
    of 296,157 pieces sit above a ceiling in at least one band but only 4 do in all 22, so throwing
    the whole piece away would discard mostly-good recording.
    """
    # Nearest-first from the rating: 10 (clean), 1000 (over at band 0 only), 20, 30.
    cache = _cache([T0, T0 + 3.0, T0 + 6.0, T0 + 9.0],
                   [_row(10.0), _row(1000.0), _row(20.0), _row(30.0)])
    ceilings = [500.0, np.inf, np.inf, np.inf]
    got, info, stats = av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=ceilings, allow_window_reuse=False)
    m = got[6.0]
    # Band 0 excluded the 1000 piece and took the next closest clean one: median(10, 20) = 15.
    assert np.isclose(m[0, 0], 15.0)
    # Band 1 has no ceiling, so the same piece is kept: median(11, 1001) = 506.
    assert np.isclose(m[0, 1], 506.0)
    assert info["n_chunk_band_values_excluded"] == 1


def test_a_dropped_piece_is_replaced_by_the_next_closest_clean_one():
    """Backfill, not simply dropping -- the PI's own choice, and the three answers differ.

    Two pieces are asked for. The nearest two are 10 and a contaminated 1000. Keeping both gives
    505; dropping the bad one and averaging what is left gives 10; taking the next closest clean
    piece instead gives 15. Asserting all three separately means this test fails if the behaviour
    ever silently becomes either of the other two rules.
    """
    cache = _cache([T0, T0 + 3.0, T0 + 6.0, T0 + 9.0],
                   [_row(10.0), _row(1000.0), _row(20.0), _row(30.0)])
    got, _info, _stats = av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=[500.0] + [np.inf] * 3, allow_window_reuse=False)
    value = got[6.0][0, 0]
    assert np.isclose(value, 15.0), value          # backfilled
    assert not np.isclose(value, 10.0), "the dropped piece was not replaced"
    assert not np.isclose(value, 505.0), "the contaminated piece was still used"


def test_a_longer_length_keeps_taking_clean_pieces_until_it_has_the_count_it_asked_for():
    """A cell asking for four pieces still averages four when one of the nearest four is bad."""
    cache = _cache([T0, T0 + 3.0, T0 + 6.0, T0 + 9.0, T0 + 12.0],
                   [_row(10.0), _row(1000.0), _row(20.0), _row(30.0), _row(40.0)])
    got, _info, _stats = av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[12.0], centers_hz=CENTERS,
        band_ceilings=[500.0] + [np.inf] * 3, allow_window_reuse=False)
    # Clean nearest four are 10, 20, 30, 40 -> median 25. Had it merely dropped the bad piece it
    # would have averaged three (10, 20, 30) and returned 20.
    assert np.isclose(got[12.0][0, 0], 25.0), got[12.0][0, 0]


def test_a_rating_with_no_voltage_trace_still_falls_back_to_the_device_spectrum():
    """The tier rule is unchanged: the voltage trace is preferred, the device's own spectrum serves
    a rating that has none, and a contaminated spectrum window is left out of its own band."""
    cache = _cache([T0], [_row(10.0)],
                   psd_t=[T0 + 5000.0, T0 + 5002.0],
                   psd_lsb=[_row(60.0), _row(9000.0)])
    got, info, stats = av.live_lsb_band_medians_by_length(
        [T0, T0 + 5001.0], cache, tol_s=600.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=[500.0] + [np.inf] * 3, allow_window_reuse=False)
    m = got[6.0]
    assert np.isclose(m[0, 0], 10.0)               # rating 0 kept its voltage-trace piece
    # Rating 1 has no voltage trace at all and sits 1 s from BOTH snapshots (a tie, broken by the
    # cache's own order, so the 60 snapshot is "nearest"). A 6 s row needs ONE snapshot (decision
    # 121, 30 s each). At band 0 the 9000 snapshot is over the ceiling; the nearest clean one is
    # 60. At band 1 nothing is excluded and the nearest alone is used: 61, not the median of both.
    assert np.isclose(m[1, 0], 60.0), m[1, 0]
    assert np.isclose(m[1, 1], 61.0), m[1, 1]
    assert info["n_chunk_band_values_excluded"] == 1
    # A 60 s row needs two snapshots: band 0 has only one clean one, so it is EMPTY there; band 1
    # has both, median(61, 9001) = 4531. A 5 min row needs ten: empty everywhere for this rating.
    got2, info2, _ = av.live_lsb_band_medians_by_length(
        [T0, T0 + 5001.0], cache, tol_s=600.0, lengths_s=[60.0, 300.0], centers_hz=CENTERS,
        band_ceilings=[500.0] + [np.inf] * 3, allow_window_reuse=False)
    assert not np.isfinite(got2[60.0][1, 0]), got2[60.0][1, 0]
    assert np.isclose(got2[60.0][1, 1], 4531.0), got2[60.0][1, 1]
    assert not np.isfinite(got2[300.0][1, 1])
    assert info2["n_psd_ratings_short_by_length"][300.0] == 1


def test_the_exclusion_never_writes_into_the_shared_recording_cache():
    """The tile cache is shared between panels and reused across all ten lengths, so the values it
    holds must be the same objects afterwards -- a masked copy, never an edit in place."""
    cache = _cache([T0, T0 + 3.0], [_row(10.0), _row(1000.0)])
    before = [list(r) for r in cache["td"]["lsb"]]
    av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=[500.0] + [np.inf] * 3, allow_window_reuse=False)
    assert [list(r) for r in cache["td"]["lsb"]] == before


# --------------------------------------------------------------------------------------------------
# merged from test_ceilings_keyed_on_participant.py
# Review B3 (2026-09-12): RCS08's outlier ceilings apply to RCS08 and to nobody else.
#
# `analytics.BAND_SWEEP_LSB_CEILINGS` holds the 99.5th-percentile ceilings measured on RCS08's own
# history (decision 94), under the six standard Percept contact-pair names every participant has.
# Keyed on the contact alone, a second participant with the same six names would have had RCS08's
# numbers applied to their own band powers, silently. The table is now keyed on the participant
# first, and the sweep looks it up through one function.
#
# Since 2026-10-03 (decision 410) the sweep reads no ceiling table: every contact of every
# participant is judged by its own 7-MAD-above bound. The table stays as the measured record of
# decision 94, and its lookup still refuses another participant. Plain asserts.


from ..routines import analytics as A
from .test_device_spectrum_mark import _sweep_power, COVERED_UID, COVERED_CHANNEL
RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


def test_the_table_is_keyed_on_rcs08_and_holds_its_six_contacts():
    assert COVERED_UID == RCS08
    assert set(A.BAND_SWEEP_LSB_CEILINGS) == {RCS08}, "one participant's ceilings, under its own uid"
    assert set(A.BAND_SWEEP_LSB_CEILINGS[RCS08]) == {
        "ZERO_THREE_RIGHT", "ONE_THREE_LEFT", "ZERO_THREE_LEFT", "ZERO_TWO_LEFT",
        "ONE_THREE_RIGHT", "ZERO_TWO_RIGHT"}
    # One real number, read back through the lookup: the 24.5 Hz ceiling on R 0-3.
    assert A.band_sweep_lsb_ceiling(RCS08, "ZERO_THREE_RIGHT", 24.5) == 498.6
    assert A.band_sweep_ceiling_table(RCS08, "ZERO_THREE_RIGHT")[24.5] == 498.6


def test_the_lookup_never_hands_rcs08s_numbers_to_another_participant():
    assert A.band_sweep_ceiling_table("another-participant", "ZERO_THREE_RIGHT") is None
    assert A.band_sweep_lsb_ceiling("another-participant", "ZERO_THREE_RIGHT", 24.5) is None
    assert A.band_sweep_ceiling_table(None, "ZERO_THREE_RIGHT") is None


def test_the_sweep_no_longer_reads_the_table():
    """Since 2026-10-03 (decision 410) every contact of every participant is judged by its own
    7-MAD-above bound (`analytics.chunk_upper_bounds`); the table chooses nothing in the sweep."""
    import inspect
    from .. import bravo_service as B
    src = inspect.getsource(B._band_time_sweep_power_by_seconds).split('"""')[2]
    assert "band_sweep_ceiling_table(" not in src and "BAND_SWEEP_LSB_CEILINGS" not in src
