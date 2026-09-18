"""Synthetic source immutability and scientific-equivalence checks for bounded speed ports."""
import copy

import numpy as np
import pandas as pd
import pytest

from modules.MedtronicPercept import Percept
from modules.Biomarkers import adapter


def td_stream(gap=False):
    return {"GlobalSequences": "1,2,4" if gap else "1,2,3",
            "GlobalPacketSizes": "2,2,2", "TicksInMses": "0,8,24" if gap else "0,8,16",
            "TimeDomainData": [1., 2., 3., 4., 5., 6.], "SampleRateInHz": "250",
            "FirstPacketDateTime": "2026-01-01T00:00:00Z", "Channel": "ONE_THREE_LEFT",
            "Descriptor": {"Nested": [1, {"keep": "original"}]}}


def power_stream():
    return {"FirstPacketDateTime": "2026-01-01T00:00:00Z", "SampleRateInHz": "5",
            "Channel": "ONE_THREE_LEFT", "Descriptor": {"Nested": [1, {"keep": "original"}]},
            "LfpData": [{"Left": {"LFP": i + 1., "mA": 1.},
                         "Right": {"LFP": i + 2., "mA": 2.}, "Seq": i, "TicksInMs": i * 200}
                        for i in range(4)]}


def assert_nested_equal(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_nested_equal(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected):
            assert_nested_equal(a, b)
    elif isinstance(expected, np.ndarray):
        np.testing.assert_array_equal(actual, expected, strict=True)
    else:
        assert actual == expected


@pytest.mark.parametrize("method,keys", [
    ("extractTimeDomainStreamingData", ["BrainSenseTimeDomain"]),
    ("extractPowerDomainStreamingData", ["BrainSenseLfp"]),
    ("extractStreamingData", ["BrainSenseTimeDomain", "BrainSenseLfp"]),
    ("extractIndefiniteStreaming", ["IndefiniteStreaming"]),
    ("extractBrainSenseSurvey", ["LfpMontageTimeDomain"]),
    ("extractSignalCalibration", ["SenseChannelTests", "CalibrationTests"]),
])
@pytest.mark.parametrize("gap", [False, True])
def test_raw_stream_copy_matches_deepcopy_and_isolates_outputs(monkeypatch, method, keys, gap):
    source = {key: [power_stream() if key == "BrainSenseLfp" else td_stream(gap)] for key in keys}
    untouched = copy.deepcopy(source)
    fn = getattr(Percept, method)
    actual = fn(source, {})
    assert source == untouched
    with monkeypatch.context() as patch:
        patch.setattr(Percept, "_copyStreamList", copy.deepcopy)
        expected = fn(copy.deepcopy(source), {})
    assert_nested_equal(actual, expected)
    # Downstream edits to decoded samples or retained metadata cannot alter originals.
    for streams in actual.values():
        for stream in streams:
            stream["Descriptor"]["Nested"][1]["keep"] = "changed"
            stream.get("Data", stream.get("Power"))[0] = 123
    assert source == untouched


def test_raw_samples_are_not_traversed_but_metadata_is_deepcopied():
    class ReadOnlySamples(list):
        def __deepcopy__(self, memo):
            raise AssertionError("large raw samples must not be traversed")
    samples = ReadOnlySamples([1., 2.])
    source = [{"TimeDomainData": samples, "LfpData": samples, "metadata": {"a": [1]}}]
    out = Percept._copyStreamList(source)
    assert out[0]["TimeDomainData"] is samples
    assert out[0]["LfpData"] is samples
    out[0]["metadata"]["a"].append(2)
    assert source[0]["metadata"] == {"a": [1]}
    assert Percept._copyStreamList([None, [1]]) == [None, [1]]
    nested = {"metadata": {"a": [1]}}
    assert Percept._copyStreamList(nested) == nested
    assert Percept._copyStreamList(nested) is not nested


def chronic_reference(pro, chronic, metrics):
    """Accepted pre-port daily reduction, retained as the numerical oracle."""
    df = pro.copy()
    times = pd.to_datetime(df.get("_pro_time_utc", df["date_time_s1_daily"]), errors="coerce")
    df["_date"] = adapter.local_calendar_day(times, naive_is_local="_pro_time_utc" not in pro)
    groups = dict(tuple(df.groupby("_date")))
    rows = []
    for index, epoch in enumerate(chronic["Time"]):
        ts = adapter._to_datetime(epoch)
        group = groups.get(adapter.local_calendar_day(ts))
        row = {"time": ts, "lfp": float(chronic["Data"][index, 0]),
               "stim_amplitude": float(chronic["Data"][index, 1]) if chronic["Data"].shape[1] > 1 else np.nan}
        for metric in metrics:
            row[metric] = group[metric].mean() if group is not None and metric in group else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


@pytest.mark.parametrize("canonical", [False, True])
@pytest.mark.parametrize("dtype", ["float64", "Float64"])
@pytest.mark.parametrize("amplitude", [False, True])
def test_chronic_broadcast_exact_daily_means_dates_order_and_missing(canonical, dtype, amplitude):
    # DST transition, UTC-midnight crossover, unsorted samples and absent days.
    dates = ["2026-11-01T07:30:00", "2026-11-01T08:30:00", "2026-11-02T01:00:00", None]
    pro = pd.DataFrame({"date_time_s1_daily": dates, "score": pd.Series([1e16, 1., -1e16, np.nan], dtype=dtype),
                        "all_missing": pd.Series([np.nan] * 4, dtype=dtype)})
    if canonical:
        pro["_pro_time_utc"] = dates
    epochs = [pd.Timestamp(t, tz="UTC").timestamp() for t in
              ["2026-11-02T01:30:00", "2026-11-01T07:45:00", "2026-11-03T01:30:00", "2026-11-01T08:45:00"]]
    chronic = {"Time": epochs, "Data": np.arange(8., dtype=float).reshape(4, 2)[:, :2 if amplitude else 1]}
    metrics = ["absent", "score", "all_missing"]
    expected = chronic_reference(pro, chronic, metrics)
    actual = adapter.align_pros(pro, target="chronic", chronic=chronic, metrics=metrics)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def test_chronic_reduces_once_per_day_instead_of_once_per_sample(monkeypatch):
    pro = pd.DataFrame({"date_time_s1_daily": ["2026-01-01T12:00:00", "2026-01-01T13:00:00"], "score": [1., 3.]})
    calls = []
    original = pd.Series.mean
    def count(self, *args, **kwargs):
        calls.append(self.name)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(pd.Series, "mean", count)
    epoch = pd.Timestamp("2026-01-01T22:00:00Z").timestamp()
    actual = adapter.align_pros(pro, target="chronic", chronic={"Time": [epoch] * 1000, "Data": np.zeros((1000, 1))}, metrics=["score", "absent"])
    assert calls == ["score"]
    assert actual.score.tolist() == [2.] * 1000
    empty = adapter.align_pros(pro, target="chronic", chronic={"Time": [], "Data": np.zeros((0, 1))}, metrics=["score"])
    assert empty.empty and len(empty.columns) == 0


@pytest.mark.parametrize("target", ["session", "chronic", "unsupported"])
def test_alignment_rejects_missing_required_inputs(target):
    pro = pd.DataFrame({"date_time_s1_daily": ["2026-01-01"], "score": [1.]})
    with pytest.raises(ValueError):
        adapter.align_pros(pro, target=target, metrics=["score"])


@pytest.mark.parametrize("tolerance", [None, 60])
def test_session_alignment_preserves_explicit_amplitude_and_invalid_times(tolerance):
    pro = pd.DataFrame({"date_time_s1_daily": ["2026-01-01T12:00:00"], "score": [1.]})
    out = adapter.align_pros(pro, target="session", recordings=[{"StartTime": None}],
                             metrics=["score"], stim_amplitudes=[2.5], match_tolerance_min=tolerance)
    assert out.loc[0, "stim_amplitude"] == 2.5
    assert not out.loc[0, "matched"]
    assert pd.isna(out.loc[0, "score_mean"])
