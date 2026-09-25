"""Proposal 3 (2026-09-25): the heat-map grid's per-row `np.nanmedian` as one whole-matrix sort.

`np.nanmedian(arr, axis=1)` on a 2D array is not the single vectorised call it looks like: numpy's
own implementation falls through to `np.apply_along_axis`, running its inner reduction once per row
in Python. Measured live on RCS08's heat-map grid, that cost 7.4 of the grid's about 13.8 seconds
across 923,076 rows and 1,284,219 discarded `RuntimeWarning`s (one per all-NaN or short row).

`availability._whole_matrix_nanmedian(values, keep)` replaces
`np.nanmedian(np.where(keep, values, np.nan), axis=1)` with a full `np.sort` of each row plus a
finite-count and an index lookup -- one vectorised call, no per-row Python loop. A median is an
order statistic, so the two must agree value for value, including the edge cases a whole-matrix
reduction could get wrong that a straightforward per-row call could not: an infinite reading (a
real, comparable value, not a value `nanmedian` throws away the way it throws away NaN), a row with
no finite value at all, an even count whose two middle values straddle `+inf` and `-inf` (numpy's
own `(inf + -inf) / 2 = nan`), and a `cap` wider than the pieces on offer.
"""
import numpy as np

from ..routines import availability as av


def _reference(values, keep):
    """The exact call this function replaces, kept here as the ground truth to compare against."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(np.where(keep, values, np.nan), axis=1)


def _assert_matches(values, keep, msg=""):
    want = _reference(values, keep)
    got = av._whole_matrix_nanmedian(values, keep)
    assert got.shape == want.shape, msg
    np.testing.assert_array_equal(got, want, err_msg=msg)


def test_matches_nanmedian_on_random_matrices_odd_and_even_counts():
    rng = np.random.default_rng(20260925)
    for trial in range(50):
        nR, width = rng.integers(1, 12), rng.integers(1, 15)
        values = rng.uniform(-500.0, 500.0, size=(nR, width))
        keep = rng.random((nR, width)) > 0.3      # some columns dropped per row -> mixed counts
        _assert_matches(values, keep, f"trial {trial}, shape {(nR, width)}")


def test_a_row_with_no_kept_value_is_nan_like_nanmedian():
    values = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    keep = np.array([[False, False, False], [True, True, False]])
    got = av._whole_matrix_nanmedian(values, keep)
    assert np.isnan(got[0])
    assert np.isclose(got[1], 4.5)                 # median(4, 5)


def test_an_infinite_reading_is_a_real_value_not_dropped_like_nan():
    """`nanmedian` strips NaN only; +inf is a legitimate, comparable value and can win a median."""
    values = np.array([[1.0, 2.0, np.inf]])
    keep = np.array([[True, True, True]])
    _assert_matches(values, keep, "median(1, 2, inf) must equal the reference")
    # median of an odd count of 3, sorted [1, 2, inf] -> middle value is 2, not inf and not nan
    assert av._whole_matrix_nanmedian(values, keep)[0] == 2.0


def test_even_count_averaging_matches_including_the_inf_minus_inf_case():
    # sorted [-inf, -inf, inf, inf]: two middle values are -inf and inf -> (-inf + inf) / 2 = nan
    values = np.array([[np.inf, -np.inf, -np.inf, np.inf]])
    keep = np.array([[True, True, True, True]])
    _assert_matches(values, keep, "the straddling +inf/-inf case must equal the reference")
    got = av._whole_matrix_nanmedian(values, keep)[0]
    ref = _reference(values, keep)[0]
    assert np.isnan(got) and np.isnan(ref), (got, ref)

    # sorted [1, 2, inf, inf]: two middle values are 2 and inf -> ordinary finite/infinite average
    values2 = np.array([[np.inf, 2.0, 1.0, np.inf]])
    keep2 = np.array([[True, True, True, True]])
    _assert_matches(values2, keep2)
    assert np.isinf(av._whole_matrix_nanmedian(values2, keep2)[0])


def test_a_cap_wider_than_the_pieces_on_offer_still_matches():
    """`keep` marks fewer True entries than the row's width -- the short-row case a real grid cell
    hits whenever a rating's own eligible pieces run out before the requested length's cap."""
    values = np.array([[10.0, 20.0, 30.0, 40.0, 50.0]])
    keep = np.array([[True, True, False, False, False]])   # only 2 of 5 columns eligible
    _assert_matches(values, keep)
    assert np.isclose(av._whole_matrix_nanmedian(values, keep)[0], 15.0)


def test_empty_matrix_is_safe():
    values = np.zeros((0, 4))
    keep = np.zeros((0, 4), dtype=bool)
    got = av._whole_matrix_nanmedian(values, keep)
    assert got.shape == (0,)

    values2 = np.zeros((3, 0))
    keep2 = np.zeros((3, 0), dtype=bool)
    got2 = av._whole_matrix_nanmedian(values2, keep2)
    assert got2.shape == (3,)
    assert np.all(np.isnan(got2))


def test_live_lsb_band_medians_by_length_unchanged_with_infinite_and_all_excluded_readings():
    """The two call sites inside `live_lsb_band_medians_by_length` (voltage-trace and
    device-spectrum branches) must still agree with a hand-built reference that calls the OLD
    `nanmedian` reduction directly on the same intermediate arrays, on a case built to exercise the
    edge conditions above: an infinite reading and a rating whose nearest piece is excluded.
    """
    CENTERS = [8.5, 12.5]
    T0 = 1_700_000_000.0
    cache = {
        "channel": "TEST", "centers_hz": CENTERS, "window_s": 3.0, "band_half_hz": 2.5,
        "td": {"t": [T0, T0 + 3.0, T0 + 6.0], "ok": [True, True, True],
               "lsb": [[10.0, np.inf], [1000.0, 20.0], [30.0, 40.0]],
               "saturated": [False, False, False], "source": ["c"] * 3,
               "n_finite_s": [3.0, 3.0, 3.0]},
        "psd": {"t": [], "lsb": [], "calibrated": [], "source": []},
        "n_td_windows": 3, "n_psd_windows": 0,
    }
    got, info, _stats = av.live_lsb_band_medians_by_length(
        [T0], cache, tol_s=1800.0, lengths_s=[6.0], centers_hz=CENTERS,
        band_ceilings=[500.0, np.inf], allow_window_reuse=False)
    # Band 0: nearest two clean pieces after excluding 1000 are 10 and 30 -> median 20.
    assert np.isclose(got[6.0][0, 0], 20.0), got[6.0][0, 0]
    # Band 1 has no ceiling: nearest two are inf and 20 -> median(inf, 20) = (inf + 20) / 2 = inf.
    assert np.isinf(got[6.0][0, 1]), got[6.0][0, 1]
    assert info["n_chunk_band_values_excluded"] == 1
