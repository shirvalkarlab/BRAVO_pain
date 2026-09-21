"""The transform-route calibration recipe: how k = 352.62 LSB per uV^2 was derived, and how it is
refit (decision 208, 2026-09-20).

THE PAIRS. A BrainSense streaming session records the same signal two ways at once: the device's
own selected-band LFP power in LSB (`BrainSenseLfp`, one reading every 0.5 s, each tagged with the
stimulation current at that moment) and the raw 250 Hz time domain (`BrainSenseTimeDomain`). They
share a first-packet time, so each LSB stream has a byte-identical time-domain twin and no time
matching is needed. One BLOCK is one (streaming session, LFP stream, side): the target is the median
device LSB over the block (all readings, or the stim-off readings only), the candidate is the
transform band power on the same block's time domain (1 s RC+S-Hann window, zero-padded 256-point
FFT, peak scaling, in-band sum of squared magnitudes at the side's sensing centre +/- 2.5 Hz,
median across the windows), in uV^2. The pairing and the transform are the lab's reference
implementation (`shirvalkarlab/percept-spectral-repro`, `scripts/benchmark_brainsense_power.py`,
commit a06afff); the vendored copy in `analytics.td_transform_band_power` reproduces it bit for
bit. The blocks live in `data/calibration/<participant>_transform_blocks_<date>.csv`, one row per
block, de-identified (no report file name).

THE CONSTANT is the median of the raw ratio LSB / uV^2 over the blocks -- a raw statistic; no
logarithm enters it (the PI's rule of 2026-09-19, decision 202). THE DEPLOYED VALUE (decision 211,
the PI, 2026-09-20) is the adopted recipe's median over EVERY block, one number for all of the data:
345.59, two decimals; `deployed_k_from_tables` recomputes it. (Decision 209 briefly deployed the
midpoint of the June reference and this value, 349.10; the PI replaced that with the one median.)

THE REFERENCE RECIPE (the lab's, June 2026) keeps every block with at least 3 device readings and
at least one 1 s window. On the 517 exports through 2026-06-24 it gives k = 352.62 (all-stim,
n = 131, r = 0.9927) and 356.61 (stim-off, n = 93). `LSB_PER_UV2_TRANSFORM` is that number.

THE ADOPTED RECIPE (the PI, 2026-09-20) adds two things the reference lacks, because the exports of
July and August 2026 added blocks as short as 1.2 s recorded at 3-4 mA, one of which reads 17 uV^2
against 1,197 LSB and on its own pulls r from 0.99 to 0.82 without moving the median:
  * a BLOCK GATE: at least 3 s of time domain (750 samples) and at least 6 device readings;
  * the platform's one OUTLIER RULE, 5 MAD on the raw ratio (`stats_utils.mad_outlier_flags`,
    decision 205), applied to the gated blocks.
On the 583 exports through 2026-09-03 the adopted recipe gives 345.59 (all-stim, n = 133, r = 0.992)
and 351.2 (stim-off, n = 98).
`test_transform_calibration_recipe.py` pins the anchor, the adopted numbers and the 2 percent.

THE BRIDGE (PSD-only patient events). A montage survey records the same contact two ways at once:
the raw time domain and the device's onboard-FFT magnitude spectrum. The bridge ratio K is the
device's band power divided by the transform band power on the same survey and contact; the
composed bridge LSB per device-uV^2 is LSB_PER_UV2_TRANSFORM / K. The June derivation (CS-3) took a
GEOMETRIC mean over 10,476 contact-band points in 5-45 Hz: 4.789, bridge 73.63 -- a log-space
average. The adopted recipe (decision 208) is the raw median with the same 5-MAD rule, on every
survey and contact at the validated 7.5-27.5 Hz centres (`data/calibration/<participant>_bridge_pairs_<date>.csv`):
4.755 on 25,790 of 26,334 pairs through 2026-09-03, within 1 percent of the deployed ratio, which
is kept; the composed bridge is DEPLOYED_K / 4.789 = 72.16. Per contact pair the raw median runs 4.64-4.88 and per centre 4.69-4.89: one
constant, not a table.
"""
import csv
import os

