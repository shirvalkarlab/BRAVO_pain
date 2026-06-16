"""
One-patient, library-mode runner for the biomarker module.

Supports TWO biomarker DATA SOURCES, selected via `source`:
  * "timedomain" : raw 250 Hz BrainSense streaming -> streaming PSD <-> pain correlation
  * "chronic"    : the ~10-min BrainSense Timeline LFP power trend -> sliding-window threshold
  * "both"       : run each independently, then merge onto ONE aligned timeline (the "same page")

End-to-end (library mode, no Django / no React):
    decoded recordings  ->  adapter reshape / chronic tidy-frame
    REDCap PROs         ->  adapter.align_pros (session | chronic) + label
    science routine     ->  streaming_psd OR threshold_biomarker (verbatim, unchanged)
    -> unified `combined` timeline -> write combined_<patient>_<source>.{csv,npz}

Architecture note: source selection is a flat enum + if/elif dispatch, matching this module's
flat-dict / free-function house style (no classes). If a 3rd data source ever appears, promote
this enum to a registry then -- cheap later, not worth carrying now.

DEFERRED HOOKS (intentionally not built here -- see plan):
  * Percept JSON decode: `decode_percept_session` is the attach point. BRAVO decodes a
    clinician session via modules/MedtronicPercept (Percept.py -> BrainSenseStream.py
    `saveBrainSenseStreams`, ChronicBrainSense.py `saveChronicBrainSense`). That path depends
    on the Django models layer, so library-mode runs take already-decoded recordings instead.
  * Django persistence: the `write_combined` step is where
    `DataAnalysis.saveAnalysisProcessedData(Data, type=..., metadata={codeVersion,...},
    recording=...)` would later attach.
  * DRF endpoint + React plot: would consume the `combined` timeline produced here.
"""

import os
import json
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .routines import streaming_psd
from .routines import threshold_biomarker
from .routines import redcap_client
from . import adapter

# Per-source code versions; stamped into every output file. Bump when a source's math changes.
STREAMING_CODE_VERSION = "streaming_psd-0.1.0"
CHRONIC_CODE_VERSION = "chronic_threshold-0.1.0"
# Back-compat alias (old name referenced the streaming version).
CODE_VERSION = STREAMING_CODE_VERSION


def decode_percept_session(*_args, **_kwargs):
    """Attach point for BRAVO Percept decode (deferred).

    Later this calls modules/MedtronicPercept BrainSenseStream.saveBrainSenseStreams() to
    turn a clinician session JSON into TimeDomain/PowerDomain/Chronic recordings. For now,
    library-mode callers pass already-decoded `recordings` to `run_streaming_biomarker`.
    """
    raise NotImplementedError(
        "Percept JSON decode is a deferred hook. In library mode, pass already-decoded "
        "BRAVO recordings to run_streaming_biomarker(recordings=...). Wiring "
        "modules/MedtronicPercept.BrainSenseStream.saveBrainSenseStreams is a later phase."
    )


def select_biomarker_band(result, p_threshold=0.05, ignore_band=None):
    """Pick the (channel, frequency) with the strongest significant |corr| vs pain.

    Require p < threshold, maximize |r|. Returns (chan_index, freq_index, r, p, freq_hz).

    `ignore_band`: optional (lo, hi) Hz to exclude from selection. Default None — NO exclusion,
    so a biomarker at 60 Hz CAN be selected (per PI request). The notebook (cells 13/16) excluded
    the 55-66 Hz mains region; pass `ignore_band=(55, 66)` to restore that behavior.
    """
    corr = result["corr"].copy()
    pval = result["pval"].copy()
    f_set = result["f_set"]

    mask = np.isfinite(corr) & np.isfinite(pval) & (pval < p_threshold)
    if ignore_band is not None:
        ignore = (f_set > ignore_band[0]) & (f_set < ignore_band[1])
        mask[:, ignore] = False
    if not mask.any():
        return None
    masked = np.where(mask, np.abs(corr), -np.inf)
    c_idx, f_idx = np.unravel_index(np.argmax(masked), masked.shape)
    return int(c_idx), int(f_idx), float(corr[c_idx, f_idx]), float(pval[c_idx, f_idx]), float(f_set[f_idx])


