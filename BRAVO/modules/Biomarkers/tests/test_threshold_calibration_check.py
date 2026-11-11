"""The threshold band-power streams check the PSD->LSB route against the device's own LSB (the PI,
2026-10-05: "wired to sanity check the PSD->LSB calibration including the visuals", decision 447).
Each stream's measured LSB (median of its readings) is set beside the LSB the bridge predicts from a
device spectrum of the same export on the same contact pair at the stream's sensing frequency. On the
RCS08 exports: measured / predicted median 1.002 from the signal check (n = 74), 1.066 from the
montage (n = 60). Device values only; nothing is fitted.

Values: per source, n, the median ratio and its 10th-90th percentiles; a stream without a prediction
from a source is not counted for it; the rows are passed through for the figure."""
from modules.Biomarkers.routines import calibration as cal


def test_summary_per_source():
    rows = [{"measured_lsb": 100.0, "predicted_lsb": {"signal check": 100.0, "montage": 50.0}},
            {"measured_lsb": 80.0, "predicted_lsb": {"signal check": 40.0}},
            {"measured_lsb": 60.0, "predicted_lsb": {"signal check": 120.0, "montage": 60.0}},
            {"measured_lsb": float("nan"), "predicted_lsb": {"signal check": 10.0}}]
    out = cal.threshold_check(rows)
    sc, mo = out["by_source"]["signal check"], out["by_source"]["montage"]
    assert sc["n"] == 3 and sc["median_ratio"] == 1.0
    assert mo["n"] == 2 and mo["median_ratio"] == 1.5
    assert out["n_streams"] == 4 and len(out["rows"]) == 4


def test_no_streams_is_said_plainly():
    out = cal.threshold_check([])
    assert out["available"] is False and "no threshold" in out["reason"]
