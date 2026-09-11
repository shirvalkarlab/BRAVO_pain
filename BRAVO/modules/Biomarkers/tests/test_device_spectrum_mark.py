"""Marking the cells the length-of-signal axis does not apply to (open item 26).

A pain report with no voltage trace in range is answered from the device's OWN spectrum, and that
route reads no length of signal at all -- it has no quantity cap, only the match tolerance. Such a
report therefore contributes the identical band power to every row of the grid, and nothing about
the number says so. Measured on RCS08 on 2026-09-10: 358 of the 451 matched reports on R 0-3+
(79.4 percent) come that way, and that contact's correlation travels only 0.037 across the whole
length axis against 0.160-0.253 on the two contacts with none.

The first test is the load-bearing one: it pins the PROPERTY the mark exists to describe, on the
real matcher, rather than trusting the description -- a device-spectrum report's value must be
identical at every length, a voltage-trace report's must not be, and the flag must name exactly the
first group.

The rest pin the mark itself, including the two ways it could be quietly wrong: counting reports a
cell did not use, and marking the area-under-the-curve grid with the correlation grid's own
denominator when the two are computed from different reports.
"""
import numpy as np

from ..routines import availability as av
from ..routines import analytics as A

CENTERS = [8.5, 12.5, 16.5, 20.5]
TILE_S = 3.0
T0 = 1_700_000_000.0
NO_CEILING = [np.inf] * len(CENTERS)
LENGTHS = [1.0, 5.0, 30.0, 300.0]


def _row(base):
    return [float(base + j) for j in range(len(CENTERS))]


def _cache(td_t, td_lsb, psd_t=(), psd_lsb=()):
    nC = len(CENTERS)
    td_t = [float(t) for t in td_t]
    return {"channel": "TEST_CONTACT", "centers_hz": [float(c) for c in CENTERS],
            "window_s": TILE_S, "band_half_hz": 2.5,
            "td": {"t": td_t, "lsb": td_lsb, "saturated": [False] * len(td_t),
                   "source": ["constructed"] * len(td_t),
                   "n_finite_s": [TILE_S] * len(td_t), "ok": [True] * len(td_t)},
            "psd": {"t": [float(t) for t in psd_t], "lsb": list(psd_lsb),
                    "calibrated": [[True] * nC] * len(psd_t),
                    "source": ["constructed"] * len(psd_t)},
            "n_td_windows": len(td_t), "n_psd_windows": len(psd_t)}


def test_the_flag_names_the_snapshot_served_reports_and_those_now_honour_the_length_axis():
    """The property, on the real matcher, under the rule of 2026-09-10 (decision 121).

    One rating sits on a long run of voltage trace, so lengthening the signal really does pull in
    more pieces and change its median. A second rating has no voltage trace anywhere near it and
    only two of the device's own FFT snapshots. Each snapshot covers 30 s, so that rating can fill
    every row up to 30 s from its nearest snapshot alone, fills the 45 s and 60 s rows from both
    (their median), and cannot fill the 5 min row at all (ten needed, two present) -- that cell is
    empty for it. Before this rule the flagged rating wrote one number into every row; the old
    version of this test asserted exactly that, and is superseded.
    """
    td_t = [T0 + 1.5 + 3.0 * k for k in range(20)]
    td_lsb = [_row(10.0 * k) for k in range(20)]
    psd_t = [T0 + 90000.0, T0 + 90002.0]          # the second is nearer to the rating below
    psd_lsb = [_row(500), _row(520)]
    cache = _cache(td_t, td_lsb, psd_t, psd_lsb)
    pro = [T0 + 30.0, T0 + 90001.5]

    lens = LENGTHS + [60.0]                        # 60 s needs two snapshots; the rest one or ten
    got, info, stats = av.live_lsb_band_medians_by_length(
        pro, cache, tol_s=600.0, lengths_s=lens, centers_hz=CENTERS,
        band_ceilings=NO_CEILING)

    flags = info["from_device_spectrum"]
    assert len(flags) == len(pro)
    assert flags == [False, True], flags
    assert info["psd_snapshot_s"] == 30.0

    for s in lens:
        need = int(np.ceil(s / 30.0))
        assert info["psd_snapshots_needed_by_length"][float(s)] == need
        v = got[s][1, 0]
        if need == 1:
            assert v == 520.0, (s, v)                       # the nearest snapshot alone
        elif need == 2:
            assert v == 510.0, (s, v)                       # median of both snapshots
        else:
            assert not np.isfinite(v), (s, v)               # not enough snapshots: empty
            assert info["n_psd_ratings_short_by_length"][float(s)] == 1
            assert stats[float(s)]["n_pro_psd"] == 0
    # The unflagged rating: at least one band genuinely moves, so the axis means something there.
    by_len = [got[s] for s in lens]
    moved = any(len({m[0, j] for m in by_len}) > 1 for j in range(len(CENTERS)))
    assert moved, "the voltage-trace rating should not be constant down the length axis"


