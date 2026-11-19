"""The timeline's detail panel (item P-18, the PI's go-ahead 2026-10-06): what one clicked mark
returns. Django-free, on synthetic recordings shaped like the decoded Percept recordings.

The panel shows what the device recorded for ONE contact pair, unscaled: the voltage trace, the
device's own PSD and the device's sensed band power around the clicked time. Nothing is computed,
matched to pain or modelled, and no other contact's values enter it.
"""
import sys
import pathlib

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import timeline_detail as TD

T0 = 1_760_000_000.0


def _stream(n=2500, start=T0):
    data = np.column_stack([np.arange(n, dtype=float), -np.arange(n, dtype=float)])
    missing = np.zeros_like(data)
    missing[10, :] = 1
    return {"ChannelNames": ["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], "Data": data, "Missing": missing,
            "SamplingRate": 250.0, "StartTime": start, "Duration": n / 250.0,
            "RecordingType": "MedtronicIndefiniteStream"}


def _montage(start=T0 + 5000):
    f = [i * 0.977 for i in range(100)]
    return {"ChannelNames": ["ZERO_AND_THREE_LEFT_RING", "ONE_AND_THREE_LEFT_RING"],
            "Data": np.ones((5000, 2)), "SamplingRate": 250.0, "StartTime": start, "Duration": 20.0,
            "RecordingType": "MedtronicBaselineMontages",
            "Descriptor": {"MedtronicPSD": [
                {"LFPFrequency": f, "LFPMagnitude": [1.0] * 100, "PeakFrequencyInHertz": 0.0,
                 "ArtifactStatus": "ARTIFACT_NOT_PRESENT", "SensingElectrodes": "ZERO_AND_THREE_LEFT_RING"},
                {"LFPFrequency": f, "LFPMagnitude": [2.0] * 100, "PeakFrequencyInHertz": 12.7,
                 "ArtifactStatus": "ARTIFACT_NOT_PRESENT", "SensingElectrodes": "ONE_AND_THREE_LEFT_RING"},
            ]}}


def test_the_trace_is_the_clicked_pair_only_with_missing_samples_left_out():
    sel = {"Channel": "ONE_THREE_LEFT", "Dtype": "timedomain", "Product": "indefinite", "TStart": T0}
    out = TD.build_detail(sel, td_recs=[_stream()], psd_recs=[], event_rows=[], native_lsb={})
    tr = out["trace"]
    assert tr["unit"] == "µV" and tr["fs"] == 250.0 and tr["n"] == 2500
    assert tr["y"][11] == -11.0 and tr["y"][10] is None          # the second column, not the first
    assert tr["every_nth"] == 1 and out["psd"] is None


def test_a_long_trace_is_thinned_to_its_minimum_and_maximum_never_averaged():
    rec = _stream(n=200_000)
    sel = {"Channel": "ZERO_THREE_LEFT", "Dtype": "timedomain", "Product": "indefinite", "TStart": T0}
    tr = TD.build_detail(sel, td_recs=[rec], psd_recs=[], event_rows=[], native_lsb={},
                         max_trace_points=1000)["trace"]
    assert len(tr["y"]) <= 1000 and tr["envelope"] is True
    finite = [v for v in tr["y"] if v is not None]
    assert max(finite) == 199_999.0 and min(finite) == 0.0       # extremes kept


def test_a_montage_mark_returns_the_devices_own_psd_for_that_pair_unscaled():
    sel = {"Channel": "ONE_AND_THREE_LEFT_RING", "Dtype": "psd", "Product": "montage_psd",
           "TStart": T0 + 5000}
    out = TD.build_detail(sel, td_recs=[], psd_recs=[_montage()], event_rows=[], native_lsb={})
    assert out["psd"]["mag"] == [2.0] * 100 and out["psd"]["unit"] == "µVp"
    assert out["psd"]["peak_hz"] == 12.7
    assert out["trace"]["n"] == 5000                              # the montage's own voltage trace


def test_a_patient_event_mark_returns_its_device_psd_and_no_trace():
    rows = [{"channel": "ZERO_THREE_LEFT", "t": T0 + 9000, "freq": [1.0, 2.0], "power": [3.0, 4.0],
             "source": "event"},
            {"channel": "ZERO_THREE_RIGHT", "t": T0 + 9000, "freq": [1.0, 2.0], "power": [9.0, 9.0],
             "source": "event"}]
    sel = {"Channel": "ZERO_THREE_LEFT", "Dtype": "psd", "Product": "patient_event", "TStart": T0 + 9000}
    out = TD.build_detail(sel, td_recs=[], psd_recs=[], event_rows=rows, native_lsb={})
    assert out["psd"]["mag"] == [3.0, 4.0] and out["trace"] is None
    assert "no voltage trace" in out["missing"]["trace"]


def test_band_power_is_this_pairs_sensed_values_inside_the_window():
    native = {"ZERO_THREE_LEFT": {"t": [T0 - 90_000, T0 - 100, T0 + 100, T0 + 90_000],
                                  "y": [1.0, 2.0, 3.0, 4.0], "center_hz": [12.7] * 4,
                                  "source": ["chronic"] * 4},
              "ONE_THREE_LEFT": {"t": [T0], "y": [99.0], "center_hz": [9.8], "source": ["streaming"]}}
    sel = {"Channel": "ZERO_THREE_LEFT", "Dtype": "bandpower", "Product": "timeline_lsb", "TStart": T0}
    out = TD.build_detail(sel, td_recs=[], psd_recs=[], event_rows=[], native_lsb=native)
    assert out["band_power"]["y"] == [2.0, 3.0] and out["band_power"]["unit"] == "LSB"
    assert out["trace"] is None and out["psd"] is None


def test_a_mark_with_no_matching_recording_says_so():
    sel = {"Channel": "ZERO_THREE_LEFT", "Dtype": "timedomain", "Product": "indefinite", "TStart": T0 + 1e6}
    out = TD.build_detail(sel, td_recs=[_stream()], psd_recs=[], event_rows=[], native_lsb={})
    assert out["trace"] is None and out["missing"]["trace"]


def test_no_pain_rating_in_the_answer():
    sel = {"Channel": "ZERO_THREE_LEFT", "Dtype": "timedomain", "Product": "indefinite", "TStart": T0}
    out = TD.build_detail(sel, td_recs=[_stream()], psd_recs=[], event_rows=[], native_lsb={})
    flat = repr(out).lower()
    assert "pain" not in flat and "vas" not in flat and "nrs" not in flat
