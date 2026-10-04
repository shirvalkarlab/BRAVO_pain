"""The modelled LSB is worked out only when the device has no measured threshold for the band (the
PI, 2026-10-04: "check if anything reads it", decision 434). Both the deployment summary and the
band-power panel read it in one place: the estimated threshold, used only when the device sensed
the band fewer than 20 times. On RCS08 the device sensed 46 of the 132 grid bands that often, and
for those the modelled values were worked out and thrown away.

Values: with 30 device-sensed values in the band, neither answer asks for the modelled values and
the threshold is the measured one; with all 30 outside the band, each asks once and the threshold is estimated."""
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from Biomarkers.tests.test_summary_auc_current_taken_out import (  # noqa: E402
    CH, _record, _django_available)


def _run(build_name, n_native):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import stim_current as sc
    detail, stream = _record("own")
    core = {"available": True, "participant_uid": "u", "Participant": None, "channel": CH,
            "center_hz": 24.5, "band_width_hz": 5.0, "pooled": detail, "stim_series": None,
            "glmer": {}, "stim": {}, "verdict": None, "label_metric": "nrs",
            "composite_parts": None, "label_strategy": "tertile", "low_pct": 33.3333,
            "high_pct": 66.6667, "match_direction": "prior", "clinic_sheet_ratings": None}
    rng = np.random.default_rng(3)
    # 30 device-sensed values, all in the band or (n_native=0) all at 60 Hz, outside it
    hz = [24.5] * n_native + [60.0] * (30 - n_native)
    series = {CH: {"y": list(rng.uniform(100, 900, 30)), "center_hz": hz,
                   "source": ["chronic"] * 30, "modeled": [False] * 30, "t": list(range(30))}}
    asked = []
    names = ("_validate_band_core", "_sign_off_recordings", "_calibration_scatter",
             "_modeled_lsb_values", "_programmed_adaptive_thresholds")
    saved = {k: getattr(bs, k) for k in names if hasattr(bs, k)}
    saved_sc, saved_lsb = sc.settings_stream_for, bs.availability.lsb_series
    try:
        bs._validate_band_core = lambda rd: dict(core)
        bs._sign_off_recordings = lambda uid: ([], [], [], [])
        bs._calibration_scatter = lambda uid: None
        bs._programmed_adaptive_thresholds = lambda p: {}
        bs.availability.lsb_series = lambda *a, **k: series

        def modeled(*a, **k):
            asked.append(a)
            return np.linspace(200.0, 800.0, 40)
        bs._modeled_lsb_values = modeled
        sc.settings_stream_for = lambda uid: stream
        out = getattr(bs, build_name)({"ParticipantId": "u", "Channel": CH, "CenterHz": 24.5,
                                       "BandWidthHz": 5.0, "NBoot": 200, "Cutpoint": 0.0})
    finally:
        for k, v in saved.items():
            setattr(bs, k, v)
        sc.settings_stream_for, bs.availability.lsb_series = saved_sc, saved_lsb
    return out, asked


def _threshold(build_name, out):
    if build_name == "_band_lsb_and_power_build":
        return out["threshold_lsb"]
    return out


def test_summary_skips_modelled_values_when_the_device_measured_the_band():
    if not _django_available():
        return
    out, asked = _run("_deployment_summary_build", 30)
    assert out.get("available") is True, out
    assert asked == []
    out, asked = _run("_deployment_summary_build", 0)
    assert len(asked) == 1


def test_band_power_skips_modelled_values_when_the_device_measured_the_band():
    if not _django_available():
        return
    out, asked = _run("_band_lsb_and_power_build", 30)
    assert asked == [] and out["threshold_lsb"]["estimated"] is False, out.get("threshold_lsb")
    out, asked = _run("_band_lsb_and_power_build", 0)
    assert len(asked) == 1 and out["threshold_lsb"]["estimated"] is True, out.get("threshold_lsb")
