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

Merged here 2026-10-05: test_live_match_caption_direction.py, test_sweep_match_direction.py.
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


# --------------------------------------------------------------------------------------------------
# merged from test_live_match_caption_direction.py
# The "Last computed: N ratings matched to TD, M to a PSD" caption follows the match direction
# (review of 2026-09-26, Biomarkers finding 4).
#
# The caption under the matching controls reads `live_match_stats`, which `run_for_participant`
# builds through `_live_pro_lsb_spectrum`. That helper never took a match direction, so the counts
# were always worked out with symmetric matching; under "Each recording picks the next report after
# it" (the "prior" direction) the caption described a different pairing from the one the scan used.
# Only "prior" changes the matcher (`availability.live_lsb_spectrum_match`; "nearest" and "pro_first"
# both match symmetrically there), so only the caption under "prior" moves.
#
# Pinned on the value the matcher receives: the matcher and the tile cache are stand-ins, the helper
# under test is the real one. Plain asserts; the container runner has no pytest.


import os
import sys
_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402


def _call(**kw):
    seen = []
    real_match = bs.availability.live_lsb_spectrum_match
    real_cache = bs._raw_lsb_cache_cached
    real_stamp = bs._stamp_td_product

    def fake_match(pt, raw_cache, **k):
        seen.append(k.get("match_direction", "<not passed>"))
        return None, {"n_pro_td": 1}

    bs.availability.live_lsb_spectrum_match = fake_match
    bs._raw_lsb_cache_cached = lambda *a, **k: {"ONE_THREE_LEFT": {"td": {}, "psd": {}}}
    bs._stamp_td_product = lambda *a, **k: None
    try:
        _, stats = bs._live_pro_lsb_spectrum(
            "caption-direction-test", [1.0, 2.0], ["ONE_THREE_LEFT"], [], [],
            tol_s=3600.0, td_quantity_s=30.0, return_spectra=False, **kw)
    finally:
        bs.availability.live_lsb_spectrum_match = real_match
        bs._raw_lsb_cache_cached = real_cache
        bs._stamp_td_product = real_stamp
    return seen, stats


def test_prior_direction_reaches_the_caption_matcher():
    seen, stats = _call(match_direction="prior")
    assert seen == ["prior"], seen
    assert stats == {"ONE_THREE_LEFT": {"n_pro_td": 1}}, stats


def test_without_a_direction_the_matcher_gets_its_own_default():
    seen, _ = _call()
    assert seen == ["nearest"], seen


# --------------------------------------------------------------------------------------------------
# merged from test_sweep_match_direction.py
# Tests for `bravo_service._sweep_match_direction`, the request-level MatchDirection parsing
# the band-by-length sweep and its per-cell drill-down both read from (Track B).
#
# WHY THIS TEST EXISTS. `test_match_direction.py` in this same directory covers the matching
# routine itself, `availability.live_lsb_spectrum_match`'s own `match_direction` argument -- but
# nothing tested whether the value typed into the page's MatchDirection control actually reaches
# that argument. Before this test, the only evidence the wiring worked was a single live bridge
# call against RCS08 in an earlier session, which is not repeatable and leaves no record in either
# test suite. This closes that gap directly, at the level this container suite can run without a
# database: the request-dict parsing function itself, and the fact that both of the sweep's two
# request-handling entry points call the one shared helper rather than re-implementing it.
#
# Run inside the container:
#     docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_sweep_match_direction.py


import inspect


def test_the_sweep_parse_defaults_to_nearest_recognises_any_case_and_falls_back_to_pro_first():
    """`_sweep_match_direction`. The default since decision 331 (was "pro_first") comes from its one
    home. The sweep's own fallback is pro_first, deliberately different from the older three-way
    parse (which falls back to "prior"): a typo or an unexpected value here must not silently switch
    the sweep to the OTHER function's default."""
    assert bs._sweep_match_direction({}) == "nearest" == bs.sweep_settings.DEFAULT_MATCH_DIRECTION
    for typed, want in (("prior", "prior"), ("nearest", "nearest"), ("PRIOR", "prior"),
                        ("Nearest", "nearest"), ("sideways", "pro_first"), ("", "pro_first"),
                        ("pro_first", "pro_first")):
        got = bs._sweep_match_direction({"MatchDirection": typed})
        assert got == want, (typed, got, want)


