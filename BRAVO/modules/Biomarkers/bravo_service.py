"""
BRAVO integration service for the Biomarkers module.

This is the ONLY Django-coupled file in the package (the pure pipeline/adapter/routines and the
test suite never import Django). It loads a participant's decoded Percept recordings + REDCap PROs
from the running platform's database, runs `pipeline.run_biomarker`, and returns a JSON-able dict
the DRF view (Server/APIs/DataAnalysis.QueryBiomarkerAnalysis) hands back to the React card.

Recording structures (from modules/MedtronicPercept) map 1:1 onto the adapter's expectations:
  TimeDomain recording dict: {SamplingRate, ChannelNames, Data (N,ch), Missing, StartTime, Duration}
  Chronic recording dict:    {SamplingRate:-1, Time:(N,), Data:(N,2) [LFP, Amp], ChannelNames, ...}
so `Database.loadSourceFile(...)` output is fed straight into run_biomarker.
"""

import os

import numpy as np
import pandas as pd

from Server import models
from modules import Database

from . import pipeline
from . import adapter
from .routines import redcap_client
from .routines import analytics

# DB recording types that decode to 250 Hz time-domain LFP and to the ~10-min chronic trend.
TIMEDOMAIN_TYPES = ["MedtronicBrainSenseTimeDomain", "MedtronicIndefiniteStream"]
CHRONIC_TYPES = ["MedtronicChronicBrainSense"]


def _load_recordings(participant_uid, types):
    """Return a list of loaded recording dicts for a participant, for the given DB types."""
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    Recordings = models.Recording.find_all(source__in=SourceFiles, type__in=types)
    loaded = []
    for rec in Recordings:
        try:
            data = Database.loadSourceFile(rec.pointer, rec.hashed)
        except Exception:
            continue
        if isinstance(data, list):
            loaded.extend([d for d in data if isinstance(d, dict)])
        elif isinstance(data, dict):
            loaded.append(data)
    return loaded


def _derive_chan_order(td_recordings):
    order = []
    for r in td_recordings:
        for ch in r.get("ChannelNames", []) or []:
            if ch not in order:
                order.append(ch)
    return order


def _load_pros(request_data):
    """Resolve the PRO DataFrame.

    Priority: (1) `ProcessedPRO` records passed in the request body (list of dicts);
    (2) a REDCap pull when REDCAP_API_URL / REDCAP_API_TOKEN are set (optionally filtered to
    `RedcapRecordId`). Returns None when no PRO source is configured.
    """
    if request_data.get("ProcessedPRO"):
        return pd.DataFrame(request_data["ProcessedPRO"])
    if os.environ.get("REDCAP_API_URL") and os.environ.get("REDCAP_API_TOKEN"):
        df = redcap_client.pull_redcap()  # token via env vars
        df = df.reset_index()
        rid = request_data.get("RedcapRecordId")
        if rid is not None and "record_id" in df.columns:
            df = df[df["record_id"].astype(str) == str(rid)]
        return df.reset_index(drop=True)
    return None


# Participants seeded with this MRN return a synthetic timeline (no real Percept/REDCap needed),
# so the card can be demonstrated end-to-end before real data is loaded.
DEMO_MRN = "DEMO_BIOMARKER"


