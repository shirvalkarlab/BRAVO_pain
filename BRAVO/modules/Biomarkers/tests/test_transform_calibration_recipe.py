"""The transform-route calibration (k = 352.62 LSB per uV^2) has a recipe in code, with the block
gate and the 5-MAD ratio rule the PI adopted on 2026-09-20 (decision 208).

Until now the constant lived in `analytics.LSB_PER_UV2_TRANSFORM` with a comment pointing at a
handoff and a CSV that was in nobody's repository. The paired blocks are now a de-identified table
in `data/calibration/` (one row per streaming block: the device's own selected-band LSB, median
over the block, against the transform band power on the same block's time domain, paired by the
shared first-packet time; produced by the lab's reference benchmark, commit a06afff, on the 583
exports through 2026-09-03), and `routines/calibration.py` applies the recipe to it:

  * the REFERENCE recipe (no gate, no rule) must give the June anchor back on the June rows:
    k = 352.62 all-stim, 356.61 stim-off, r = 0.9927, n = 131 -- the proof the table is the one
    the constant came from;
  * the ADOPTED recipe is the reference recipe plus a block gate (at least 3 s of time domain and
    at least 6 device points) and the platform's one outlier rule, 5 MAD on the RAW ratio
    LSB / uV^2 (decision 205), and it must not take a logarithm anywhere;
  * on every block through 2026-09-03 the adopted recipe lands within 2 percent of 352.62, which
    is why the deployed constant is KEPT (the PI, 2026-09-20: "keep 352.62").
"""
import ast
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A  # noqa: E402
from Biomarkers.routines import calibration as C  # noqa: E402

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "calibration", "RCS08_transform_blocks_2026-09-03.csv")


def _blocks():
    return C.load_blocks("RCS08")


def test_the_block_table_is_tracked_and_carries_no_report_name():
    assert os.path.isfile(TABLE), TABLE
    with open(TABLE, newline="") as f:
        header = next(csv.reader(f))
    assert "report" not in header and "lfp_channel" not in header, header
    for col in ("report_date", "timestamp", "channel", "side", "center_hz", "n_td_samples",
                "n_lfp_points_all", "n_lfp_points_off", "target_lsb_all", "target_lsb_off",
                "existing_uv2"):
        assert col in header, col
    rows = _blocks()
    assert len(rows) == 170, len(rows)
    assert max(r["report_date"] for r in rows) == "20260902", max(r["report_date"] for r in rows)


def test_the_reference_recipe_reproduces_the_june_anchor_on_the_june_rows():
    """No gate, no rule: the numbers the handoff of 2026-06-27 and the lab's committed summary
    carry, to the precision they carry them."""
    june = [r for r in _blocks() if r["report_date"] <= "20260624"]
    assert len(june) == 133, len(june)
    fit = C.transform_k(june, target="all", gate=False, mad_rule=False)
    assert fit["n"] == 131, fit["n"]
    assert round(fit["k"], 2) == 352.62, fit["k"]
    assert round(fit["r"], 4) == 0.9927, fit["r"]
    assert round(fit["median_fold_error"], 3) == 1.092, fit["median_fold_error"]
    off = C.transform_k(june, target="off", gate=False, mad_rule=False)
    assert off["n"] == 93 and round(off["k"], 2) == 356.61, (off["n"], off["k"])


def test_the_adopted_recipe_gates_short_blocks_and_flags_ratio_outliers_on_the_raw_scale():
    rows = _blocks()
    fit = C.transform_k(rows, target="all")                 # gate and rule on by default
    assert fit["gate"] == {"min_td_seconds": 3.0, "min_lfp_points": 6}
    assert fit["outlier_rule"] == "5 MAD on the raw ratio LSB / uV^2"
    assert fit["n_before_gate"] == 167 and fit["n_after_gate"] == 156, (fit["n_before_gate"], fit["n_after_gate"])
    assert fit["n"] == 133 and fit["n_flagged_by_rule"] == 23, (fit["n"], fit["n_flagged_by_rule"])
    assert round(fit["k"], 1) == 345.6 and round(fit["r"], 3) == 0.992, (fit["k"], fit["r"])
    off = C.transform_k(rows, target="off")
    assert off["n"] == 98 and round(off["k"], 1) == 351.2, (off["n"], off["k"])
    # the gate alone, without the rule, is the r = 0.980 middle row of the record
    gated = C.transform_k(rows, target="all", mad_rule=False)
    assert gated["n"] == 156 and round(gated["k"], 1) == 347.9 and round(gated["r"], 3) == 0.980