def test_a_rating_with_no_recording_at_all_is_not_marked_as_device_spectrum():
    """An unmatched rating is absent, not device-served. Marking it would inflate the share with
    reports that contributed nothing to any cell."""
    cache = _cache([T0 + 1.5], [_row(10)], [T0 + 5.0], [_row(50)])
    pro = [T0 + 2.0, T0 + 999999.0]
    _got, info, _stats = av.live_lsb_band_medians_by_length(
        pro, cache, tol_s=60.0, lengths_s=LENGTHS, centers_hz=CENTERS, band_ceilings=NO_CEILING)
    assert info["from_device_spectrum"] == [False, False]


def test_the_count_uses_only_the_reports_a_cell_actually_used():
    """The denominator is a finite band power AND a finite pain score, cell by cell.

    Built so the three exclusions are all present and all different: one report has no band value
    in one cell, one has no pain score at all, and one is a perfectly good device-served report.
    """
    # X is (lengths, reports, bands). Four reports, two lengths, two bands.
    X = np.array([
        [[1.0, 2.0], [3.0, np.nan], [5.0, 6.0], [7.0, 8.0]],
        [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]],
    ], dtype=float)
    pain = np.array([1.0, 2.0, 3.0, np.nan])
    flags = [True, True, False, True]

    n_dev, n_tot = A._device_spectrum_cell_counts(X, pain, flags)

    # Length 0, band 1: report 1 has no band value and report 3 has no pain score, so only reports
    # 0 (device) and 2 (not) remain.
    assert n_tot[0, 1] == 2 and n_dev[0, 1] == 1
    # Length 0, band 0: reports 0, 1, 2 remain; two of them are device-served.
    assert n_tot[0, 0] == 3 and n_dev[0, 0] == 2
    # The report with no pain score is never counted anywhere, even though it is flagged.
    assert n_tot.max() == 3


def test_a_flag_list_of_the_wrong_length_marks_nothing_rather_than_raising():
    """The mark is a caveat. A caveat that can break the page it annotates is worse than none."""
    X = np.ones((2, 3, 2), dtype=float)
    pain = np.array([1.0, 2.0, 3.0])
    for bad in (None, [], [True], [True] * 99):
        n_dev, n_tot = A._device_spectrum_cell_counts(X, pain, bad)
        assert n_dev.sum() == 0
        assert n_tot.min() == 3          # the denominator is still real


def _grid(pain, flags, strategy="tertile"):
    rng = np.random.default_rng(11)
    n = len(pain)
    power = {s: rng.normal(100.0, 5.0, size=(n, 3)) for s in (1.0, 5.0, 30.0)}
    return A.band_time_sweep_from_power(
        power, pain, center_freqs_hz=[8.5, 12.5, 16.5], strategy=strategy,
        n_perm=20, n_boot=20, seed=0, from_device_spectrum=flags)


