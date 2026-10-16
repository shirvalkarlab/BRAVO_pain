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


RISES, FALLS = "band power rises as current rises", "band power falls as current rises"
WORSEN = "raising stimulation current on this contact is expected to worsen pain through this band"
RELIEVE = "raising stimulation current on this contact is expected to relieve pain through this band"
MORE = "higher band power is associated with more pain"
LESS = "higher band power is associated with less pain"


@pytest.mark.parametrize("within,r,pain_direction,implied", [
    (RISES, 0.4, MORE, WORSEN),
    (RISES, -0.5, LESS, RELIEVE),
    (FALLS, 0.3, MORE, RELIEVE),
    (FALLS, -0.2, LESS, WORSEN),
], ids=["rises_more_pain_worsens", "rises_less_pain_relieves", "falls_more_pain_relieves",
        "falls_less_pain_worsens"])
def test_the_two_directions_combine_into_the_implied_control_direction(within, r, pain_direction,
                                                                        implied):
    out = DC.implied_control_direction(_wv(within), _row(r))
    assert out["cross_visit_pain_direction"] == pain_direction
    assert out["implied_control_direction"] == implied
    assert out["reason"] is None


@pytest.mark.parametrize("wv,row,reason,check", [
    # the correlation is never even inspected once the within-visit link is missing
    (_wv("no straight-line movement detected across the currents tested"), _row(0.4), "within-visit",
     lambda out: np.isnan(out["cross_visit_pain_correlation_r"])),
    (_wv("not assessed"), _row(0.4), "not assessed", None),
    (_wv(RISES), None, "no cross-visit correlation", None),
    # the correlation value itself is still reported, just not acted on
    (_wv(RISES), _row(0.6, p=0.34), "not statistically significant",
     lambda out: out["cross_visit_pain_correlation_r"] == 0.6),
    (_wv(RISES), _row(float("nan"), p=0.01), "could not be computed", None),
], ids=["no_within_visit_movement", "within_visit_not_assessed", "no_correlation_row",
        "correlation_not_significant", "nan_correlation"])
def test_a_missing_link_is_not_assessed_with_its_own_reason(wv, row, reason, check):
    out = DC.implied_control_direction(wv, row)
    assert out["implied_control_direction"] == "not assessed"
    assert reason in out["reason"]
    assert check is None or check(out)


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