def _demo_inputs():
    """Synthetic recordings + chronic trend + PRO mirroring the package's test fixtures.

    Deterministic (fixed epoch base, seeded RNG). Even days = high pain (high LFP power, high
    [left_leg_vas, mpq_sum]); the chronic threshold detector and KMeans labeler both light up.
    """
    fs = 250.0
    midnight = 1_699_920_000.0  # 2023-11-14 00:00:00 UTC
    chan_order = ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"]
    rng = np.random.default_rng(0)

    days = 14

    # Streaming time-domain recordings, ONE PER DAY, with 30 Hz power scaling with that day's
    # pain (even days = high). So the streaming PSD<->pain correlation is real: the spectrum
    # peaks near 30 Hz and the selected-band biomarker series tracks pain across sessions.
    recordings = []
    for d in range(days):
        pain = 8.0 if d % 2 == 0 else 2.0
        n = int(8 * fs)
        t = np.arange(n) / fs
        amp30 = 1.0 + 0.15 * pain  # 30 Hz amplitude grows with pain
        ch0 = np.sin(2 * np.pi * 20 * t) + 0.3 * rng.standard_normal(n)          # 20 Hz, pain-independent
        ch1 = amp30 * np.sin(2 * np.pi * 30 * t) + 0.3 * rng.standard_normal(n)  # 30 Hz, ∝ pain
        recordings.append({
            "SamplingRate": fs, "ChannelNames": list(chan_order),
            "Data": np.column_stack([ch0, ch1]),
            "StartTime": midnight + d * 86_400 + 12 * 3_600, "Duration": n / fs,
        })

    # Chronic ~10-min trend over the same days (sampled every 2 h here).
    times, lfp, amp = [], [], []
    for d in range(days):
        high = (d % 2 == 0)
        for h in range(0, 24, 2):
            times.append(midnight + d * 86_400 + h * 3_600)
            lfp.append(150.0 if high else 110.0)
            amp.append(2.0)
    chronic = {"SamplingRate": -1, "Time": np.array(times, dtype=float),
               "Data": np.column_stack([np.array(lfp), np.array(amp)]),
               "ChannelNames": ["L LFP", "L Amplitude"]}

    pro = pd.DataFrame({
        "date_time_s1_daily": [pd.Timestamp(midnight + d * 86_400 + 12 * 3_600, unit="s").isoformat()
                               for d in range(days)],
        "nrs": [8 if d % 2 == 0 else 2 for d in range(days)],
        "left_leg_vas": [70 if d % 2 == 0 else 10 for d in range(days)],
        "mpq_sum": [40 if d % 2 == 0 else 5 for d in range(days)],
    })
    return recordings, chronic, pro, chan_order


def _demo_run(source):
    recordings, chronic, pro, chan_order = _demo_inputs()
    td = recordings if source in ("timedomain", "both") else []
    ch = chronic if source in ("chronic", "both") else None
    run = pipeline.run_biomarker(td, pro, chan_order, source=source, chronic=ch,
                                 train_days=3, gap_days=1, test_days=2)
    out = _serialize_run(run, _compute_analytics(run, ch, pro))
    out["message"] = "DEMO DATA — synthetic timeline (no real Percept/REDCap loaded)."
    return out


def _compute_analytics(run, chronic, pro_df, label_metric="nrs"):
    """Build the notebook-style analytics (sliding-window AUC/R, ROC, LFP/Otsu histogram, KMeans
    cluster scatter, and the streaming correlation spectrum). Each piece is guarded so an
    analytics failure never breaks the main timeline response.
    """
    result = {"timedomain": None, "chronic": None}

    td = run.get("timedomain")
    if td is not None:
        try:
            det = td["detail"]
            tl = td.get("timeline")
            times = [str(x) for x in tl["time"]] if (tl is not None and "time" in tl) else []
            result["timedomain"] = {
                "corr_spectrum": analytics.corr_spectrum(det),
                "psd_spectra": analytics.psd_spectra(det),
                "spectrogram": analytics.psd_spectrogram(det, times),
            }
        except Exception as e:
            result["timedomain"] = {"error": str(e)}

    if chronic is not None and pro_df is not None and len(pro_df) > 0:
        try:
            cv_df = adapter.bravo_chronic_to_lfp_df(chronic, pro_df, label_metric=label_metric)
            result["chronic"] = {
                "sliding_window": analytics.sliding_window_analytics(cv_df),
                "roc": analytics.roc_analysis(cv_df),
                "lfp_distribution": analytics.lfp_distribution(cv_df),
                "cluster_scatter": analytics.cluster_scatter(cv_df),
            }
        except Exception as e:
            result["chronic"] = {"error": str(e)}

    return result


