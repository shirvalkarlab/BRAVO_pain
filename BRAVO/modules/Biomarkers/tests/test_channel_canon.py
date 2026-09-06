"""Regression test for the ring-aware channel canonicalizer (bravo_service._canon_channel).

Guards the fix for the silent Survey-product exclusion: the per-channel spectral scan tested
`_MAIN_BIPOLAR` membership with an exact string match, so BrainSense Survey channels named in the
ring vocabulary (e.g. `ZERO_AND_THREE_LEFT_RING`) never matched and the product contributed zero
rows to the pool. `_canon_channel` strips `_AND_` and the `_RING` suffix so ring names map onto the
canonical bipolar pairs; already-short names are unchanged (idempotent).

Needs Django configured (bravo_service imports models at module load); the harness runs each
test_* under django.setup(), so importing here is safe in that context.
"""
import os
import sys
import pathlib

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from modules.Biomarkers import bravo_service as bs


def test_canon_ring_names_map_into_main_bipolar():
    """Every Survey ring name for a main pair canonicalizes into _MAIN_BIPOLAR."""
    cases = {
        "ZERO_AND_THREE_LEFT_RING": "ZERO_THREE_LEFT",
        "ZERO_AND_THREE_RIGHT_RING": "ZERO_THREE_RIGHT",
        "ONE_AND_THREE_LEFT_RING": "ONE_THREE_LEFT",
        "ONE_AND_THREE_RIGHT_RING": "ONE_THREE_RIGHT",
        "ZERO_AND_TWO_LEFT_RING": "ZERO_TWO_LEFT",
        "ZERO_AND_TWO_RIGHT_RING": "ZERO_TWO_RIGHT",
    }
    for raw, want in cases.items():
        got = bs._canon_channel(raw)
        assert got == want, f"{raw} -> {got}, expected {want}"
        assert got in bs._MAIN_BIPOLAR, f"{got} not in _MAIN_BIPOLAR"


def test_canon_is_idempotent_on_short_names():
    """Already-canonical names are returned unchanged (TD/Stim montage spelling)."""
    for name in bs._MAIN_BIPOLAR:
        assert bs._canon_channel(name) == name
        assert bs._canon_channel(bs._canon_channel(name)) == name  # idempotent


def test_canon_lowercase_input():
    """Canon upper-cases, so lower/mixed-case ring names still match."""
    assert bs._canon_channel("zero_and_three_left_ring") == "ZERO_THREE_LEFT"


def test_canon_version_in_cache_keys():
    """The canon version is folded into both cache keys so a rule change invalidates stale caches."""
    assert bs._CHANNEL_CANON_VERSION in bs._recording_psd_cache_path("uid123", "hashabc")