import numpy as np

from .stats_utils import mad_outlier_flags

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "calibration")

#: The deployed constant. Defined in analytics as LSB_PER_UV2_TRANSFORM; repeated here so this
#: module stays free of the analytics import and the test can assert the two agree.
DEPLOYED_K = 345.59

#: The deployed bridge ratio (analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO), repeated for the same reason.
DEPLOYED_BRIDGE_RATIO = 4.789
BRIDGE_OUTLIER_RULE = "5 MAD on the raw ratio device / transform band power"

#: The adopted block gate (decision 208).
MIN_TD_SECONDS = 3.0
MIN_LFP_POINTS = 6
OUTLIER_RULE = "5 MAD on the raw ratio LSB / uV^2"

_FLOAT_COLS = ("center_hz", "sample_rate_hz", "n_td_samples", "n_lfp_points_all", "n_lfp_points_off",
               "median_ma_all", "median_ma_off", "target_lsb_all", "target_lsb_off",
               "existing_uv2", "welch256_uv2", "welch250_uv2")


def block_table_path(participant, date=None):
    """The newest block table for a participant (or the one dated `date`)."""
    code = str(participant or "").strip().upper()
    if date:
        return os.path.join(_DATA_DIR, f"{code}_transform_blocks_{date}.csv")
    names = sorted(n for n in os.listdir(_DATA_DIR)
                   if n.upper().startswith(f"{code}_TRANSFORM_BLOCKS_") and n.endswith(".csv"))
    if not names:
        raise FileNotFoundError(f"no transform block table for {code} in {_DATA_DIR}")
    return os.path.join(_DATA_DIR, names[-1])


def load_blocks(participant, date=None):
    """The paired blocks as a list of dicts; numeric columns as floats, NaN where blank."""
    rows = []
    with open(block_table_path(participant, date), newline="") as f:
        for r in csv.DictReader(f):
            row = dict(r)
            for k in _FLOAT_COLS:
                try:
                    row[k] = float(r[k])
                except (KeyError, TypeError, ValueError):
                    row[k] = float("nan")
            rows.append(row)
    return rows


def deployed_k_from_tables(participant):
    """The deployed constant recomputed from the table: the adopted recipe's median over every
    block, to two decimals (decision 211)."""
    return round(transform_k(load_blocks(participant), target="all")["k"], 2)


def gate_blocks(rows, *, min_td_seconds=MIN_TD_SECONDS, min_lfp_points=MIN_LFP_POINTS):
    """The blocks that carry enough signal to calibrate on: at least `min_td_seconds` of time
    domain and at least `min_lfp_points` device readings (all-stim count)."""
    out = []
    for r in rows:
        fs = r.get("sample_rate_hz")
        fs = 250.0 if not (isinstance(fs, float) and np.isfinite(fs) and fs > 0) else fs
        if r["n_td_samples"] >= min_td_seconds * fs and r["n_lfp_points_all"] >= min_lfp_points:
            out.append(r)
    return out


def block_status(rows, *, target="all", gate=True, mad_rule=True,
                 min_td_seconds=MIN_TD_SECONDS, min_lfp_points=MIN_LFP_POINTS):
    """One status per row, in the rows' order, under the recipe: "unusable" (no finite positive
    pair), "gated" (fails the block gate), "flagged" (the 5-MAD rule on the raw ratio), "kept"."""
    if target not in ("all", "off"):
        raise ValueError(f"target must be 'all' or 'off', got {target!r}")
    col = f"target_lsb_{target}"
    status = []
    for r in rows:
        usable = (np.isfinite(r["existing_uv2"]) and r["existing_uv2"] > 0
                  and np.isfinite(r[col]) and r[col] > 0)
        if not usable:
            status.append("unusable")
        elif gate and not gate_blocks([r], min_td_seconds=min_td_seconds, min_lfp_points=min_lfp_points):
            status.append("gated")
        else:
            status.append("kept")
    if mad_rule:
        idx = [i for i, st in enumerate(status) if st == "kept"]
        if idx:
            ratio = np.array([rows[i][col] / rows[i]["existing_uv2"] for i in idx], float)
            flags, _info = mad_outlier_flags(ratio)
            for i, f in zip(idx, flags):
                if f:
                    status[i] = "flagged"
    return status


