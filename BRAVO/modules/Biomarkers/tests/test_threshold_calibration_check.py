"""Check the PSD-to-LSB route against threshold band-power streams from the same export,
contact pair and sensing frequency. Compare each stream's median native LSB with
the bridge prediction. This is a comparison of device values, not a fitted model;
private historical agreement statistics are not test fixtures.

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
