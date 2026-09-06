"""Portable estimator tests, plus explicitly opted-in private model acceptance.

Generic math uses invented coefficients, never the participant calibration asset.
The two scientific acceptance tests require BRAVO_RUN_PRIVATE_MODEL_TESTS=1 and
the real reviewed RCS08 model at its normal runtime location. Without that opt-in
they remain explicitly unverified; opting in with a missing asset fails.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import psd_lsb_model as plm  # noqa: E402

PART = "SYNTHETIC08"


@pytest.fixture
def synthetic_model(tmp_path, monkeypatch):
    """Invented model: LSB = 80 * sqrt(power) at 26.4 Hz, 40 * sqrt at 8.8."""
    channel = {
        "fittable": True, "common_slope_b": 0.5,
        "bands": [{"center_hz": hz, "intercept_a": float(np.log10(gain)),
                   "LSB_at_1uV2": gain, "n": 10}
                  for hz, gain in [(8.8, 40), (26.4, 80)]],
    }
    model = {"schema": "psd_lsb_conversion/v1", "pipeline": {"special": {}},
             "channels": {"ZERO_THREE_RIGHT": channel, "ZERO_THREE_LEFT": channel,
                          "ONE_THREE_LEFT": {"channel_pooled_k": 10}}}
    (tmp_path / f"{PART}.json").write_text(json.dumps(model))
    monkeypatch.setattr(plm, "_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(plm, "_CACHE", {})


@pytest.fixture
def private_model(monkeypatch):
    if os.environ.get("BRAVO_RUN_PRIVATE_MODEL_TESTS") != "1":
        pytest.skip("Private calibration acceptance requires BRAVO_RUN_PRIVATE_MODEL_TESTS=1")
    monkeypatch.setattr(plm, "_CACHE", {})
    model = plm.load_model("RCS08")
    assert model is not None, "Private acceptance requested but reviewed RCS08 model is missing or invalid"
    return model


def test_model_loads_and_is_cached(synthetic_model):
    m = plm.load_model(PART)
    assert m is not None and m.get("schema") == "psd_lsb_conversion/v1"
    assert plm.load_model(PART) is m                      # cached identity
    assert plm.has_model(PART) and plm.has_model("synthetic08 ")  # canonicalized
    assert not plm.has_model("FAKE99")


def test_tier2_exact_band(synthetic_model):
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 1.0)
    assert e["available"] and e["estimated"] and e["tier"] == "band"
    assert e["model_center_hz"] == 26.4
    assert e["lsb"] == pytest.approx(80)


def test_tier2_power_dependent_gain(synthetic_model):
    """b != 1, so effective k = LSB/uV^2 changes with power (falls as power rises)."""
    e1 = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 1.0)
    e10 = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 10.0)
    assert e10["lsb"] > e1["lsb"]                          # more power -> more LSB
    assert e10["k_effective"] < e1["k_effective"]          # but lower per-uV^2 gain (sub-proportional)
    assert e10["lsb"] == pytest.approx(80 * np.sqrt(10))
    assert e10["k_effective"] == pytest.approx(8 * np.sqrt(10))


def test_tier3_nearest_frequency(synthetic_model):
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 15.0, 5.0)
    assert e["available"] and e["tier"] == "channel_freq"
    assert e["model_center_hz"] != 15.0 and "nearest" in e["note"]
    assert e["model_center_hz"] == 8.8
    assert e["lsb"] == pytest.approx(40 * np.sqrt(5))


def test_tier4_channel_pooled(synthetic_model):
    e = plm.estimate_lsb(PART, "ONE_THREE_LEFT", 9.0, 2.0)
    assert e["available"] and e["tier"] == "channel_pooled"
    assert e["slope_b"] == 1.0                             # proportional fallback
    assert abs(e["lsb"] - e["k_effective"] * 2.0) < 1e-6
    assert e["lsb"] == 20 and e["k_effective"] == 10


def test_none_when_unmodelable(synthetic_model):
    assert not plm.estimate_lsb(PART, "ONE_THREE_RIGHT", 9.0, 2.0)["available"]
    assert not plm.estimate_lsb("FAKE99", "ZERO_THREE_RIGHT", 26.4, 1.0)["available"]
    # estimated flag is present even on the failure path (so callers never read a None as measured)
    assert plm.estimate_lsb("FAKE99", "ZERO_THREE_RIGHT", 26.4, 1.0)["estimated"] is True


def test_array_input_mirrors_shape(synthetic_model):
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, [1.0, 2.0, 4.0])
    assert isinstance(e["lsb"], list) and len(e["lsb"]) == 3
    assert e["lsb"][0] < e["lsb"][1] < e["lsb"][2]         # monotone in power
    assert e["lsb"] == pytest.approx([80, 80 * np.sqrt(2), 160])


def test_plot_payload_shape(synthetic_model):
    pp = plm.model_plot_payload(PART)
    assert pp["available"]
    fittable = [c for c in pp["channels"] if c["fittable"]]
    assert len(fittable) >= 2                              # 0-3 Right, 0-3 Left
    for c in fittable:
        assert c["common_slope_b"] is not None and len(c["bands"]) >= 2
        for bd in c["bands"]:
            assert {"center_hz", "lsb_at_1uv2", "intercept_a", "n"} <= set(bd)


def test_8p8hz_cut_is_current_config_not_changepoint_date(private_model):
    """Guard the deliberate 8.8 Hz restriction so a future edit doesn't 'fix' it.

    The chronic 0-3R sensing config was reassigned off 8.8 Hz on 2025-12-05, but the
    8.8 Hz gain falls through a settling transient and only reaches stationarity from
    ~2026-02-15. The model cut is therefore >= 2026-03-01 (stable current-config regime),
    NOT the 2025-12-05 config-change date. If anyone moves the cut back to the change
    date, this test should make them justify it.
    """
    m = private_model
    note = (m["pipeline"]["special"] or {}).get("ZERO_THREE_RIGHT_8.8Hz", "")
    assert "2026-03-01" in note                              # the cut that is actually applied
    assert "2025-12-05" in note                              # change date is named and explained
    # the note must explain WHY the change date is not the cut (settling/transient)
    assert any(w in note.lower() for w in ("transient", "settl", "stationar"))
    # the frozen 8.8 Hz fit reflects the stable regime: gain ~1.77 log10 intercept (LSB@1uV2 ~ 59)
    z3r = m["channels"]["ZERO_THREE_RIGHT"]
    b88 = next(bd for bd in z3r["bands"] if abs(bd["center_hz"] - 8.8) < 1e-6)
    assert 1.70 < b88["intercept_a"] < 1.85                  # stable-regime intercept, not the ~2.0 transient


def test_highgamma_estimate_flagged_extrapolated(synthetic_model):
    """A high-gamma (55.5 Hz) LSB estimate must be flagged freq_extrapolated, not snapped silently.

    estimate_lsb snaps an out-of-range request to the nearest fitted band (here 26.4 Hz, ~29 Hz
    away). The validated PSD->LSB range is 7.8-28.3 Hz and the gain is NOT band-flat, so the snapped
    LSB is an untested extrapolation. The estimate must carry freq_extrapolated=True and say so in
    its note, so a clinician never deploys a high-gamma threshold as if it were calibrated.
    """
    est = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 55.5, 1.0)
    assert est["available"]
    assert est.get("freq_extrapolated") is True
    assert est.get("validated_hz_range") == [7.8, 28.3]
    assert "extrapolat" in est["note"].lower()
    # an in-range band must NOT be flagged
    est_ok = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 24.4, 1.0)
    assert est_ok["available"] and est_ok.get("freq_extrapolated") is False
    # boundary: just above the validated ceiling is extrapolated
    assert plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 28.4, 1.0).get("freq_extrapolated") is True


def test_no_impedance_gain_term_adopted(private_model):
    """Pin the decision to REJECT the electrode-impedance gain covariate (c=1.02).

    The term was significant only under naive OLS that pseudoreplicated 2985 epochs
    sharing 230 session-level impedance measurements; cluster-robust SE -> n.s.
    (p=0.26), the deployable >=2026-03-01 regime -> c=0.17 p=0.38, and the coefficient
    was unstable across specifications. The frozen model therefore carries NO impedance
    term, and the rejection is documented in the special block. If a future session
    re-adds an impedance gain term, this test should make them justify it on
    cluster-correct evidence.
    """
    m = private_model
    # the model must NOT have grown an impedance/gain-correction field on any band
    for ch in m["channels"].values():
        for bd in ch.get("bands", []):
            assert not any("imped" in str(k).lower() for k in bd), \
                "an impedance term leaked into a fitted band"
    # the rejection must be documented in the special block, with the cluster-robust reason
    special = m["pipeline"]["special"] or {}
    note = special.get("no_impedance_gain_term", "")
    assert note, "impedance-rejection rationale missing from special block"
    assert any(w in note.lower() for w in ("pseudoreplicat", "cluster", "n.s.")), \
        "rejection note must cite the pseudoreplication/cluster-robust evidence"
    assert "1.02" in note                                   # the originally claimed coefficient is named