#: The scatter of the calibration, in the constant's own units: 1 MAD of the raw ratio over the
#: kept blocks. It is the band the Closed-Loop page draws either side of a MODELLED threshold
#: (ruling A2, the PI, 2026-09-21), replacing the deleted June model's log-space 1.26 fold.
SCATTER_RULE = "1 MAD of the raw ratio LSB / uV^2 over the kept blocks"
N_BOOT = 2000
PROPORTIONALITY_ALPHA = 0.01


def transform_k(rows, *, target="all", gate=True, mad_rule=True,
                min_td_seconds=MIN_TD_SECONDS, min_lfp_points=MIN_LFP_POINTS, n_boot=N_BOOT):
    """The proportional constant k = median(LSB / uV^2) over the blocks, with its fit statistics.

    `target` is "all" (every device reading in the block) or "off" (stim-off readings only).
    `gate=False, mad_rule=False` is the lab's reference recipe; both on is the adopted one.
    Returns a dict: k, n, r (Pearson, raw scale), rmse_lsb, median_fold_error, n_before_gate,
    n_after_gate, n_flagged_by_rule, gate, outlier_rule, target, and (ruling C1, the PI,
    2026-09-21, every one in raw units, never a log) k_interval (95% bootstrap interval on the
    median ratio, `n_boot` resamples, seed 0), scatter_mad (1 MAD of the raw ratio over the kept
    blocks, in LSB per uV^2) with scatter_mad_frac (the same as a fraction of k), and
    proportionality (does the ratio change with the power level: Spearman's rho of the ratio
    against uV^2 with its p; `holds` when p >= 0.01).
    """
    col = f"target_lsb_{target}"
    status = block_status(rows, target=target, gate=gate, mad_rule=mad_rule,
                          min_td_seconds=min_td_seconds, min_lfp_points=min_lfp_points)
    n_before = sum(1 for st in status if st != "unusable")
    n_flagged = sum(1 for st in status if st == "flagged")
    kept = [r for r, st in zip(rows, status) if st == "kept"]
    P = np.array([r["existing_uv2"] for r in kept], float)
    L = np.array([r[col] for r in kept], float)
    out = {"target": target, "n_before_gate": n_before, "n_after_gate": n_before - sum(1 for st in status if st == "gated"),
           "n_flagged_by_rule": n_flagged, "n": int(P.size),
           "gate": ({"min_td_seconds": float(min_td_seconds), "min_lfp_points": int(min_lfp_points)}
                    if gate else None),
           "outlier_rule": OUTLIER_RULE if mad_rule else None,
           "k": None, "r": None, "rmse_lsb": None, "median_fold_error": None,
           "k_interval": None, "k_interval_method": None, "scatter_mad": None,
           "scatter_mad_frac": None, "scatter_rule": SCATTER_RULE, "proportionality": None}
    if P.size < 3:
        return out
    ratio = L / P
    k = float(np.median(ratio))
    pred = k * P
    out["k"] = k
    out["r"] = float(np.corrcoef(P, L)[0, 1])
    out["rmse_lsb"] = float(np.sqrt(np.mean((L - pred) ** 2)))
    out["median_fold_error"] = float(np.median(np.maximum(pred / L, L / pred)))
    out.update(raw_uncertainty(P, L, n_boot=n_boot))
    return out