def test_the_two_grids_are_marked_from_their_own_reports_not_from_one_shared_count():
    """THE CASE LIVE DATA CANNOT SHOW. Splitting the pain scores into thirds throws the middle third
    away, so the area-under-the-curve grid is computed from fewer reports than the correlation grid
    above it. Here every device-served report is deliberately put IN that middle third, so the
    correlation grid's share is large and the curve grid's is zero. One shared count would report
    the same number twice and one of them would be wrong.

    On RCS08 these two agree everywhere, because its pain scores are whole numbers and the thirds
    land between them so nothing is actually dropped -- which is exactly why the case has to be
    constructed rather than measured.
    """
    pain = np.array([0.0, 1.0, 2.0, 40.0, 50.0, 60.0, 90.0, 95.0, 99.0])
    flags = [False, False, False, True, True, True, False, False, False]

    sw = _grid(pain, flags)

    corr_tot = np.asarray(sw["device_spectrum_total_grid"], dtype=float)
    auc_tot = np.asarray(sw["device_spectrum_total_grid_auc"], dtype=float)
    corr_share = np.asarray([[np.nan if v is None else v for v in r]
                             for r in sw["device_spectrum_share_grid"]], dtype=float)
    auc_share = np.asarray([[np.nan if v is None else v for v in r]
                            for r in sw["device_spectrum_share_grid_auc"]], dtype=float)

    corr_n = np.asarray(sw["device_spectrum_n_grid"], dtype=float)
    auc_n = np.asarray(sw["device_spectrum_n_grid_auc"], dtype=float)

    # Every curve cell is computed from fewer reports than the correlation cell above it.
    assert (auc_tot < corr_tot).all(), (auc_tot, corr_tot)
    # Every device-served report sits in the discarded middle third, so the correlation grid is
    # heavily marked and the curve grid is not marked at all. One shared count could not say both.
    assert (corr_n == 3).all(), corr_n
    assert (auc_n == 0).all(), auc_n
    assert np.allclose(auc_share, 0.0)
    # The share is that cell's own count over that cell's own denominator, everywhere.
    assert np.allclose(corr_share, corr_n / corr_tot)
    # And the curve grid's denominator is its OWN high-plus-low count, not the correlation's.
    hi = np.asarray(sw["auc_n_high_grid"], dtype=float)
    lo = np.asarray(sw["auc_n_low_grid"], dtype=float)
    assert np.array_equal(auc_tot, hi + lo)
    # PER CELL, NOT PER CONTACT, and this fixture proves the difference is real rather than
    # theoretical: the outlier rule drops one report from ONE cell, so that cell's denominator is 8
    # where its neighbours' is 9 and its share is 0.375 against their 0.333. A single contact-wide
    # share pasted onto every cell would be wrong for that cell.
    assert corr_tot.min() == 8 and corr_tot.max() == 9, corr_tot
    assert len(set(np.round(corr_share.ravel(), 6))) > 1, corr_share


def test_the_headline_row_carries_the_mark_for_its_own_winning_length():
    """Each band centre's row names ONE cell. It must be handed that cell's count, not another
    length's -- so the row's own reported length is what the lookup uses."""
    pain = np.arange(12, dtype=float)
    flags = [True] * 6 + [False] * 6
    sw = _grid(pain, flags, strategy="median")

    n_dev = np.asarray(sw["device_spectrum_n_grid"], dtype=float)
    req = [float(s) for s in sw["integration_seconds_requested"]]
    rows = sw["best_correlation_rows"]
    assert len(rows) == 3
    for c, row in enumerate(rows):
        t = req.index(float(row["integration_seconds_requested"]))
        assert row["n_pain_reports_from_device_spectrum"] == int(n_dev[t, c])
        assert row["device_spectrum_share"] is not None


def test_a_contact_with_no_device_served_reports_gets_no_note_and_a_zero_share():
    """Nothing to warn about must read as nothing, not as a reassurance and not as an absence."""
    pain = np.arange(12, dtype=float)
    sw = _grid(pain, [False] * 12, strategy="median")
    assert sw["n_pain_reports_from_device_spectrum"] == 0
    assert np.asarray(sw["device_spectrum_n_grid"], dtype=float).sum() == 0
    assert not any("device's own FFT snapshots" in str(n) for n in sw["notes"])

    marked = _grid(pain, [True] * 6 + [False] * 6, strategy="median")
    assert marked["n_pain_reports_from_device_spectrum"] == 6
    assert any("device's own FFT snapshots" in str(n) for n in marked["notes"])