def run_for_participant(request_data):
    """Assemble inputs from the DB + REDCap and run the biomarker pipeline for one participant.

    Returns a dict: {source, channels, timeline (records), summary, message}. `message` is
    non-empty (and timeline empty) when required inputs are missing -- the card renders that
    as a friendly state instead of erroring.
    """
    participant_uid = request_data["ParticipantId"]
    source = request_data.get("source", "both")
    if source not in ("timedomain", "chronic", "both"):
        source = "both"

    # Demo participant -> synthetic timeline (lets the card render before real data exists).
    Participant = models.Participant.find(uid=participant_uid)
    if Participant is not None and getattr(Participant, "mrn", "") == DEMO_MRN:
        return _demo_run(source)

    td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES) if source in ("timedomain", "both") else []
    chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES) if source in ("chronic", "both") else []
    pro_df = _load_pros(request_data)

    missing = []
    if source in ("timedomain", "both") and not td:
        missing.append("time-domain BrainSense recordings")
    if source in ("chronic", "both") and not chronic_list:
        missing.append("chronic BrainSense Timeline recordings")
    if pro_df is None or len(pro_df) == 0:
        missing.append("REDCap PRO data (set REDCAP_API_URL/REDCAP_API_TOKEN, or pass ProcessedPRO)")
    if missing:
        return {"source": source, "channels": [], "timeline": [], "summary": {},
                "message": "Cannot compute biomarker — missing: " + "; ".join(missing) + "."}

    chan_order = _derive_chan_order(td)
    chronic = chronic_list if chronic_list else None

    run = pipeline.run_biomarker(td, pro_df, chan_order, source=source, chronic=chronic)
    return _serialize_run(run, _compute_analytics(run, chronic, pro_df))


def _serialize_run(run, analytics_data=None):
    """Convert a run_biomarker result into the JSON-able dict the card consumes."""
    combined = run["combined"]
    if hasattr(combined, "to_dict"):
        combined = combined.copy()
        # Stringify datetime/date columns so DRF's JSON renderer can serialize them.
        for col in combined.columns:
            dtype = str(combined[col].dtype)
            if "datetime" in dtype or "date" in dtype or col in ("time", "date"):
                combined[col] = combined[col].astype(str)
        combined = combined.replace({np.nan: None})
        records = combined.to_dict(orient="records")
        channels = list(combined.columns)
    else:
        records, channels = [], []

    return {
        "source": run["source"],
        "channels": channels,
        "timeline": records,
        "summary": {
            "timedomain": run["timedomain"]["summary"] if run.get("timedomain") else None,
            "chronic": run["chronic"]["summary"] if run.get("chronic") else None,
        },
        "analytics": analytics_data,
        "message": "",
    }


# =============================================================================================
# Pain-score reports (Surveys & Questionnaires) -- visualizes the REDCap PRO pain metrics over
# time, the way Yiyuan's redcap_pull / full_trend_pain_score figures do.
# =============================================================================================

# (key, display label, [y-min, y-max]) -- mirrors dbs_stage2_percept/redcap_pull.py.
PAIN_METRICS = [
    ("nrs", "NRS (0–10)", [0, 10]),
    ("vas", "Overall VAS", [0, 100]),
    ("left_leg_vas", "Left Leg VAS", [0, 100]),
    ("back_vas", "Back VAS", [0, 100]),
    ("relief", "Relief (%)", [0, 100]),
    ("mpq_sum", "MPQ Sum", [0, 72]),
    ("mpq_aff", "MPQ Affective", [0, 16]),
    ("mpq_sen", "MPQ Sensory", [0, 56]),
    ("electrocuting", "Electrocuting", [0, 3]),
    ("tingly", "Tingly", [0, 3]),
]


