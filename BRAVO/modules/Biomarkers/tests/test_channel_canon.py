"""Regression test for the ring-aware channel canonicalizer (bravo_service._canon_channel).

Guards the fix for the silent Survey-product exclusion: the per-channel spectral scan tested
`_MAIN_BIPOLAR` membership with an exact string match, so BrainSense Survey channels named in the
ring vocabulary (e.g. `ZERO_AND_THREE_LEFT_RING`) never matched and the product contributed zero
rows to the pool. `_canon_channel` strips `_AND_` and the `_RING` suffix so ring names map onto the
canonical bipolar pairs; already-short names are unchanged (idempotent).

Needs Django configured (bravo_service imports models at module load); the harness runs each
test_* under django.setup(), so importing here is safe in that context.

Merged here 2026-10-05: test_td_missing_version_follows_limit.py.
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


def test_the_service_and_the_availability_module_share_one_canonicaliser():
    """Review B9.1 (2026-09-12): the service no longer carries its own copy of the rule."""
    from modules.Biomarkers.routines import availability as av
    assert bs._canon_channel is av._canon_channel


# --------------------------------------------------------------------------------------------------
# merged from test_td_missing_version_follows_limit.py
# P-05 (handoff pending-items list, 2026-09-25): the per-recording PSD files were filed under the
# hand-written name `_TD_MISSING_VERSION = "v1_missing_aware"`, a string typed by hand and never tied
# to the 10% missing-sample limit (`streaming_psd.WELCH_MAX_MISSING_FRAC`) it names. A change to that
# limit would silently serve PSDs built under the OLD limit forever, because nothing would tell the
# cache key to change.
#
# The fix names the version from the limit itself: at TODAY's limit (10%) it reproduces the exact
# literal string every already-cached file is filed under, so this change alone rebuilds nothing;
# any OTHER limit produces a different name, so a future change to the limit is caught by its own
# cache key instead of by a human remembering to bump a hand-written string.
#
# No Django and no database: stubbed the way test_shared_raw_lsb_cache.py stubs them.
#
# Run inside the container:
#     python3 _agent_bridge/run_tests.py


import unittest.mock as mock
_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()


def test_todays_limit_reproduces_the_existing_literal_name():
    """At the limit in force today (10%), the computed name equals the hand-written string every
    file on disk is already keyed under -- so this change alone forces no rebuild."""
    assert B._td_missing_version_for(0.10) == "v1_missing_aware", B._td_missing_version_for(0.10)
    assert B._TD_MISSING_VERSION == "v1_missing_aware", B._TD_MISSING_VERSION


def test_the_live_constant_is_built_from_the_live_limit():
    """`_TD_MISSING_VERSION` is not a separate hand-typed literal -- it is the function applied to
    the SAME limit the Welch rejection itself reads (`streaming_psd.WELCH_MAX_MISSING_FRAC`)."""
    assert B._TD_MISSING_VERSION == B._td_missing_version_for(B.streaming_psd.WELCH_MAX_MISSING_FRAC)


def test_changing_the_limit_changes_the_name():
    """A different missing-fraction limit must yield a DIFFERENT version name, so a future retune
    of the limit invalidates the caches keyed on the old one instead of silently reusing them."""
    base = B._td_missing_version_for(0.10)
    moved = B._td_missing_version_for(0.15)
    assert moved != base, (base, moved)
    tightened = B._td_missing_version_for(0.05)
    assert tightened != base and tightened != moved, (base, moved, tightened)


def test_the_name_carries_the_percentage_for_a_non_default_limit():
    """The non-default name is not opaque -- the percentage it was built from is readable in it,
    so a later reader can tell which limit produced a given cached file."""
    name = B._td_missing_version_for(0.15)
    assert "15" in name, name