def test_the_flag_is_reported_as_unknown_rather_than_zero_when_it_never_arrived():
    """"None of them" and "nobody checked" are different answers. A caller that passes no flag gets
    the second, so a page cannot show a confident zero for a question that was never asked."""
    pain = np.arange(12, dtype=float)
    sw = _grid(pain, None, strategy="median")
    assert sw["n_pain_reports_from_device_spectrum"] is None
    assert np.asarray(sw["device_spectrum_n_grid"], dtype=float).sum() == 0


def test_the_mark_does_not_travel_inside_the_argument_that_switches_the_outlier_rule():
    """`chunk_exclusion` is a switch as well as a payload: its mere presence tells the grid that the
    per-piece ceiling rule already ran and the median-absolute-deviation rule must NOT be applied on
    top. Folding this flag in there would silently turn that second rule off for every contact the
    ceiling table does not cover. So the flag must mark the grid while leaving that rule alone."""
    pain = np.arange(12, dtype=float)
    sw = _grid(pain, [True] * 12, strategy="median")
    assert sw["chunk_exclusion"] is None
    assert sw["outlier_rule"].endswith("_mad_log") or "_mad_" in sw["outlier_rule"], sw["outlier_rule"]
    assert sw["n_pain_reports_from_device_spectrum"] == 12


def test_the_blank_result_carries_the_fields_rather_than_omitting_them():
    """An absent key reads on this page as "does not apply". A grid that could not be built has not
    established that the length axis is meaningful, so it must not say so by omission."""
    blank = A._sweep_blank("nothing to do")
    for k in ("device_spectrum_n_grid", "device_spectrum_total_grid", "device_spectrum_share_grid",
              "device_spectrum_n_grid_auc", "device_spectrum_total_grid_auc",
              "device_spectrum_share_grid_auc"):
        assert blank[k] == []
    assert blank["n_pain_reports_from_device_spectrum"] is None


# ---------------------------------------------------------------------------------------------
# The two paths into the sweep, and the one field that must not travel with the flag.

def _sweep_power(channel):
    from .. import bravo_service as B
    # Two reports: the first sits on voltage trace, the second only near device-spectrum events.
    td_t = [T0 + 1.5 + 3.0 * k for k in range(8)]
    td_lsb = [_row(10.0 * k) for k in range(8)]
    cache = _cache(td_t, td_lsb, [T0 + 90000.0, T0 + 90002.0], [_row(500), _row(520)])
    pro = [T0 + 12.0, T0 + 90001.0]
    return B._band_time_sweep_power_by_seconds(
        pro, cache, CENTERS, tol_s=600.0, allow_window_reuse=False, seconds=LENGTHS,
        channel=channel)


def test_both_matching_paths_report_the_flag_and_agree_about_which_report_is_which():
    """The sweep has TWO matchers -- the per-piece-ceiling path for a contact the ceiling table
    covers, and the older path for one it does not. A caveat that appeared on only one of them
    would be missing exactly where a reader has least reason to expect it, so both are asked, and
    both must name the same report."""
    covered = next(iter(A.BAND_SWEEP_LSB_CEILINGS))          # a real contact with a ceiling table
    for channel in (covered, "A_CONTACT_WITH_NO_CEILING_TABLE"):
        *_rest, chunk_excl, flags = _sweep_power(channel)
        assert flags == [False, True], (channel, flags)
        # And the two paths are genuinely different paths, which is what makes the check worth
        # making: only the covered one runs the per-piece ceiling rule.
        assert (chunk_excl is not None) == (channel == covered), channel


def test_the_per_report_flag_does_not_ride_into_the_response_inside_the_exclusion_block():
    """REGRESSION. `chunk_exclusion` is copied into the served response whole. The flag was first
    built inside it, which shipped one boolean per pain report per contact pair -- 4,584 of them on
    RCS08, growing with every report filed -- for a fact the grids already carry summarised per
    cell, under a name that does not describe it. It is lifted out before the response is built."""
    covered = next(iter(A.BAND_SWEEP_LSB_CEILINGS))
    *_rest, chunk_excl, flags = _sweep_power(covered)
    assert chunk_excl is not None
    assert "from_device_spectrum" not in chunk_excl, sorted(chunk_excl)
    assert flags, "the flag itself must still be returned, just not through that block"
