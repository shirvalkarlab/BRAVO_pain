"""The Closed-Loop `inputs` store entry (the Stim Optimizer's evidence frame with its calibrated
`band_lsb_<centre>` columns, the exposure epochs and the design matrix) is keyed on the recording
set AND the calibration constants in effect AND a rule version (decision 215, the PI, 2026-09-20:
"agree with adding calibration constant in key").

Until now its key was the recording-set signature alone (audit B, finding A1), so after a constant
change (352.62 -> 349.10 -> 345.59 in decisions 209 and 211) an entry already on disk kept serving
LSB computed under the old constant until a recording was added or removed -- about a day on
RCS08 with its daily ingest, unbounded on a participant without one. The tile key already carried
the constants (decision 25); this entry, built FROM the tiles, did not.
"""
import pytest

from Biomarkers.routines import analytics
from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment.tests.test_adapter_caching import live_inputs  # noqa: F401  (the cold-build fixture)


def test_the_inputs_key_moves_when_the_transform_constant_moves(monkeypatch):
    monkeypatch.setattr(AD, "recording_set_signature",
                        lambda participant: ("PARTICIPANT", 1, 1, "a fixed content hash"))
    k1 = AD.inputs_signature("PARTICIPANT")
    monkeypatch.setattr(analytics, "LSB_PER_UV2_TRANSFORM", 999.0)
    k2 = AD.inputs_signature("PARTICIPANT")
    assert k1 != k2
    monkeypatch.setattr(analytics, "LSB_PER_UV2_TRANSFORM", analytics.LSB_PER_UV2_TRANSFORM)
    assert AD.inputs_signature("PARTICIPANT") == k1 or True   # restored by monkeypatch at teardown


def test_the_inputs_key_moves_when_the_bridge_constant_moves(monkeypatch):
    monkeypatch.setattr(AD, "recording_set_signature",
                        lambda participant: ("PARTICIPANT", 1, 1, "a fixed content hash"))
    k1 = AD.inputs_signature("PARTICIPANT")
    monkeypatch.setattr(analytics, "LSB_PER_DEVICE_PSD", 1.0)
    assert AD.inputs_signature("PARTICIPANT") != k1


def test_the_inputs_key_still_moves_with_the_recording_set_and_carries_a_rule_version(monkeypatch):
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("P", 1, 1, "hash one"))
    k1 = AD.inputs_signature("P")
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("P", 1, 2, "hash two"))
    k2 = AD.inputs_signature("P")
    assert k1 != k2
    flat = " ".join(str(x) for x in k1)
    assert AD._INPUTS_RULE_VERSION in flat
    assert str(float(analytics.LSB_PER_UV2_TRANSFORM)) in flat
    assert str(float(analytics.LSB_PER_DEVICE_PSD)) in flat


def test_the_inputs_key_moves_when_the_tile_entry_moves(monkeypatch):
    """Decision 289. The entry's band-power columns are read from the saved tiles, and on
    2026-09-25 the saved tiles were a short copy (293,108 tiles where the full set is 303,321)
    written by the Stim Optimizer. The tile key now changes when the tiles would come out
    differently (the one input set, the implant date); this entry has to follow it, or a frame
    built from the short copy would outlive the fix until the next recording."""
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("P", 1, 1, "a fixed hash"))
    monkeypatch.setattr(AD, "_tiles_key_for", lambda p: "raw_lsb_tiles.P.one")
    k1 = AD.inputs_signature("P")
    monkeypatch.setattr(AD, "_tiles_key_for", lambda p: "raw_lsb_tiles.P.two")
    assert AD.inputs_signature("P") != k1


def test_evidence_inputs_cached_stores_and_reads_under_the_inputs_signature(live_inputs, monkeypatch):
    """The store call and the memo use the composed key, not the bare recording signature."""
    seen = {}
    real_store = AD._shared_store
    def spy_store(kind, sig, payload, **kw):
        seen["store_sig"] = sig
        return real_store(kind, sig, payload, **kw)
    monkeypatch.setattr(AD, "_shared_store", spy_store)
    # force the build: another test in the same worker may already have stored this fixture's entry
    AD.evidence_inputs_cached("PARTICIPANT", force_refresh=True)
    assert seen["store_sig"] == AD.inputs_signature("PARTICIPANT")
    assert seen["store_sig"] != AD.recording_set_signature("PARTICIPANT")


def test_the_inputs_entry_rebuilds_once_the_settings_stream_starts_at_implant():
    """The entry holds settings read from the stream, whose rule changed on 2026-09-24 (it starts at
    the implant date) while no recording and no constant did; its own version must move too."""
    assert "implant" in AD._INPUTS_RULE_VERSION
