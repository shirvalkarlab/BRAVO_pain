"""The Biomarkers page's bottom-right calibration panel draws the calibration IN EFFECT, from the
recipe and the tables in `routines/calibration.py`, not the frozen June log-log model (decision 212,
the PI, 2026-09-20: "update the Biomarkers page frontend so the bottom calibration plots use the
latest calibration constants").

Until now `/api/queryPsdLsbConversionModel` served the frozen June model's plot payload: the v1 asset's
per-band gain anchors (LSB at 1 uV^2, fitted on log10 power, decisions 11 and 18) and per-channel
slopes 0.85 / 0.52 -- numbers that are neither the constant the platform converts with (345.59 since
decision 211) nor derived on raw power, and a model no calculation has read since the fallback was
removed on 2026-06-28. The panel's caption also said it was "the fallback the threshold estimator
uses", which has been false since that day.

Now the endpoint serves `calibration.panel_payload`: every paired block with its status under the
adopted recipe (kept / gated / flagged / unusable), the recipe's fit, the bridge ratio per centre and
per contact pair, and the constants in effect read from `analytics` (never typed into the payload).
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A  # noqa: E402
from Biomarkers.routines import calibration as C  # noqa: E402


def _payload():
    return C.panel_payload("RCS08", deployed_k=A.LSB_PER_UV2_TRANSFORM,
                           deployed_bridge_ratio=A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO,
                           deployed_bridge=A.LSB_PER_DEVICE_PSD)


def test_every_block_carries_its_status_under_the_adopted_recipe():
    """170 rows: 3 with no usable pair, 11 that fail the block gate, 23 flagged by the 5-MAD ratio
    rule, 133 kept -- the same counts `transform_k` reports, block by block."""
    st = C.block_status(C.load_blocks("RCS08"), target="all")
    assert len(st) == 170
    counts = {s: sum(1 for x in st if x == s) for s in ("kept", "gated", "flagged", "unusable")}
    assert counts == {"kept": 133, "gated": 11, "flagged": 23, "unusable": 3}, counts
    fit = C.transform_k(C.load_blocks("RCS08"), target="all")
    assert counts["kept"] == fit["n"] and counts["flagged"] == fit["n_flagged_by_rule"]
    assert counts["gated"] == fit["n_before_gate"] - fit["n_after_gate"]


def test_the_short_block_of_july_is_gated_and_the_block_is_named_by_date_channel_and_centre():
    rows = C.load_blocks("RCS08")
    st = C.block_status(rows, target="all")
    i = next(k for k, r in enumerate(rows)
             if r["timestamp"].startswith("2026-07-07T20:49:53") and r["side"] == "Right")
    assert st[i] == "gated"
    p = _payload()
    b = next(b for b in p["transform"]["blocks"] if b["timestamp"].startswith("2026-07-07T20:49:53")
             and b["side"] == "Right")
    assert b["status"] == "gated" and b["channel"] and b["center_hz"] > 0
    assert round(b["uv2"], 0) == 17 and round(b["lsb"], 0) == 1197


def test_the_payload_carries_the_recipe_fit_and_the_constants_in_effect_from_analytics():
    p = _payload()
    assert p["available"] is True and p["participant"] == "RCS08"
    assert p["table_date"] == "2026-09-03"
    assert p["deployed"] == {"k": A.LSB_PER_UV2_TRANSFORM,
                             "bridge_ratio": A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO,
                             "bridge_lsb_per_device_uv2": A.LSB_PER_DEVICE_PSD}
    t = p["transform"]
    assert t["n"] == 133 and round(t["k"], 2) == round(A.LSB_PER_UV2_TRANSFORM, 2)
    assert round(t["r"], 3) == 0.992
    assert t["gate"] == {"min_td_seconds": 3.0, "min_lfp_points": 6}
    assert t["outlier_rule"] == C.OUTLIER_RULE
    assert len(t["blocks"]) == 170
    for b in t["blocks"]:
        assert set(b) >= {"uv2", "lsb", "side", "channel", "center_hz", "date", "timestamp", "status"}
        assert b["status"] in ("kept", "gated", "flagged", "unusable")
    # the June anchor is reported beside it, as the reference the table reproduces, from the table
    assert round(t["june_reference"]["k"], 2) == 352.62 and t["june_reference"]["n"] == 131


def test_the_bridge_block_is_the_raw_median_per_centre_and_per_contact_pair():
    b = _payload()["bridge"]
    assert b["n_pairs"] == 26334 and b["n"] == 25790 and round(b["ratio"], 3) == 4.755
    assert b["outlier_rule"] == C.BRIDGE_OUTLIER_RULE
    assert len(b["per_centre"]) == 21 and [x["center_hz"] for x in b["per_centre"]] == sorted(
        x["center_hz"] for x in b["per_centre"])
    assert len(b["per_channel"]) == 12
    assert len(b["per_channel_centre"]) == 12 * 21
    for x in b["per_centre"] + b["per_channel"]:
        assert 4.6 < x["ratio"] < 4.9 and x["n"] > 0, x
    for x in b["per_channel_centre"]:
        assert {"channel", "center_hz", "ratio", "n"} <= set(x)


def test_the_payload_is_json_and_takes_no_logarithm():
    s = json.dumps(_payload())
    assert "NaN" not in s and "Infinity" not in s
    src = open(C.__file__).read()
    assert "log10" not in src and "np.log" not in src


def test_the_frozen_june_model_is_gone():
    """The PI, 2026-09-21: delete the frozen June log-log model. Drawn by no page since decision
    212, read by no calculation since 2026-06-28. The module, its asset folder and its test are
    gone; nothing under Biomarkers imports it; the extrapolation guard keeps its own range."""
    import importlib
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    assert not os.path.exists(os.path.join(root, "routines", "psd_lsb" + "_model.py"))
    assert not os.path.exists(os.path.join(root, "data", "psd_lsb" + "_models"))
    assert not os.path.exists(os.path.join(root, "tests", "test_psd_lsb" + "_model.py"))
    try:
        importlib.import_module("Biomarkers.routines.psd_lsb" + "_model")
    except ImportError:
        pass
    else:
        raise AssertionError("the frozen model module still imports")
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                src = open(os.path.join(dirpath, f)).read()
                assert ("psd_lsb" + "_model") not in src, os.path.join(dirpath, f)


def test_the_committed_band_refit_names_the_constant_in_effect_beside_its_own():
    """The bottom-left panel (the committed band's own refit) reports `k_in_effect` so the page
    can draw the constant the platform converts with beside the band's own fit, from the server."""
    rng = np.random.default_rng(0)
    P = rng.gamma(2.0, 0.5, 60)
    L = 340.0 * P * rng.gamma(50.0, 1 / 50.0, 60)
    out = A.psd_lsb_conversion(P, L, n_boot=50)
    assert out["k_in_effect"] == A.LSB_PER_UV2_TRANSFORM


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
