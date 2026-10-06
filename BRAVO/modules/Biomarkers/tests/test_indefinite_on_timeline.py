"""Indefinite streaming on the recording timeline (item P-11, the PI's go-ahead 2026-10-06).

Indefinite streaming records every sensing pair at once, stimulation off, with no band setting.
The timeline now draws one modelled band-power point per recording per pair: the median, over the
recording's usable 3-second chunks (the heat maps' own checks: at most 10% missing, no sample at
the rail), of the time-domain transform at the band in force on that pair at that time (the last
band the device sensed there before the recording), else the pair's configured band. Each pair
stays its own; the value is modelled, never sensed, and never sets the lane's scale.
"""
import sys
import pathlib

import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers.routines import availability as av
from modules.Biomarkers.routines import analytics

T0 = 1_760_000_000.0
FS = 250.0


def _sine(hz, n, amp=20.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FS
    return amp * np.sin(2 * np.pi * hz * t) + rng.normal(0, 2.0, n)


def _indefinite(n=FS * 60, start=T0):
    n = int(n)
    data = np.column_stack([_sine(12.7, n, seed=1), _sine(20.0, n, seed=2)])
    return {"ChannelNames": ["ZERO_THREE_LEFT", "ONE_THREE_LEFT"], "Data": data,
            "Missing": np.zeros_like(data), "SamplingRate": FS, "StartTime": start,
            "Duration": n / FS, "RecordingType": "MedtronicIndefiniteStream"}


def _powerdomain(hz, start):
    return {"ChannelNames": ["ZERO_THREE_LEFT Power"], "Data": np.full((20, 1), 500.0),
            "Missing": np.zeros((20, 1)), "SamplingRate": 2.0, "StartTime": start, "Duration": 10.0,
            "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": hz}}}}}


def _series(indexed, **kw):
    if indexed:
        return av.lsb_series(kw.pop("chronic", []), kw.pop("pd", []), **kw)
    return av._lsb_series_scan(kw.pop("chronic", []), kw.pop("pd", []), **kw)


def _ind_points(out, ch):
    d = out.get(ch) or {"method": []}
    return [i for i, m in enumerate(d["method"]) if m and "indefinite" in m]


def test_one_modelled_point_per_pair_tagged_and_never_sensed():
    out = _series(True, indefinite_td_recordings=[_indefinite()],
                  sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7, "ONE_THREE_LEFT": 19.53})
    for ch in ("ZERO_THREE_LEFT", "ONE_THREE_LEFT"):
        idx = _ind_points(out, ch)
        assert len(idx) == 1
        i = idx[0]
        assert out[ch]["modeled"][i] is True and out[ch]["source"][i] == "psd_modeled"
        assert out[ch]["method"][i].startswith("td_transform_x_k=")
        assert out[ch]["t"][i] == T0


def test_the_value_is_the_median_of_the_usable_chunks_at_that_band():
    rec = _indefinite()
    out = _series(True, indefinite_td_recordings=[rec], sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7})
    i = _ind_points(out, "ZERO_THREE_LEFT")[0]
    vals = av._td_tile_values(rec["Data"][:, 0], np.zeros(rec["Data"].shape[0], bool), FS,
                              np.array([12.7]), window_s=analytics.RAW_LSB_WINDOW_SECONDS, half=2.5,
                              max_missing_frac=0.10, saturation_uv=av.PRO_LSB_SATURATION_UV)
    expect = float(np.nanmedian(vals["lsb"][vals["passes"], 0]))
    assert out["ZERO_THREE_LEFT"]["y"][i] == expect


def test_the_band_is_the_one_in_force_on_that_pair_then():
    pd = [_powerdomain(9.77, T0 - 3600), _powerdomain(26.37, T0 + 3600)]
    out = _series(True, pd=pd, indefinite_td_recordings=[_indefinite()],
                  sensing_hz_by_channel={"ZERO_THREE_LEFT": 26.37})
    i = _ind_points(out, "ZERO_THREE_LEFT")[0]
    assert out["ZERO_THREE_LEFT"]["center_hz"][i] == av.snap_freq(9.77)
    assert "band=in_force" in out["ZERO_THREE_LEFT"]["method"][i]


