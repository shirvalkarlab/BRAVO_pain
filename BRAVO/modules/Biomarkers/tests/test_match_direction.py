"""`live_lsb_spectrum_match`'s new `match_direction` argument (decision 60's follow-on wiring).

The calibrated band-by-length sweep's own matcher took no direction argument at all before this
change and always matched symmetrically in either time direction -- confirmed live this session by
running the page's three-way "Match direction" control (PRO-first / Nearest / Prior) and getting
identical matched counts and timings from all three, because the setting was never read. These
tests pin the fix with a hand-computable scenario, not just a shape check: under "prior" (the
forecasting-safe direction, kept for the threshold-deployment view where a recording must already
exist before the rating it explains), a recording after the rating it would otherwise match closest
to is excluded and the rating either falls back to an earlier recording or goes unmatched, both
checked against numbers worked out by hand rather than asserted from the code under test.
"""
import numpy as np

from ..routines import availability as av

CENTERS = [4.9]
T0 = 1_700_000_000.0


def _raw_cache(td_times, td_values, window_s=3.0):
    """One band centre, TD-only, every tile 'ok'. `td_values` is one value per tile."""
    n = len(td_times)
    return {
        "centers_hz": CENTERS, "window_s": window_s,
        "td": {"t": [T0 + t for t in td_times], "ok": [True] * n,
               "lsb": [[float(v)] for v in td_values]},
        "psd": {"t": [], "lsb": []},
    }


def test_prior_direction_excludes_a_recording_that_comes_after_the_rating():
    """Three TD tiles at t=100,200,300 (values 10,20,30); two ratings at t=150,250; tol=60 s,
    quantity=6 s (cap=2 tiles). Worked out by hand:

    Symmetric ("nearest"): tile100 and tile200 are both closer to rating150 (dist 50 each, tile200
    ties and a tie goes to the earlier rating) than to rating250 -> rating150 owns [tile100,
    tile200], median(10,20)=15. tile300 is closer to rating250 (dist 50) -> rating250 owns
    [tile300] alone, value 30.

    "prior" (a tile must be at or before the rating it explains): tile100's nearest rating AT OR
    AFTER it is rating150 (dt=50, eligible) -> rating150 owns [tile100] alone, value 10. tile200's
    nearest rating at or after it is rating250 (dt=50, eligible) -> rating250 owns [tile200] alone,
    value 20. tile300 has no rating at or after it at all (both ratings are earlier) -> unmatched,
    and neither rating's value changes because of it.
    """
    cache = _raw_cache([100, 200, 300], [10, 20, 30])
    pro = [T0 + 150, T0 + 250]

    recs_near, stats_near = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, match_direction="nearest")
    assert recs_near[0]["lsb"] == [15.0]
    assert recs_near[1]["lsb"] == [30.0]
    assert stats_near["match_direction"] == "prospective"

    recs_prior, stats_prior = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, match_direction="prior")
    assert recs_prior[0]["lsb"] == [10.0]
    assert recs_prior[1]["lsb"] == [20.0]
    assert stats_prior["match_direction"] == "prior"


def test_prior_direction_leaves_a_rating_unmatched_when_nothing_precedes_it():
    """One tile at t=500, one rating at t=200 (before the only tile) -- under "prior" the tile can
    never explain a rating it comes after, so the rating gets no TD tier at all, while "nearest"
    matches it (dist 300, within tol) as it always did."""
    cache = _raw_cache([500], [42])
    pro = [T0 + 200]

    recs_near, _ = av.live_lsb_spectrum_match(
        pro, cache, tol_s=400.0, td_quantity_s=6.0, match_direction="nearest")
    assert recs_near[0]["tier"] == av.PRO_LSB_TIER_TD
    assert recs_near[0]["lsb"] == [42.0]

    recs_prior, stats_prior = av.live_lsb_spectrum_match(
        pro, cache, tol_s=400.0, td_quantity_s=6.0, match_direction="prior")
    assert recs_prior[0]["tier"] is None
    assert stats_prior["n_pro_unmatched"] == 1


def test_pro_first_matches_symmetrically_same_as_nearest():
    """This matcher is window-first, not PRO-first (see the module docstring on
    `live_lsb_spectrum_match`) -- there is no PRO-first framing to switch to here, so the "PRO-first"
    UI setting is deliberately treated the same as "Nearest" rather than left silently ignored or
    given an invented, different behaviour."""
    cache = _raw_cache([100, 200, 300], [10, 20, 30])
    pro = [T0 + 150, T0 + 250]
    recs_a, stats_a = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, match_direction="pro_first")
    recs_b, stats_b = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, match_direction="nearest")
    assert recs_a[0]["lsb"] == recs_b[0]["lsb"] == [15.0]
    assert recs_a[1]["lsb"] == recs_b[1]["lsb"] == [30.0]
    assert stats_a["match_direction"] == stats_b["match_direction"] == "prospective"


def test_no_direction_argument_is_unchanged_from_before_this_change():
    """Backward compatibility: a caller that supplies no `match_direction` at all (every call site
    before this change) must get exactly what it always got -- symmetric matching."""
    cache = _raw_cache([100, 200, 300], [10, 20, 30])
    pro = [T0 + 150, T0 + 250]
    recs_default, stats_default = av.live_lsb_spectrum_match(pro, cache, tol_s=60.0, td_quantity_s=6.0)
    recs_explicit, _ = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, match_direction="nearest")
    assert recs_default[0]["lsb"] == recs_explicit[0]["lsb"] == [15.0]
    assert recs_default[1]["lsb"] == recs_explicit[1]["lsb"] == [30.0]
    assert stats_default["match_direction"] == "prospective"


def test_prior_direction_also_restricts_the_window_reuse_path():
    """The same restriction applies with `allow_window_reuse=True`, where a tile can serve more
    than one rating: with tol=60 and quantity=6 (cap=2), rating150 is eligible for tile100 (dt=50)
    and tile200 (dt=50, both within tol) under "nearest", but only for tile100 under "prior" since
    tile200 (t=200) comes after rating150 (t=150)."""
    cache = _raw_cache([100, 200, 300], [10, 20, 30])
    pro = [T0 + 150]

    recs_near, _ = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, allow_window_reuse=True,
        match_direction="nearest")
    assert recs_near[0]["lsb"] == [15.0]                # median(10, 20)

    recs_prior, _ = av.live_lsb_spectrum_match(
        pro, cache, tol_s=60.0, td_quantity_s=6.0, allow_window_reuse=True,
        match_direction="prior")
    assert recs_prior[0]["lsb"] == [10.0]                # tile100 only
