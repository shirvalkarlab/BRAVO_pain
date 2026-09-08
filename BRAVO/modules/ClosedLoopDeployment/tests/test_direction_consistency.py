"""The consistency check: combining the pooled within-visit dose-response direction with the
cross-visit band-power-to-pain correlation into one explicit implied control direction.
"""
import numpy as np
import pytest

from ClosedLoopDeployment import direction_consistency as DC


def _wv(direction, slope=1.0, p=0.01, n=30, n_visits=5):
    return dict(pooled_direction=direction, pooled_slope_per_mA=slope, pooled_slope_p=p,
                n=n, n_visits=n_visits)


def _row(r, p=0.01, band_center_hz=12.5):
    return dict(pearson_r=r, p_selection_aware=p, band_center_hz=band_center_hz)


def test_power_rises_with_current_and_higher_power_means_more_pain_so_raising_current_worsens_pain():
    out = DC.implied_control_direction(_wv("band power rises as current rises"), _row(0.4))
    assert out["cross_visit_pain_direction"] == "higher band power is associated with more pain"
    assert out["implied_control_direction"] == (
        "raising stimulation current on this contact is expected to worsen pain through this band")
    assert out["reason"] is None


def test_power_rises_with_current_and_higher_power_means_less_pain_so_raising_current_relieves_pain():
    out = DC.implied_control_direction(_wv("band power rises as current rises"), _row(-0.5))
    assert out["cross_visit_pain_direction"] == "higher band power is associated with less pain"
    assert out["implied_control_direction"] == (
        "raising stimulation current on this contact is expected to relieve pain through this "
        "band")


def test_power_falls_with_current_and_higher_power_means_more_pain_so_raising_current_relieves_pain():
    out = DC.implied_control_direction(_wv("band power falls as current rises"), _row(0.3))
    assert out["implied_control_direction"] == (
        "raising stimulation current on this contact is expected to relieve pain through this "
        "band")


def test_power_falls_with_current_and_higher_power_means_less_pain_so_raising_current_worsens_pain():
    out = DC.implied_control_direction(_wv("band power falls as current rises"), _row(-0.2))
    assert out["implied_control_direction"] == (
        "raising stimulation current on this contact is expected to worsen pain through this band")


def test_no_within_visit_movement_is_not_assessed_with_a_specific_reason():
    out = DC.implied_control_direction(
        _wv("no straight-line movement detected across the currents tested"), _row(0.4))
    assert out["implied_control_direction"] == "not assessed"
    assert "within-visit" in out["reason"]
    # the correlation is never even inspected once the within-visit link is missing
    assert np.isnan(out["cross_visit_pain_correlation_r"])


def test_within_visit_not_assessed_is_not_assessed():
    out = DC.implied_control_direction(_wv("not assessed"), _row(0.4))
    assert out["implied_control_direction"] == "not assessed"
    assert "not assessed" in out["reason"]


def test_no_correlation_row_is_not_assessed():
    out = DC.implied_control_direction(_wv("band power rises as current rises"), None)
    assert out["implied_control_direction"] == "not assessed"
    assert "no cross-visit correlation" in out["reason"]


def test_correlation_not_significant_is_not_assessed():
    out = DC.implied_control_direction(_wv("band power rises as current rises"),
                                       _row(0.6, p=0.34))
    assert out["implied_control_direction"] == "not assessed"
    assert "not statistically significant" in out["reason"]
    # the correlation value itself is still reported, just not acted on
    assert out["cross_visit_pain_correlation_r"] == 0.6


def test_nan_correlation_is_not_assessed():
    out = DC.implied_control_direction(_wv("band power rises as current rises"),
                                       _row(float("nan"), p=0.01))
    assert out["implied_control_direction"] == "not assessed"
    assert "could not be computed" in out["reason"]


def test_empty_or_none_within_visit_dict_does_not_raise():
    out = DC.implied_control_direction(None, _row(0.4))
    assert out["implied_control_direction"] == "not assessed"
    assert out["within_visit_direction"] == "not assessed"
    out2 = DC.implied_control_direction({}, None)
    assert out2["implied_control_direction"] == "not assessed"


def test_correlation_row_for_band_matches_on_centre_and_contact():
    grid = {
        "available": True,
        "band_time_sweep": {
            "ONE_THREE_LEFT": {"best_correlation_rows": [_row(0.2, band_center_hz=10.5),
                                                          _row(-0.3, band_center_hz=12.5)]},
        },
    }
    row = DC.correlation_row_for_band(grid, "ONE_THREE_LEFT", 12.5)
    assert row is not None and row["pearson_r"] == -0.3
    assert DC.correlation_row_for_band(grid, "ONE_THREE_LEFT", 99.5) is None
    assert DC.correlation_row_for_band(grid, "ZERO_TWO_LEFT", 12.5) is None


def test_correlation_row_for_band_handles_an_unavailable_or_missing_grid():
    assert DC.correlation_row_for_band(None, "ONE_THREE_LEFT", 12.5) is None
    assert DC.correlation_row_for_band({"available": False}, "ONE_THREE_LEFT", 12.5) is None
    assert DC.correlation_row_for_band({"available": True, "band_time_sweep": {}},
                                       "ONE_THREE_LEFT", 12.5) is None


def test_for_band_wires_the_pooled_shape_and_the_correlation_lookup_together(monkeypatch):
    from ClosedLoopDeployment import amplitude_effect as AE

    called = {}

    def fake_pooled(build, band_center_hz, sensing_contact, min_points=8):
        called["build"] = build
        called["band_center_hz"] = band_center_hz
        called["sensing_contact"] = sensing_contact
        return _wv("band power rises as current rises")

    monkeypatch.setattr(AE, "pooled_shape_for_band", fake_pooled)
    grid = {"available": True,
            "band_time_sweep": {"ONE_THREE_LEFT": {"best_correlation_rows": [_row(0.5, band_center_hz=12.5)]}}}
    out = DC.for_band({"comparisons": []}, grid, "ONE_THREE_LEFT", 12.5)
    assert called["band_center_hz"] == 12.5
    assert called["sensing_contact"] == "ONE_THREE_LEFT"
    assert out["sensing_contact"] == "ONE_THREE_LEFT"
    assert out["band_center_hz"] == 12.5
    assert out["implied_control_direction"] == (
        "raising stimulation current on this contact is expected to worsen pain through this band")