def test_with_no_earlier_band_the_configured_band_is_used_and_said():
    out = _series(True, indefinite_td_recordings=[_indefinite()],
                  sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7})
    i = _ind_points(out, "ZERO_THREE_LEFT")[0]
    assert out["ZERO_THREE_LEFT"]["center_hz"][i] == av.snap_freq(12.7)
    assert "band=configured" in out["ZERO_THREE_LEFT"]["method"][i]
    assert _ind_points(out, "ONE_THREE_LEFT") == []        # no band known at all: no point


def test_a_recording_with_no_usable_chunk_gives_no_point():
    rec = _indefinite()
    rec["Data"][:, 0] = 5000.0                               # every sample at the rail
    rec["Missing"][:, 1] = 1                                 # every sample missing
    out = _series(True, indefinite_td_recordings=[rec],
                  sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7, "ONE_THREE_LEFT": 19.53})
    assert _ind_points(out, "ZERO_THREE_LEFT") == [] and _ind_points(out, "ONE_THREE_LEFT") == []


def test_the_indexed_and_reference_paths_agree():
    kw = dict(indefinite_td_recordings=[_indefinite()],
              sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7, "ONE_THREE_LEFT": 19.53})
    a = _series(True, pd=[_powerdomain(9.77, T0 - 3600)], **dict(kw))
    b = _series(False, pd=[_powerdomain(9.77, T0 - 3600)], **dict(kw))
    assert a == b


def test_without_indefinite_nothing_changes():
    pd = [_powerdomain(9.77, T0 - 3600)]
    assert _series(True, pd=list(pd)) == _series(True, pd=list(pd), indefinite_td_recordings=[])


def test_the_overview_keeps_them_off_the_scale_and_out_of_the_sessions():
    pd = [_powerdomain(9.77, T0 - 3600)]
    base = av.lsb_overview(_series(True, pd=list(pd)))
    ov = av.lsb_overview(_series(True, pd=list(pd), indefinite_td_recordings=[_indefinite()],
                                 sensing_hz_by_channel={"ZERO_THREE_LEFT": 12.7}))
    c = ov["ZERO_THREE_LEFT"]
    assert (c["y_lo"], c["y_hi"]) == (base["ZERO_THREE_LEFT"]["y_lo"], base["ZERO_THREE_LEFT"]["y_hi"])
    assert c["sessions"] == base["ZERO_THREE_LEFT"]["sessions"]
    assert any("indefinite" in (m["method"] or "") for m in c["modeled"])


def test_the_saved_timeline_is_rebuilt_under_the_new_rule():
    src = (_BRAVO_ROOT / "modules" / "Biomarkers" / "bravo_service.py").read_text()
    assert '_ACQ_TIMELINE_RULE_VERSION = "v3_indefinite_modelled' in src


def test_the_chronic_records_own_band_and_pair_schedule_count_as_in_force():
    chronic = {"ChannelNames": ["LeftHemisphere LFP", "LeftHemisphere Amplitude"],
               "Time": np.array([T0 - 7200.0, T0 - 600.0]), "Data": np.array([[400.0, 2.0], [410.0, 2.0]]),
               "SamplingRate": -1, "StartTime": T0 - 7200.0, "Duration": 6600.0,
               "FreqScheduleHz": [[T0 - 9000.0, 22.46], [T0 - 4000.0, 11.72]],
               "ContactSchedule": [[T0 - 9000.0, "1-3"], [T0 - 4000.0, "0-3"]]}
    hist = av._band_history([chronic], [])
    assert hist["ZERO_THREE_LEFT"] == [(T0 - 4000.0, 11.72)]
    assert hist["ONE_THREE_LEFT"] == [(T0 - 9000.0, 22.46)]


def test_one_band_per_pair_is_not_used_for_the_band_in_force():
    # power_center_freqs keeps the LAST run's band for a pair; the run before the recording was 9.77
    pd = [_powerdomain(9.77, T0 - 3600), _powerdomain(26.37, T0 + 3600)]
    assert analytics.power_center_freqs(pd)["ZERO_THREE_LEFT"] == 26.37
    assert av._band_history([], pd)["ZERO_THREE_LEFT"] == [(T0 - 3600, 9.77), (T0 + 3600, 26.37)]