# ---------------------------------------------------------------------------
# Per-source branches. Each returns a "SourceRun" dict with a namespaced `timeline`:
#   {source, code_version, timeline (DataFrame), detail (raw science), summary (headline)}
# The timeline columns are prefixed td_* / chronic_* so source="both" merges without collision.
# ---------------------------------------------------------------------------
def run_timedomain_branch(recordings, pro_df, chan_order, *, align="session",
                          label_metric="nrs", label_reduce="min",
                          transform="log", stim_amplitudes=None):
    """Time-domain (250 Hz streaming) PSD<->pain branch -> SourceRun with a td_* timeline.

    `align` is accepted for signature back-compat but no longer changes the timeline: the
    time-domain timeline is always session-resolution (one row per streaming session). The
    chronic spine, when present, comes from the chronic branch.
    """
    streams = adapter.bravo_timedomain_recordings_to_streams(recordings)
    metrics = (label_metric,) if label_metric not in ("nrs", "vas", "mpq_sum") else ("nrs", "vas", "mpq_sum")
    session_df = adapter.align_pros(
        pro_df, target="session", recordings=recordings,
        metrics=metrics, stim_amplitudes=stim_amplitudes,
    )
    label_col = f"{label_metric}_{label_reduce}"
    labels = session_df[label_col].to_numpy(dtype=float)

    result = streaming_psd.compute_psd_pain_correlation(streams, labels, chan_order, transform=transform)
    band = select_biomarker_band(result)

    timeline = pd.DataFrame({
        "time": pd.to_datetime(session_df["session_start"]),
        "date": session_df["session_date"],
    })
    if band is not None:
        c_idx, f_idx, r, p, f_hz = band
        timeline["td_biomarker_value"] = result["psd"][:, c_idx, f_idx]
        timeline["td_biomarker_channel"] = result["chan_order"][c_idx]
        timeline["td_biomarker_freq_hz"] = f_hz
        timeline["td_biomarker_r"] = r
        timeline["td_biomarker_p"] = p
    else:
        timeline["td_biomarker_value"] = np.nan
    timeline["td_stim_amplitude"] = session_df.get("stim_amplitude", np.nan)
    for m in metrics:
        for red in ("mean", "min"):
            col = f"{m}_{red}"
            if col in session_df.columns:
                timeline[f"td_{col}"] = session_df[col].to_numpy()

    summary = {"band": band}
    if band is not None:
        summary.update({"channel": result["chan_order"][band[0]],
                        "freq_hz": band[4], "r": band[2], "p": band[3]})
    return {"source": "timedomain", "code_version": STREAMING_CODE_VERSION,
            "timeline": timeline, "detail": result, "summary": summary}