def raw_uncertainty(P, L, *, n_boot=N_BOOT, seed=0):
    """The constant's uncertainty from the kept pairs, in raw units (ruling C1): a 95% bootstrap
    percentile interval on the median ratio, 1 MAD of the ratio, and whether the ratio changes
    with the power level (Spearman's rho of ratio against uV^2). Every quantity is on the raw
    ratio; no logarithm."""
    from scipy import stats
    P = np.asarray(P, float); L = np.asarray(L, float)
    ratio = L / P
    n = int(ratio.size)
    k = float(np.median(ratio))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(int(n_boot), n))
    meds = np.median(ratio[idx], axis=1)
    lo, hi = (float(v) for v in np.percentile(meds, [2.5, 97.5]))
    mad = float(np.median(np.abs(ratio - k)))
    rho, p = stats.spearmanr(P, ratio)
    rho = float(rho); p = float(p)
    holds = bool(np.isfinite(p) and p >= PROPORTIONALITY_ALPHA)
    sentence = (f"The ratio does not change with the power level over the {n} kept blocks "
                f"(Spearman's rho {rho:+.2f}, p = {p:.2g}), so one constant fits."
                if holds else
                f"The ratio changes with the power level over the {n} kept blocks "
                f"(Spearman's rho {rho:+.2f}, p = {p:.2g}): one constant does not describe every level.")
    return {"k_interval": [lo, hi], "k_interval_method": f"bootstrap percentile, {int(n_boot)} resamples, seed {seed}",
            "scatter_mad": mad, "scatter_mad_frac": (mad / k if k else None),
            "proportionality": {"spearman_rho": rho, "p": p, "n": n, "holds": holds,
                                "alpha": PROPORTIONALITY_ALPHA, "sentence": sentence}}


def bridge_pairs_path(participant, date=None):
    """The newest bridge-pairs table for a participant (or the one dated `date`)."""
    code = str(participant or "").strip().upper()
    if date:
        return os.path.join(_DATA_DIR, f"{code}_bridge_pairs_{date}.csv")
    names = sorted(n for n in os.listdir(_DATA_DIR)
                   if n.upper().startswith(f"{code}_BRIDGE_PAIRS_") and n.endswith(".csv"))
    if not names:
        raise FileNotFoundError(f"no bridge pairs table for {code} in {_DATA_DIR}")
    return os.path.join(_DATA_DIR, names[-1])


def load_bridge_pairs(participant, date=None):
    """One row per (survey, contact pair, band centre): the transform band power of the survey's
    time domain and the device's onboard-FFT band power, both in uV^2."""
    rows = []
    with open(bridge_pairs_path(participant, date), newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"survey_utc": r["survey_utc"], "channel": r["channel"],
                         "center_hz": float(r["center_hz"]),
                         "td_transform_uv2": float(r["td_transform_uv2"]),
                         "device_psd_uv2": float(r["device_psd_uv2"])})
    return rows


def bridge_ratio(pairs, *, mad_rule=True, k_transform=DEPLOYED_K):
    """K = median(device band power / transform band power) over the pairs, on the raw ratio, with
    the platform's 5-MAD rule; and the composed bridge k_transform / K in LSB per device-uV^2."""
    P = np.array([p["td_transform_uv2"] for p in pairs], float)
    Q = np.array([p["device_psd_uv2"] for p in pairs], float)
    m = np.isfinite(P) & np.isfinite(Q) & (P > 0) & (Q > 0)
    P, Q = P[m], Q[m]
    out = {"n_pairs": int(P.size), "n_flagged_by_rule": 0, "n": int(P.size),
           "outlier_rule": BRIDGE_OUTLIER_RULE if mad_rule else None,
           "ratio": None, "ratio_before_rule": None, "bridge_lsb_per_device_uv2": None}
    if P.size < 3:
        return out
    ratio = Q / P
    out["ratio_before_rule"] = float(np.median(ratio))
    if mad_rule:
        flags, _info = mad_outlier_flags(ratio)
        out["n_flagged_by_rule"] = int(flags.sum())
        ratio = ratio[~flags]
    out["n"] = int(ratio.size)
    out["ratio"] = float(np.median(ratio))
    out["bridge_lsb_per_device_uv2"] = float(k_transform / out["ratio"])
    return out


# --- the Biomarkers page's calibration panel (decision 212) -------------------------------------

JUNE_REFERENCE_LAST_DATE = "20260624"   #: the last export in the June derivation (decision 18)


def _finite(x):
    return float(x) if isinstance(x, (int, float, np.floating)) and np.isfinite(x) else None


