"""Regression tests for the frozen PSD->device-LSB conversion model + fallback estimator.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        -m pytest modules/Biomarkers/tests/test_psd_lsb_model.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import psd_lsb_model as plm  # noqa: E402

PART = "RCS08"


def test_model_loads_and_is_cached():
    m = plm.load_model(PART)
    assert m is not None and m.get("schema") == "psd_lsb_conversion/v1"
    assert plm.load_model(PART) is m                      # cached identity
    assert plm.has_model(PART) and plm.has_model("rcs08 ")  # canonicalized
    assert not plm.has_model("FAKE99")


def test_tier2_exact_band():
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 1.0)
    assert e["available"] and e["estimated"] and e["tier"] == "band"
    assert e["model_center_hz"] == 26.4
    # LSB at 1 uV^2 == 10**intercept; positive and in the device's plausible range.
    assert 40 < e["lsb"] < 120


def test_tier2_power_dependent_gain():
    """b != 1, so effective k = LSB/uV^2 changes with power (falls as power rises)."""
    e1 = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 1.0)
    e10 = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, 10.0)
    assert e10["lsb"] > e1["lsb"]                          # more power -> more LSB
    assert e10["k_effective"] < e1["k_effective"]          # but lower per-uV^2 gain (sub-proportional)


def test_tier3_nearest_frequency():
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 15.0, 5.0)
    assert e["available"] and e["tier"] == "channel_freq"
    assert e["model_center_hz"] != 15.0 and "nearest" in e["note"]


def test_tier4_channel_pooled():
    e = plm.estimate_lsb(PART, "ONE_THREE_LEFT", 9.0, 2.0)
    assert e["available"] and e["tier"] == "channel_pooled"
    assert e["slope_b"] == 1.0                             # proportional fallback
    assert abs(e["lsb"] - e["k_effective"] * 2.0) < 1e-6


def test_none_when_unmodelable():
    assert not plm.estimate_lsb(PART, "ONE_THREE_RIGHT", 9.0, 2.0)["available"]
    assert not plm.estimate_lsb("FAKE99", "ZERO_THREE_RIGHT", 26.4, 1.0)["available"]
    # estimated flag is present even on the failure path (so callers never read a None as measured)
    assert plm.estimate_lsb("FAKE99", "ZERO_THREE_RIGHT", 26.4, 1.0)["estimated"] is True


def test_array_input_mirrors_shape():
    e = plm.estimate_lsb(PART, "ZERO_THREE_RIGHT", 26.4, [1.0, 2.0, 4.0])
    assert isinstance(e["lsb"], list) and len(e["lsb"]) == 3
    assert e["lsb"][0] < e["lsb"][1] < e["lsb"][2]         # monotone in power


def test_plot_payload_shape():
    pp = plm.model_plot_payload(PART)
    assert pp["available"]
    fittable = [c for c in pp["channels"] if c["fittable"]]
    assert len(fittable) >= 2                              # 0-3 Right, 0-3 Left
    for c in fittable:
        assert c["common_slope_b"] is not None and len(c["bands"]) >= 2
        for bd in c["bands"]:
            assert {"center_hz", "lsb_at_1uv2", "intercept_a", "n"} <= set(bd)


def test_8p8hz_cut_is_current_config_not_changepoint_date():
    """Guard the deliberate 8.8 Hz restriction so a future edit doesn't 'fix' it.

    The chronic 0-3R sensing config was reassigned off 8.8 Hz on 2025-12-05, but the
    8.8 Hz gain falls through a settling transient and only reaches stationarity from
    ~2026-02-15. The model cut is therefore >= 2026-03-01 (stable current-config regime),
    NOT the 2025-12-05 config-change date. If anyone moves the cut back to the change
    date, this test should make them justify it.
    """
    m = plm.load_model(PART)
    note = (m["pipeline"]["special"] or {}).get("ZERO_THREE_RIGHT_8.8Hz", "")
    assert "2026-03-01" in note                              # the cut that is actually applied
    assert "2025-12-05" in note                              # change date is named and explained
    # the note must explain WHY the change date is not the cut (settling/transient)
    assert any(w in note.lower() for w in ("transient", "settl", "stationar"))
    # the frozen 8.8 Hz fit reflects the stable regime: gain ~1.77 log10 intercept (LSB@1uV2 ~ 59)
    z3r = m["channels"]["ZERO_THREE_RIGHT"]
    b88 = next(bd for bd in z3r["bands"] if abs(bd["center_hz"] - 8.8) < 1e-6)
    assert 1.70 < b88["intercept_a"] < 1.85                  # stable-regime intercept, not the ~2.0 transient


def test_highgamma_estimate_flagged_extrapolated():
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


def test_no_impedance_gain_term_adopted():
    """Pin the decision to REJECT the electrode-impedance gain covariate (c=1.02).

    The term was significant only under naive OLS that pseudoreplicated 2985 epochs
    sharing 230 session-level impedance measurements; cluster-robust SE -> n.s.
    (p=0.26), the deployable >=2026-03-01 regime -> c=0.17 p=0.38, and the coefficient
    was unstable across specifications. The frozen model therefore carries NO impedance
    term, and the rejection is documented in the special block. If a future session
    re-adds an impedance gain term, this test should make them justify it on
    cluster-correct evidence.
    """
    m = plm.load_model(PART)
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


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"PASS {fn.__name__}")
        except Exception:                                  # noqa: BLE001
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