def run_powerdomain_branch(pro_df, *, chronic, label_metric="nrs", pain_cutoff=None,
                           label_strategy="kmeans", kmeans_features=("left_leg_vas", "mpq_sum"),
                           thresholds=None, train_days=7, gap_days=1, test_days=2, sliding=True):
    """Power-domain (band-power-over-time) sliding-window threshold branch -> SourceRun with a
    powerdomain_* timeline. The "power domain" is the complement to the time domain: it merges the
    ~10-min Chronic LFP-power timeline with the per-session BrainSense Power-Domain band power
    (both already concatenated into `chronic` upstream as chronic-shaped power dicts).

    `chronic` is one chronic-shaped power recording dict OR a list of them (concatenated +
    time-sorted into one long trend -- the detector needs ~train+gap+test days of data).
    `label_strategy` ("kmeans" | "cutoff") selects the pain_level labeler; "kmeans" matches the
    source notebook (clusters [left_leg_vas, mpq_sum]) and falls back to "cutoff" if those
    columns are absent from pro_df.
    """
    if chronic is None:
        raise ValueError('a "powerdomain" source requires `chronic` (a power recording or list).')
    cv_df = adapter.bravo_chronic_to_lfp_df(chronic, pro_df, label_metric=label_metric,
                                            pain_cutoff=pain_cutoff, label_strategy=label_strategy,
                                            kmeans_features=kmeans_features)
    detail = threshold_biomarker.run_chronic_threshold(
        cv_df, thresholds=thresholds, train_days=train_days, gap_days=gap_days, test_days=test_days,
        sliding=sliding)
    thr = detail.get("mean_thr_sens", np.nan)

    lfp_s = cv_df["LFP_smoothed"].to_numpy(dtype=float)
    timeline = pd.DataFrame({
        "time": pd.to_datetime(cv_df["timestamp"]),
        "date": pd.to_datetime(cv_df["timestamp"]).dt.date,
        "powerdomain_biomarker_value": lfp_s,
        "powerdomain_lfp_raw": cv_df["LFP"].to_numpy(dtype=float),
        "powerdomain_threshold": thr,
        "powerdomain_stim_amplitude": cv_df["stim_amplitude"].to_numpy(dtype=float),
        "powerdomain_pain_level": cv_df["pain_level"].to_numpy(dtype=float),
    })
    timeline["powerdomain_pred"] = (lfp_s >= thr).astype(float) if np.isfinite(thr) else np.nan
    timeline[f"powerdomain_{label_metric}"] = cv_df[label_metric].to_numpy(dtype=float)

    # run_sliding_window_dual is a DUAL detector: it returns two independent operating points
    # -- a sensitivity-optimized threshold (mean_thr_sens, with mean_test_*_sens metrics) and a
    # specificity-optimized threshold (mean_thr_spec, with mean_test_*_spec metrics). The headline
    # summary reports ONE self-consistent operating point: the sens-objective threshold and the
    # metrics ACTUALLY achieved at THAT threshold (so `spec` is mean_test_spec_SENS, not _spec --
    # pairing mean_thr_sens with mean_test_spec_spec would overstate specificity, since no single
    # threshold attains both). chronic_threshold / chronic_pred above also use mean_thr_sens, so
    # they stay consistent with this summary. The spec-objective point is preserved explicitly.
    summary = {
        "objective": "sens",
        "best_threshold": thr,                                   # mean_thr_sens
        "sens": detail.get("mean_test_sens_sens", np.nan),       # sens at best_threshold
        "spec": detail.get("mean_test_spec_sens", np.nan),       # spec at best_threshold (self-consistent)
        "acc": detail.get("mean_test_acc_sens", np.nan),         # acc at best_threshold
        "n_windows": detail.get("n_windows", 0),
        # The alternative (specificity-optimized) operating point, kept explicit, not mixed in:
        "spec_objective_threshold": detail.get("mean_thr_spec", np.nan),
        "spec_objective_sens": detail.get("mean_test_sens_spec", np.nan),
        "spec_objective_spec": detail.get("mean_test_spec_spec", np.nan),
        "spec_objective_acc": detail.get("mean_test_acc_spec", np.nan),
    }
    return {"source": "powerdomain", "code_version": CHRONIC_CODE_VERSION,
            "timeline": timeline, "detail": detail, "summary": summary,
            # Expose the full-resolution tidy frame so the analytics step can reuse it instead of
            # rebuilding (a second KMeans + Savitzky-Golay over 100k+ rows). Not serialized.
            "cv_df": cv_df}


# Back-compat: the chronic branch was renamed to the power-domain branch (chronic timeline is now
# merged with per-session power-domain band power upstream). Keep the old name as an alias.
run_chronic_branch = run_powerdomain_branch


