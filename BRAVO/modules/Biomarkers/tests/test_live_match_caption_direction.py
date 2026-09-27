"""The "Last computed: N ratings matched to TD, M to a PSD" caption follows the match direction
(review of 2026-09-26, Biomarkers finding 4).

The caption under the matching controls reads `live_match_stats`, which `run_for_participant`
builds through `_live_pro_lsb_spectrum`. That helper never took a match direction, so the counts
were always worked out with symmetric matching; under "Each recording picks the next report after
it" (the "prior" direction) the caption described a different pairing from the one the scan used.
Only "prior" changes the matcher (`availability.live_lsb_spectrum_match`; "nearest" and "pro_first"
both match symmetrically there), so only the caption under "prior" moves.

Pinned on the value the matcher receives: the matcher and the tile cache are stand-ins, the helper
under test is the real one. Plain asserts; the container runner has no pytest.
"""
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
