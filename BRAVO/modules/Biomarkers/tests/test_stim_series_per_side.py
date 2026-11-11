"""Each band's stimulation-current series is its own side's (the PI, 2026-10-18: "don't pool both
sides' currents into one ... keep them unilateral"; decision 483, CLAUDE.md rule 13). The chronic
log carries the current on each side's own recordings; until 483 `availability.stim_series`
concatenated both sides into one series, so a left band's stimulation eras were cut by right-side
changes too.

Run:  python3 modules/Biomarkers/tests/test_stim_series_per_side.py   (in the container)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import availability as av
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import availability as av

T0 = 1_700_000_000.0


def _rec(side, t, amp):
    t = np.asarray(t, float)
    return {"ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
            "Time": t, "Data": np.column_stack([np.ones_like(t), np.asarray(amp, float)]),
            "RecordingType": "MedtronicChronicBrainSense", "Source": "chronic"}


CL = [_rec("Left", [T0, T0 + 600], [1.0, 1.0]), _rec("Right", [T0 + 300, T0 + 900], [4.0, 5.0]),
      _rec("Left", [T0 + 1200], [2.0])]


def test_one_side_only():
    left = av.stim_series(CL, hemisphere="Left")
    assert left["t"] == [T0, T0 + 600, T0 + 1200] and left["y"] == [1.0, 1.0, 2.0]
    right = av.stim_series(CL, hemisphere="Right")
    assert right["y"] == [4.0, 5.0]


def test_no_side_named_is_the_old_pooled_series():
    pooled = av.stim_series(CL)
    assert pooled["t"] == sorted([T0, T0 + 600, T0 + 1200, T0 + 300, T0 + 900])
    assert av.stim_series(CL, hemisphere=None) == pooled


def test_a_recording_with_no_side_in_its_names_never_counts_for_a_side():
    odd = dict(_rec("Left", [T0 + 50], [9.0]), ChannelNames=["LFP", "Amplitude"])
    assert 9.0 not in av.stim_series(CL + [odd], hemisphere="Left")["y"]


def _bs():
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for p in (_root, os.path.join(_root, "modules")):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    try:
        from modules.Biomarkers import bravo_service as bs
    except ImportError:                                        # pragma: no cover - host spelling
        from Biomarkers import bravo_service as bs
    return bs


def test_each_band_reads_its_own_sides_series_and_the_neutral_setting_the_pooled_one():
    bs = _bs()
    setup = {"stim_series": av.stim_series(CL),
             "stim_series_by_side": {s: av.stim_series(CL, hemisphere=s) for s in ("Left", "Right")}}
    assert bs.STIM_SERIES_PER_SIDE is True
    assert bs._stim_series_for(setup, "ONE_THREE_LEFT")["y"] == [1.0, 1.0, 2.0]
    assert bs._stim_series_for(setup, "ZERO_THREE_RIGHT")["y"] == [4.0, 5.0]
    keep = bs.STIM_SERIES_PER_SIDE
    try:
        bs.STIM_SERIES_PER_SIDE = False
        assert bs._stim_series_for(setup, "ONE_THREE_LEFT") is setup["stim_series"]
    finally:
        bs.STIM_SERIES_PER_SIDE = keep


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
