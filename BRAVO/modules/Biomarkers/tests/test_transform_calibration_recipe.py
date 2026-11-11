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
  * the DEPLOYED constant is the adopted recipe on EVERY block, one median over all of the data
    (the PI, 2026-09-20, decision 211: "run the refit on the ... median of all of the data, rather
    than looking at two clusters"): 345.59; the composed bridge follows, 345.59 / 4.789. (Decision
    209 briefly deployed the midpoint of the June and September values, 349.10.)

Merged here 2026-10-05: test_calibration_panel.py.
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


def test_the_deployed_constant_is_the_adopted_recipes_median_over_every_block():
    """Decision 211: one median over all the data, 345.5870 deployed as 345.59 (two decimals, the
    precision the June constant carried); no era split, no midpoint. Recomputed here from the
    table, so a change to the table or the recipe shows up as a failure rather than a drift."""
    fit = C.transform_k(_blocks(), target="all")
    assert fit["n"] == 133 and round(fit["k"], 2) == 345.59, (fit["n"], fit["k"])
    assert A.LSB_PER_UV2_TRANSFORM == 345.59
    assert C.DEPLOYED_K == A.LSB_PER_UV2_TRANSFORM
    assert C.deployed_k_from_tables("RCS08") == 345.59
    # the composed bridge moves with it: 345.59 / 4.789
    assert round(A.LSB_PER_DEVICE_PSD, 2) == 72.16, A.LSB_PER_DEVICE_PSD


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
    rule: 4.755 on every survey through 2026-09-03 in the validated 7.5-27.5 Hz range; the ratio
    4.789 is kept (within 1 percent). The composed bridge is the deployed k over that ratio."""
    fit = C.bridge_ratio(C.load_bridge_pairs("RCS08"))
    assert fit["n_pairs"] == 26334 and fit["n_flagged_by_rule"] == 544 and fit["n"] == 25790, fit
    assert round(fit["ratio"], 3) == 4.755, fit["ratio"]
    assert round(fit["ratio_before_rule"], 3) == 4.774, fit["ratio_before_rule"]
    assert round(fit["bridge_lsb_per_device_uv2"], 2) == round(345.59 / 4.755, 2), fit["bridge_lsb_per_device_uv2"]
    assert fit["outlier_rule"] == "5 MAD on the raw ratio device / transform band power"
    assert A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO == 4.789 and round(A.LSB_PER_DEVICE_PSD, 2) == 72.16
    assert abs(fit["ratio"] - A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO) / A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO < 0.01
    assert C.DEPLOYED_BRIDGE_RATIO == A.LSB_PER_UV2_DEVICE_PSD_TD_RATIO


# --------------------------------------------------------------------------------------------------
# merged from test_calibration_panel.py
# The Biomarkers page's bottom-right calibration panel draws the calibration IN EFFECT, from the
# recipe and the tables in `routines/calibration.py`, not the frozen June log-log model (decision 212,
# the PI, 2026-09-20: "update the Biomarkers page frontend so the bottom calibration plots use the
# latest calibration constants").
#
# Until now `/api/queryPsdLsbConversionModel` served the frozen June model's plot payload: the v1 asset's
# per-band gain anchors (LSB at 1 uV^2, fitted on log10 power, decisions 11 and 18) and per-channel
# slopes 0.85 / 0.52 -- numbers that are neither the constant the platform converts with (345.59 since
# decision 211) nor derived on raw power, and a model no calculation has read since the fallback was
# removed on 2026-06-28. The panel's caption also said it was "the fallback the threshold estimator
# uses", which has been false since that day.
#
# Now the endpoint serves `calibration.panel_payload`: every paired block with its status under the
# adopted recipe (kept / gated / flagged / unusable), the recipe's fit, the bridge ratio per centre and
# per contact pair, and the constants in effect read from `analytics` (never typed into the payload).


import json


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


def test_the_committed_band_refit_and_its_log_log_fit_are_gone():
    """The PI, 2026-09-21: the bottom-left refit panel was redundant with the calibration-in-effect
    panel and its fit ran in log space (the free log-log slope, the log-residual scatter). The
    endpoint, the service function and the analytics routine are deleted with it."""
    import os as _os
    assert not hasattr(A, "psd_lsb_conversion")
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    svc = open(_os.path.join(root, "Biomarkers", "bravo_service.py")).read()
    assert "def band_psd_lsb_conversion" not in svc
    urls = open(_os.path.join(_os.path.dirname(root), "Server", "APIs", "urls.py")).read()
    assert "'queryPsdLsbConversion'" not in urls


def test_the_recipe_reports_a_raw_interval_a_raw_scatter_band_and_a_raw_proportionality_check():
    """The PI, 2026-09-21 (ruling C1): the constant's uncertainty in the same raw units, never a
    log. A planted proportional law LSB = 300 * uV^2 with multiplicative scatter of about 5%:
    the bootstrap interval on the median ratio covers 300, the 1-MAD band is a few percent of
    the constant, and the ratio does not change with the power level (Spearman near 0, p large).
    A planted law that BENDS (LSB grows as the square root of power) fails the check."""
    rng = np.random.default_rng(3)
    P = rng.gamma(2.0, 0.5, 120)
    L = 300.0 * P * (1.0 + 0.05 * rng.standard_normal(120))
    rows = [dict(existing_uv2=float(p), target_lsb_all=float(l), n_td_samples=2500.0, sample_rate_hz=250.0,
                 n_lfp_points_all=10.0, n_lfp_points_off=10.0) for p, l in zip(P, L)]
    fit = C.transform_k(rows, target="all")
    lo, hi = fit["k_interval"]
    assert lo < 300.0 < hi and hi - lo < 30.0, fit["k_interval"]
    assert fit["k_interval_method"].startswith("bootstrap")
    assert 0.0 < fit["scatter_mad"] < 0.10 * fit["k"]              # 1 MAD of the raw ratio, in LSB per uV^2
    assert 0.0 < fit["scatter_mad_frac"] < 0.10
    pr = fit["proportionality"]
    assert set(pr) >= {"spearman_rho", "p", "n", "holds", "sentence"}
    assert abs(pr["spearman_rho"]) < 0.25 and pr["p"] > 0.01 and pr["holds"] is True
    assert "does not change with the power level" in pr["sentence"]
    bent = [dict(r, target_lsb_all=float(300.0 * np.sqrt(r["existing_uv2"]))) for r in rows]
    fb = C.transform_k(bent, target="all")
    assert fb["proportionality"]["holds"] is False and fb["proportionality"]["p"] < 1e-6
    assert "changes with the power level" in fb["proportionality"]["sentence"]
    # too few blocks: the fields exist and say so, nothing raises
    few = C.transform_k(rows[:2], target="all")
    assert few["k_interval"] is None and few["proportionality"] is None


def test_the_live_recipe_carries_the_raw_uncertainty_and_the_panel_payload_serves_it():
    fit = C.transform_k(C.load_blocks("RCS08"), target="all")
    assert fit["k_interval"] is not None and fit["k_interval"][0] < fit["k"] < fit["k_interval"][1]
    assert fit["scatter_mad"] > 0 and fit["proportionality"]["n"] == fit["n"] == 133
    t = _payload()["transform"]
    for key in ("k_interval", "k_interval_method", "scatter_mad", "scatter_mad_frac", "proportionality"):
        assert key in t, key
    assert t["k_interval"] == [round(x, 6) for x in fit["k_interval"]] or t["k_interval"] == list(fit["k_interval"])