def _table_date(path):
    stem = os.path.basename(path).rsplit(".", 1)[0]
    return stem.rsplit("_", 1)[-1]


def panel_payload(participant, *, deployed_k, deployed_bridge_ratio, deployed_bridge):
    """Everything the page's calibration panel draws: every paired block with its status under the
    adopted recipe, the recipe's fit, the June reference recomputed from the same table, the
    bridge ratio overall and per centre / per contact pair, and the constants IN EFFECT, which the
    caller reads from `analytics` (this module carries no analytics import on purpose)."""
    try:
        rows = load_blocks(participant)
        pairs = load_bridge_pairs(participant)
    except FileNotFoundError as e:
        return {"available": False, "reason": str(e)}
    status = block_status(rows, target="all")
    fit = transform_k(rows, target="all")
    june = transform_k([r for r in rows if r["report_date"] <= JUNE_REFERENCE_LAST_DATE],
                       target="all", gate=False, mad_rule=False)
    blocks = [{"uv2": _finite(r["existing_uv2"]), "lsb": _finite(r["target_lsb_all"]),
               "side": r["side"], "channel": r["channel"], "center_hz": _finite(r["center_hz"]),
               "date": r["report_date"], "timestamp": r["timestamp"],
               "td_seconds": _finite(r["n_td_samples"] / (r["sample_rate_hz"] if np.isfinite(r["sample_rate_hz"]) and r["sample_rate_hz"] > 0 else 250.0)),
               "n_lfp_points": _finite(r["n_lfp_points_all"]),
               "median_ma": _finite(r["median_ma_all"]), "status": st}
              for r, st in zip(rows, status)]
    transform = dict(fit)
    transform["k"] = _finite(fit["k"]); transform["r"] = _finite(fit["r"])
    transform["rmse_lsb"] = _finite(fit["rmse_lsb"]); transform["median_fold_error"] = _finite(fit["median_fold_error"])
    transform["scatter_mad"] = _finite(fit["scatter_mad"]); transform["scatter_mad_frac"] = _finite(fit["scatter_mad_frac"])
    transform["k_interval"] = [_finite(v) for v in fit["k_interval"]] if fit["k_interval"] else None
    if fit["proportionality"]:
        transform["proportionality"] = dict(fit["proportionality"], spearman_rho=_finite(fit["proportionality"]["spearman_rho"]),
                                            p=_finite(fit["proportionality"]["p"]))
    transform["blocks"] = blocks
    transform["june_reference"] = {"k": _finite(june["k"]), "n": june["n"], "r": _finite(june["r"]),
                                   "last_date": JUNE_REFERENCE_LAST_DATE}
    br = bridge_ratio(pairs, k_transform=deployed_k)
    bridge = {k: (_finite(v) if isinstance(v, float) else v) for k, v in br.items()}

    def _group(key):
        groups = {}
        for p in pairs:
            groups.setdefault(key(p), []).append(p)
        return groups
    bridge["per_centre"] = [{"center_hz": c, "ratio": _finite(bridge_ratio(g)["ratio"]), "n": bridge_ratio(g)["n"]}
                            for c, g in sorted(_group(lambda p: p["center_hz"]).items())]
    bridge["per_channel"] = [{"channel": ch, "ratio": _finite(bridge_ratio(g)["ratio"]), "n": bridge_ratio(g)["n"]}
                             for ch, g in sorted(_group(lambda p: p["channel"]).items())]
    bridge["per_channel_centre"] = [{"channel": ch, "center_hz": c, "ratio": _finite(bridge_ratio(g)["ratio"]),
                                     "n": bridge_ratio(g)["n"]}
                                    for (ch, c), g in sorted(_group(lambda p: (p["channel"], p["center_hz"])).items())]
    bridge["n_surveys"] = len({p["survey_utc"] for p in pairs})
    return {"available": True, "participant": str(participant).strip().upper(),
            "table_date": _table_date(block_table_path(participant)),
            "deployed": {"k": deployed_k, "bridge_ratio": deployed_bridge_ratio,
                         "bridge_lsb_per_device_uv2": deployed_bridge},
            "transform": transform, "bridge": bridge}