def _demo_pain_scores():
    """Synthetic daily pain-score reports over ~30 days (gradual improvement + daily variation,
    with a few missing days to show gaps). Deterministic."""
    midnight = 1_699_920_000.0
    days = 30
    rng = np.random.default_rng(1)
    rows = []
    for d in range(days):
        if rng.random() < 0.15:  # missed report
            continue
        frac = d / (days - 1)
        nrs = float(np.clip(8 - 4.5 * frac + rng.normal(0, 0.9), 0, 10))
        relief = float(np.clip(10 + 55 * frac + rng.normal(0, 8), 0, 100))
        rows.append({
            "date_time_s1_daily": pd.Timestamp(midnight + d * 86_400 + 12 * 3_600, unit="s").isoformat(),
            "nrs": round(nrs, 1),
            "vas": float(np.clip(nrs * 10 + rng.normal(0, 6), 0, 100)),
            "left_leg_vas": float(np.clip(nrs * 9 + rng.normal(0, 8), 0, 100)),
            "back_vas": float(np.clip(nrs * 7 + rng.normal(0, 10), 0, 100)),
            "relief": round(relief, 0),
            "mpq_sum": float(np.clip(42 - 22 * frac + rng.normal(0, 4), 0, 72)),
            "mpq_aff": float(np.clip(11 - 6 * frac + rng.normal(0, 1.5), 0, 16)),
            "mpq_sen": float(np.clip(31 - 16 * frac + rng.normal(0, 3), 0, 56)),
        })
    return pd.DataFrame(rows)


def pain_scores_for_participant(request_data):
    """Return the participant's pain-score reports over time, per metric, JSON-able for the card.

    Demo participant -> synthetic; otherwise REDCap PROs (env vars) or `ProcessedPRO` in the body.
    """
    from .routines.analytics import _f

    participant_uid = request_data["ParticipantId"]
    Participant = models.Participant.find(uid=participant_uid)
    demo = Participant is not None and getattr(Participant, "mrn", "") == DEMO_MRN

    pro = _demo_pain_scores() if demo else _load_pros(request_data)
    if pro is None or len(pro) == 0:
        return {"metrics": [], "n_reports": 0,
                "message": "No pain-score reports found. Set REDCAP_API_URL / REDCAP_API_TOKEN "
                           "(or pass ProcessedPRO) to load this patient's REDCap surveys."}

    ts_col = "date_time_s1_daily"
    if ts_col not in pro.columns:
        return {"metrics": [], "n_reports": 0,
                "message": "PRO data has no 'date_time_s1_daily' timestamp column."}

    t = pd.to_datetime(pro[ts_col], errors="coerce")
    metrics = []
    for key, label, rng_ in PAIN_METRICS:
        if key not in pro.columns:
            continue
        vals = pd.to_numeric(pro[key], errors="coerce")
        pts = [{"t": str(tt), "v": _f(v)} for tt, v in zip(t, vals) if pd.notna(tt) and pd.notna(v)]
        if pts:
            pts.sort(key=lambda p: p["t"])
            metrics.append({"key": key, "label": label, "range": rng_, "points": pts})

    # Pearson correlation between metrics (pairwise over aligned reports).
    present = [m["key"] for m in metrics]
    correlation = {"keys": [], "labels": [], "matrix": []}
    if len(present) >= 2:
        num = pro[present].apply(pd.to_numeric, errors="coerce")
        cmat = num.corr(method="pearson")
        label_of = {m["key"]: m["label"] for m in metrics}
        correlation = {
            "keys": present,
            "labels": [label_of[k] for k in present],
            "matrix": [[_f(cmat.loc[a, b]) for b in present] for a in present],
        }

    return {"metrics": metrics, "n_reports": int(t.notna().sum()), "correlation": correlation,
            "message": "DEMO DATA — synthetic pain-score reports." if demo else ""}
