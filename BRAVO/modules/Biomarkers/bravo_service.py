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