def test_the_forecast_parse_defaults_to_nearest_recognises_its_spellings_and_falls_back_to_prior():
    """`_forecast_match_direction` is the OLDER MatchDirection parse used by `run_for_participant`
    and the pooled-detail builder (a review found it duplicated verbatim at both call sites). Its
    default with no key is the one-home default, "nearest" since decision 331. Its fallback is the
    opposite of the sweep's, and deliberately so: this reader is the causal-forecasting view, not
    the discovery sweep."""
    assert bs._forecast_match_direction({}) == "nearest"
    for typed, want in (("prior", "prior"), ("nearest", "nearest"), ("pro", "pro_first"),
                        ("pro-first", "pro_first"), ("sideways", "prior"), ("", "prior")):
        got = bs._forecast_match_direction({"MatchDirection": typed})
        assert got == want, (typed, got, want)


def test_forecast_and_sweep_helpers_disagree_only_on_the_documented_fallback():
    """The two helpers' own contract: identical on every recognised value, and differ ONLY on
    what an unrecognised value becomes. Pins the exact disagreement a review flagged, so a future
    edit that accidentally unifies the two fallbacks (or drifts them apart on a recognised value
    too) fails here first."""
    for value in ("prior", "nearest", "pro_first", "pro", "pro-first", "PRIOR", "Nearest"):
        rd = {"MatchDirection": value}
        assert bs._forecast_match_direction(rd) == bs._sweep_match_direction(rd), (
            f"the two helpers must agree on the recognised value {value!r}")
    rd = {"MatchDirection": "not-a-real-value"}
    assert bs._forecast_match_direction(rd) == "prior"
    assert bs._sweep_match_direction(rd) == "pro_first"


def test_run_for_participant_and_validate_band_core_both_use_the_shared_forecast_helper():
    """The two call sites this helper was extracted from -- `run_for_participant` and
    `_validate_band_core` -- must reach `_forecast_match_direction` rather than re-duplicating the
    parse inline. Checked by reading each function's own source, no database needed.

    WHY `_validate_band_core` IS CHECKED THROUGH `_band_validation_setup` NOW. The parse did not go
    away and was not duplicated: the participant-level setup was extracted out of
    `_validate_band_core` into `_band_validation_setup` so the calibrated-grid path could pay it
    once for 132 points instead of once per point, and the MatchDirection parse moved with it.
    `_validate_band_core` reaches the helper by calling that function.

    The original assertion is kept rather than relabelled, and a third is ADDED: that
    `_validate_band_core` really does delegate to the setup helper. Without that, this test could
    pass while `_validate_band_core` quietly stopped resolving MatchDirection at all.
    """
    # The functions that must call the helper directly. `_band_validation_setup` now owns the parse
    # that `_validate_band_core` used to make itself.
    for fn in (bs.run_for_participant, bs._band_validation_setup):
        src = inspect.getsource(fn)
        assert "_forecast_match_direction(request_data)" in src, (
            f"{fn.__name__} no longer calls the shared MatchDirection helper -- "
            f"has its parsing been re-duplicated inline?")

    # No call site may re-parse MatchDirection inline alongside the shared helper -- including
    # `_validate_band_core`, which must get its answer from the setup helper and nowhere else.
    for fn in (bs.run_for_participant, bs._band_validation_setup, bs._validate_band_core):
        src = inspect.getsource(fn)
        assert 'request_data.get("MatchDirection"' not in src, (
            f"{fn.__name__} parses MatchDirection inline again, alongside the shared helper")

    # And `_validate_band_core` must actually route through the setup helper, or it would resolve
    # MatchDirection nowhere at all while still satisfying the checks above.
    core_src = inspect.getsource(bs._validate_band_core)
    assert "_band_validation_setup(request_data)" in core_src, (
        "_validate_band_core no longer calls _band_validation_setup -- it now resolves "
        "MatchDirection nowhere, or has re-inlined the setup it was extracted from")


def test_the_grid_endpoint_and_the_cell_endpoint_call_the_one_shared_helper():
    """Both `band_time_sweep_for_participant` and `band_time_sweep_cell_for_participant` must read
    `_sweep_match_direction` rather than each re-parsing MatchDirection inline -- which is exactly
    the duplication this fix removed. Checked by reading each function's own source rather than by
    running the full request pipeline, so this test does not need a database or a participant.
    """
    for fn in (bs.band_time_sweep_for_participant, bs.band_time_sweep_cell_for_participant):
        src = inspect.getsource(fn)
        assert "_sweep_match_direction(request_data)" in src, (
            f"{fn.__name__} no longer calls the shared MatchDirection helper -- "
            f"has its parsing been re-duplicated inline?")
        assert 'request_data.get("MatchDirection"' not in src, (
            f"{fn.__name__} parses MatchDirection inline again, alongside the shared helper -- "
            f"that reintroduces the duplication this fix removed.")