def run_biomarker(recordings, pro_df, chan_order, *, source="timedomain", chronic=None,
                  align="session", label_metric="nrs", label_reduce="min", transform="log",
                  pain_cutoff=None, label_strategy="kmeans",
                  kmeans_features=("left_leg_vas", "mpq_sum"),
                  thresholds=None, train_days=7, gap_days=1, test_days=2,
                  stim_amplitudes=None, sliding=True):
    """
    Run biomarker identification with a selectable data source.

    source : {"timedomain", "powerdomain", "both"}  ("chronic" accepted as alias of "powerdomain")
        "timedomain"  -> 250 Hz streaming PSD<->pain (needs `recordings`).
        "powerdomain" -> band-power-over-time threshold detector (needs `chronic`: the merged
                         Chronic timeline + per-session Power-Domain band power as chronic-shaped dicts).
        "both"        -> run each independently and merge onto one timeline.

    Returns
    -------
    dict: {"source", "timedomain": SourceRun|None, "powerdomain": SourceRun|None,
           "combined": DataFrame}  -- `combined` is the unified, NaN-tolerant same-page timeline.
    """
    if source == "chronic":           # back-compat alias
        source = "powerdomain"
    if source not in ("timedomain", "powerdomain", "both"):
        raise ValueError('source must be "timedomain", "powerdomain", or "both"')

    def _td():
        return run_timedomain_branch(recordings, pro_df, chan_order, align=align,
                                     label_metric=label_metric, label_reduce=label_reduce,
                                     transform=transform, stim_amplitudes=stim_amplitudes)

    def _power():
        return run_powerdomain_branch(pro_df, chronic=chronic, label_metric=label_metric,
                                      pain_cutoff=pain_cutoff, label_strategy=label_strategy,
                                      kmeans_features=kmeans_features, thresholds=thresholds,
                                      train_days=train_days, gap_days=gap_days, test_days=test_days,
                                      sliding=sliding)

    td = ch = None
    if source == "both":
        # The two branches are independent (separate data sources + science), so compute them
        # concurrently — "both" wall-clock becomes max(td, powerdomain) instead of their sum.
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_td, fut_power = ex.submit(_td), ex.submit(_power)
            td, ch = fut_td.result(), fut_power.result()
    elif source == "timedomain":
        td = _td()
    elif source == "powerdomain":
        ch = _power()

    combined = adapter.merge_timelines(td["timeline"] if td else None,
                                       ch["timeline"] if ch else None)
    return {"source": source, "timedomain": td, "powerdomain": ch, "combined": combined}


def run_streaming_biomarker(recordings, pro_df, chan_order, *, align="session",
                            label_metric="nrs", label_reduce="min",
                            transform="log", chronic=None, stim_amplitudes=None):
    """Back-compat shim -> run_biomarker(source="timedomain").

    Preserves the original return shape {"result", "band", "combined"} so existing callers
    and tests stay green.
    """
    run = run_biomarker(recordings, pro_df, chan_order, source="timedomain", align=align,
                        label_metric=label_metric, label_reduce=label_reduce,
                        transform=transform, stim_amplitudes=stim_amplitudes)
    td = run["timedomain"]
    return {"result": td["detail"], "band": td["summary"]["band"], "combined": run["combined"]}


def write_combined(run_output, patient, out_dir="."):
    """Write the unified `combined` timeline + per-source detail as flat files.

    Stems as `combined_<patient>_<source>.{csv,npz}` and tags each present branch's
    code_version into the npz. This is the deferred Django-persistence attach point.
    Returns (csv_path, npz_path).
    """
    os.makedirs(out_dir, exist_ok=True)
    source = run_output.get("source", "timedomain")
    stem = f"combined_{patient}_{source}"
    csv_path = os.path.join(out_dir, f"{stem}.csv")
    npz_path = os.path.join(out_dir, f"{stem}.npz")

    run_output["combined"].to_csv(csv_path, index=False)

    arrays = {"source": source}
    td = run_output.get("timedomain")
    ch = run_output.get("powerdomain") or run_output.get("chronic")  # back-compat key
    if td is not None:
        r = td["detail"]
        arrays.update({
            "timedomain_code_version": td["code_version"],
            "td_f_set": r["f_set"], "td_psd": r["psd"], "td_corr": r["corr"], "td_pval": r["pval"],
            "td_chan_order": np.array(r["chan_order"], dtype=object),
            "td_transform": r["transform"], "td_labels": r["labels"],
            "td_band": np.array(td["summary"]["band"], dtype=object) if td["summary"]["band"] else np.array([]),
        })
    if ch is not None:
        arrays.update({
            "chronic_code_version": ch["code_version"],
            "chronic_summary": np.array(list(ch["summary"].items()), dtype=object),
            "chronic_detail": np.array(list(ch["detail"].items()), dtype=object),
        })
    np.savez(npz_path, **arrays)
    return csv_path, npz_path