def test_a_single_short_block_is_what_the_gate_removes():
    """The 1.2 s block of 2026-07-07 at 4 mA: 17 uV^2 in the time domain against 1,197 LSB on the
    device, a five-fold miss on its own. The gate drops it; nothing else about it is special."""
    rows = _blocks()
    bad = [r for r in rows if r["timestamp"].startswith("2026-07-07T20:49:53") and r["side"] == "Right"]
    assert len(bad) == 1 and bad[0]["n_td_samples"] == 312
    kept = C.gate_blocks(rows)
    assert bad[0] not in kept
    assert all(r["n_td_samples"] >= 750 and r["n_lfp_points_all"] >= 6 for r in kept)


def test_the_deployed_constant_is_kept_and_the_refit_does_not_contradict_it():
    assert A.LSB_PER_UV2_TRANSFORM == 352.62
    fit = C.transform_k(_blocks(), target="all")
    assert abs(fit["k"] - A.LSB_PER_UV2_TRANSFORM) / A.LSB_PER_UV2_TRANSFORM < 0.02, fit["k"]
    assert C.DEPLOYED_K == A.LSB_PER_UV2_TRANSFORM


def test_the_recipe_takes_no_logarithm_and_uses_the_platforms_one_outlier_rule():
    src = open(C.__file__).read()
    tree = ast.parse(src)
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("log10", "log", "log2", "exp", "power")]
    assert hits == [], hits
    assert "mad_outlier_flags" in src, "the recipe must call stats_utils.mad_outlier_flags, not its own rule"
    # the median fold error is a ratio statistic and is computed as one: max(pred/obs, obs/pred)
    assert "np.maximum" in src



# --- the bridge: device onboard-FFT band power against the transform on the same montage survey ---

BRIDGE = os.path.join(os.path.dirname(TABLE), "RCS08_bridge_pairs_2026-09-03.csv")


def test_the_bridge_pairs_are_tracked_and_de_identified():
    assert os.path.isfile(BRIDGE), BRIDGE
    with open(BRIDGE, newline="") as f:
        header = next(csv.reader(f))
    assert header == ["survey_utc", "channel", "center_hz", "td_transform_uv2", "device_psd_uv2"], header
    pairs = C.load_bridge_pairs("RCS08")
    assert len(pairs) == 26334, len(pairs)
    assert {p["channel"] for p in pairs} == {
        "ZERO_ONE_LEFT", "ZERO_TWO_LEFT", "ZERO_THREE_LEFT", "ONE_TWO_LEFT", "ONE_THREE_LEFT", "TWO_THREE_LEFT",
        "ZERO_ONE_RIGHT", "ZERO_TWO_RIGHT", "ZERO_THREE_RIGHT", "ONE_TWO_RIGHT", "ONE_THREE_RIGHT", "TWO_THREE_RIGHT"}
    assert min(p["center_hz"] for p in pairs) == 7.5 and max(p["center_hz"] for p in pairs) == 27.5


def test_the_bridge_ratio_is_the_raw_median_with_the_five_mad_rule_and_the_bridge_is_kept():
    """The deployed ratio 4.789 was a geometric mean (a log-space average, June 2026, 5-45 Hz). The
    adopted recipe is the raw median of device / transform band power with the platform's 5-MAD
    rule: 4.755 on every survey through 2026-09-03 in the validated 7.5-27.5 Hz range, composed
    bridge 352.62 / 4.755 = 74.16 against the deployed 73.63, within 1 percent -- kept."""
    fit = C.bridge_ratio(C.load_bridge_pairs("RCS08"))
    assert fit["n_pairs"] == 26334 and fit["n_flagged_by_rule"] == 544 and fit["n"] == 25790, fit
    assert round(fit["ratio"], 3) == 4.755, fit["ratio"]
    assert round(fit["ratio_before_rule"], 3) == 4.774, fit["ratio_before_rule"]
    assert round(fit["bridge_lsb_per_device_uv2"], 2) == 74.16, fit["bridge_lsb_per_device_uv2"]
    assert fit["outlier_rule"] == "5 MAD on the raw ratio device / transform band power"
    assert A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO == 4.789 and round(A.LSB_PER_DEVICE_PSD, 2) == 73.63
    assert abs(fit["ratio"] - A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO) / A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO < 0.01
    assert C.DEPLOYED_BRIDGE_RATIO == A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO


def test_the_bridge_ratio_is_flat_across_contacts_and_centres():
    """Per contact pair 4.64-4.88 and per centre 4.69-4.89 on the raw median: one constant, not a
    curve in frequency and not a per-contact table."""
    pairs = C.load_bridge_pairs("RCS08")
    for ch in sorted({p["channel"] for p in pairs}):
        r = C.bridge_ratio([p for p in pairs if p["channel"] == ch])["ratio"]
        assert 4.6 < r < 4.9, (ch, r)
    for c in (7.5, 11.5, 15.5, 19.5, 23.5, 27.5):
        r = C.bridge_ratio([p for p in pairs if p["center_hz"] == c])["ratio"]
        assert 4.6 < r < 4.9, (c, r)

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