def _load_chan_order(pt_config_path):
    cfg = json.load(open(pt_config_path, "r"))
    return list(cfg["channel_names"].keys())


def _load_chronic_npz(path):
    blob = np.load(path, allow_pickle=True)["chronic"]
    return blob.item() if getattr(blob, "ndim", None) == 0 else list(blob)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Biomarker identification (library mode): time-domain | chronic | both.")
    ap.add_argument("--patient", required=True, help="Patient id, e.g. RCS08")
    ap.add_argument("--source", choices=["timedomain", "chronic", "both"], default="timedomain")
    ap.add_argument("--align", choices=["session", "chronic"], default="session")
    ap.add_argument("--pro-csv", required=True, help="Processed PRO CSV (pt_data/<pt>_redcap_proc.csv)")
    ap.add_argument("--pt-config", required=True, help="pt_config/<pt>_config.json (for channel order)")
    ap.add_argument("--recordings-npz",
                    help="NPZ with key 'recordings' = list of BRAVO TimeDomain dicts (timedomain/both).")
    ap.add_argument("--chronic-npz",
                    help="NPZ with key 'chronic' = a Chronic recording dict or list (chronic/both).")
    ap.add_argument("--transform", default="log")
    ap.add_argument("--label-metric", default="nrs")
    ap.add_argument("--label-strategy", choices=["kmeans", "cutoff"], default="kmeans",
                    help="Chronic pain_level labeler: 'kmeans' (notebook: clusters "
                         "[left_leg_vas, mpq_sum]) or 'cutoff' (single-metric threshold).")
    ap.add_argument("--pain-cutoff", type=float, default=None,
                    help="Chronic 'cutoff' strategy threshold (default: median of the metric).")
    ap.add_argument("--out-dir", default=".")
    args = ap.parse_args(argv)

    chan_order = _load_chan_order(args.pt_config)
    pro_df = redcap_client.load_processed_pro_csv(args.pro_csv)

    recordings = None
    if args.recordings_npz:
        recordings = list(np.load(args.recordings_npz, allow_pickle=True)["recordings"])
    chronic = _load_chronic_npz(args.chronic_npz) if args.chronic_npz else None

    if args.source in ("timedomain", "both") and recordings is None:
        ap.error("--recordings-npz is required for source timedomain/both")
    if args.source in ("chronic", "both") and chronic is None:
        ap.error("--chronic-npz is required for source chronic/both")

    run_output = run_biomarker(recordings, pro_df, chan_order, source=args.source,
                               chronic=chronic, align=args.align, transform=args.transform,
                               label_metric=args.label_metric, pain_cutoff=args.pain_cutoff,
                               label_strategy=args.label_strategy)
    csv_path, npz_path = write_combined(run_output, args.patient, out_dir=args.out_dir)
    print(f"Wrote {csv_path}\nWrote {npz_path}")

    td = run_output.get("timedomain")
    ch = run_output.get("powerdomain") or run_output.get("chronic")  # back-compat key
    if td is not None:
        b = td["summary"]["band"]
        if b is not None:
            print(f"[timedomain] top band: ch={td['detail']['chan_order'][b[0]]} "
                  f"{b[4]:.2f} Hz  r={b[2]:.3f} p={b[3]:.4g}")
        else:
            print("[timedomain] no significant biomarker band found.")
    if ch is not None:
        s = ch["summary"]
        print(f"[chronic] threshold={s['best_threshold']}  sens={s['sens']}  "
              f"spec={s['spec']}  n_windows={s['n_windows']}")


if __name__ == "__main__":
    main()
