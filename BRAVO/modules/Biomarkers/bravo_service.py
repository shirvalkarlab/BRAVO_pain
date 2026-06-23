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
import json
import math
import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from Server import models
from modules import Database

from . import pipeline
from . import adapter
from .routines import redcap_client
from .routines import analytics
from .routines import availability
from .routines import streaming_psd

_log = logging.getLogger(__name__)

# DB recording types. Time-domain = raw 250 Hz LFP. The "power domain" source merges TWO
# band-power-over-time streams: the ~10-min Chronic (BrainSense Timeline) trend AND the per-session
# BrainSense Power-Domain band power — concatenated so power is compared apples-to-apples.
TIMEDOMAIN_TYPES = ["MedtronicBrainSenseTimeDomain", "MedtronicIndefiniteStream"]
CHRONIC_TYPES = ["MedtronicChronicBrainSense"]
POWERDOMAIN_TYPES = ["MedtronicBrainSensePowerDomain"]
# PSD-bearing products (montage surveys) for the data-availability timeline — loaded ONLY for the
# availability payload (they don't feed the decoder). See routines/availability.AVAILABILITY_TYPES.
# Patient-triggered LABELED events: button presses the patient annotated ("Higher Pain",
# "Tingly/Burning", "Feeling Good", "Medication", ...). Stored as PatientControllerEvent rows whose
# `metadata` carries, per hemisphere, the event DateTime + a full-band PSD (Frequency/FFTBinData).
# Auto-generated "Streaming" markers are excluded. These only corroborate (DESIGN §2/§6), never feed
# the decoder, but are demarcated (with their label) on the timeline.
PATIENT_EVENT_TYPE = "PatientControllerEvent"
_EVENT_NAME_EXCLUDE = {"streaming"}   # auto-markers, not patient annotations (timeline display only)
AVAILABILITY_PSD_TYPES = ["MedtronicBrainSenseSurvey", "MedtronicBaselineMontages",
                          "MedtronicStimulationMontages"]

# Source label for PSDs harvested from PatientControllerEvent markers (incl. "Streaming" markers the
# patient was instructed to fire around each survey). These carry the device's ONBOARD FFT
# (Frequency/FFTBinData on the row metadata) rather than a Welch-of-time-domain spectrum, so they sit
# ~6 dB higher than the TD/Montage Welch PSDs on the same channel. That constant offset is removed
# automatically because the matrix builder z-scores within (channel, source): tagging events as their
# own source makes them poolable with the rest without re-scaling. (psd_rows_to_matrix already lists
# "Patient event" as a recognised source.)
EVENT_PSD_SOURCE = "Patient event"

# Map a patient-event PSD block to its canonical bipolar channel. The block's identity lives in
# SenseID (a SensingElectrodeConfigDef, e.g. "...ZERO_AND_THREE") plus the hemisphere key; SenseID is
# frequently blank, so we fall back to the hemisphere's habitual sensing pair, established empirically
# on RCS08: Right hemisphere always sensed ZERO_AND_THREE (-> ZERO_THREE_RIGHT) across all groups;
# Left hemisphere sensed ONE_AND_THREE (-> ONE_THREE_LEFT). An explicit SenseID overrides the default.
_EVENT_SENSE_CONTACT = {
    "ZERO_AND_THREE": "ZERO_THREE", "ONE_AND_THREE": "ONE_THREE",
    "ZERO_AND_TWO": "ZERO_TWO", "ONE_AND_TWO": "ONE_TWO",
}
_EVENT_HEMI_DEFAULT_CONTACT = {"Right": "ZERO_THREE", "Left": "ONE_THREE"}

# How many worker threads the recording loader uses. Decoding each .bdat is independent and
# largely GIL-friendly (file I/O + numpy), so threads give near-linear speedup. Defaults to all
# available cores; override with BRAVO_BIOMARKER_THREADS.
def _loader_threads():
    try:
        env = int(os.environ.get("BRAVO_BIOMARKER_THREADS", "0"))
        if env > 0:
            return env
    except (TypeError, ValueError):
        pass
    return os.cpu_count() or 4


# Pain metrics the LFP biomarker can be computed against (correlated for time-domain; clustered
# into the binary pain_level for the chronic detector). The composite is a normalized blend of
# MPQ sum + left-leg VAS. `key` must be a column in the tidy PRO table (composite is synthesized).
BIOMARKER_METRICS = [
    {"key": "nrs", "label": "NRS (0–10)"},
    {"key": "vas", "label": "Overall VAS"},
    {"key": "left_leg_vas", "label": "Left Leg VAS"},
    {"key": "back_vas", "label": "Back VAS"},
    {"key": "mpq_sum", "label": "MPQ Sum"},
    {"key": "composite_mpq_leftleg", "label": "Composite (MPQ + Left Leg VAS)"},
]
DEFAULT_BIOMARKER_METRIC = "nrs"
COMPOSITE_METRIC = "composite_mpq_leftleg"
COMPOSITE_PARTS = ("mpq_sum", "left_leg_vas")


def _resolve_biomarker_metric(request_data, pro_df):
    """Resolve the requested `LabelMetric` against `pro_df`.

    Returns (pro_df, label_metric, kmeans_features):
      * label_metric   : PRO column the biomarker is computed against (time-domain PSD<->pain
                         correlation; chronic carried/display metric). For the composite this is
                         a freshly-added, min-max-normalized (0–100) blend column.
      * kmeans_features: feature(s) the chronic detector clusters into the binary pain_level —
                         a single selected metric -> [metric]; the composite -> [mpq_sum,
                         left_leg_vas] (which is also the source notebook's 2-D KMeans labeler).
    Unknown selections, or a composite whose parts are absent, fall back to the default metric.
    """
    metric = request_data.get("LabelMetric") or DEFAULT_BIOMARKER_METRIC
    if metric not in {m["key"] for m in BIOMARKER_METRICS}:
        metric = DEFAULT_BIOMARKER_METRIC

    if metric == COMPOSITE_METRIC:
        parts = [p for p in COMPOSITE_PARTS if p in pro_df.columns]
        if parts:
            df = pro_df.copy()
            # Z-SCORE each part across all surveys, then average the available parts per row.
            # Standardizing by spread (not min-max range) means outliers don't set the scale and
            # each PRO contributes equal variance to the blend. Averaging only the parts present on
            # a row (skipna) also keeps a day whenever EITHER part exists, instead of dropping it
            # when one is missing — on RCS08 this lifted composite coverage 253 -> 312 days and
            # improved both LFP separability and balance over the old min-max blend
            # (see docs/binarization_recommendation_RCS08.md). Only parts that actually VARY
            # (finite, non-constant) contribute.
            zcols = []
            for p in parts:
                v = pd.to_numeric(df[p], errors="coerce")
                arr = v.to_numpy(dtype=float)
                if np.isfinite(arr).any():
                    mu, sd = np.nanmean(arr), np.nanstd(arr)
                    if sd > 0:
                        zcols.append((v - mu) / sd)
            if zcols:
                df[COMPOSITE_METRIC] = pd.concat(zcols, axis=1).mean(axis=1, skipna=True)
                return df, COMPOSITE_METRIC, tuple(parts)
        metric = DEFAULT_BIOMARKER_METRIC  # no usable composite signal -> fall back

    return pro_df, metric, (metric,)


def _load_recordings(participant_uid, types):
    """Return a list of loaded recording dicts for a participant, for the given DB types."""
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    Recordings = list(models.Recording.find_all(source__in=SourceFiles, type__in=types))
    if not Recordings:
        return []

    # Decode the .bdat files concurrently — independent reads, so this scales with cores. Only
    # the file pointer/hash (already-fetched attrs) are touched per task, so no ORM call runs in
    # a worker thread. Each task returns the decoded payload (or None on failure).
    def _decode(rec):
        try:
            data = Database.loadSourceFile(rec.pointer, rec.hashed)
            # Carry the chronic-trend sensing CENTER FREQUENCY forward. It is stored on the
            # Recording.metadata (stamped at decode time from the GROUP-level config) rather than in
            # the .bdat payload, so merge it onto the loaded dict(s) here so the report can label the
            # chronic trend with its sensing frequency.
            chz = None
            fsched = None
            csched = None
            md = getattr(rec, "metadata", None)
            if isinstance(md, dict):
                chz = md.get("CenterFrequencyHz")
                fsched = md.get("FreqScheduleHz")
                csched = md.get("ContactSchedule")
            if chz is not None or fsched is not None or csched is not None:
                for d in (data if isinstance(data, list) else [data]):
                    if isinstance(d, dict):
                        if chz is not None:
                            d.setdefault("CenterFrequencyHz", chz)
                        if fsched is not None:
                            d.setdefault("FreqScheduleHz", fsched)
                        if csched is not None:
                            d.setdefault("ContactSchedule", csched)
            return data
        except Exception:
            # Per-file resilience: one corrupt/undecodable recording must not sink the whole
            # threaded load. But log it (pointer only, never the payload) so a SYSTEMATIC decode
            # failure is diagnosable instead of silently yielding an empty timeline that looks
            # identical to "no recordings".
            _log.warning("Biomarkers: failed to decode recording %r; skipping",
                         getattr(rec, "pointer", "?"), exc_info=True)
            return None

    workers = max(1, min(len(Recordings), _loader_threads()))
    loaded = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for data in pool.map(_decode, Recordings):
            if isinstance(data, list):
                loaded.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                loaded.append(data)
    return loaded


def _load_patient_events(participant_uid):
    """Load patient-annotated LFP snapshot events for the availability timeline.

    These are PatientControllerEvent rows — button presses the patient labeled ("Higher Pain",
    "Tingly/Burning", "Feeling Good", "Medication", ...). Unlike the .bdat recordings, the event's
    time and per-hemisphere PSD live on the ROW's `metadata` (one subdict per hemisphere, each with
    `DateTime`, `Frequency`, `FFTBinData`), so we read them off the ORM directly — no file decode.

    The auto-generated "Streaming" markers are excluded (not patient annotations). The authoritative
    timestamp is the per-hemisphere `DateTime` (ISO-Z); we fall back to the row's `date` if absent.

    Returns [{"name": str, "t": epoch_s, "psds": [(freq_list, power_list), ...]}, ...].
    """
    import datetime as _dt
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    rows = list(models.Recording.find_all(source__in=SourceFiles, type=PATIENT_EVENT_TYPE))
    out = []
    for r in rows:
        name = getattr(r, "name", "") or ""
        if not name or name.strip().lower() in _EVENT_NAME_EXCLUDE:
            continue
        md = getattr(r, "metadata", None)
        if not isinstance(md, dict):
            continue
        t = None
        psds = []
        for hemi_block in md.values():
            if not isinstance(hemi_block, dict):
                continue
            if t is None and hemi_block.get("DateTime"):
                try:
                    t = _dt.datetime.fromisoformat(
                        str(hemi_block["DateTime"]).replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    t = None
            freq = hemi_block.get("Frequency")
            power = hemi_block.get("FFTBinData")
            if isinstance(freq, (list, tuple)) and isinstance(power, (list, tuple)) \
                    and len(freq) == len(power) and len(freq) > 0:
                psds.append((list(freq), list(power)))
        if t is None:
            t = getattr(r, "date", None)
        if t is None:
            continue
        out.append({"name": name, "t": float(t), "psds": psds})
    return out


def _event_block_channel(hemi_key, sense_id):
    """Resolve a patient-event PSD block's canonical bipolar channel (e.g. 'ZERO_THREE_RIGHT').

    `hemi_key` is the metadata key for this block (e.g. 'HemisphereLocationDef.Right'); `sense_id`
    is its SenseID (e.g. 'SensingElectrodeConfigDef.ZERO_AND_THREE' or '' / None). The contact pair
    comes from SenseID when present, else from the hemisphere's habitual sensing pair
    (`_EVENT_HEMI_DEFAULT_CONTACT`). Returns a name in `_MAIN_BIPOLAR`, or None if it can't be
    resolved to one of the six main bipolar channels."""
    hemi = "Right" if str(hemi_key).endswith("Right") else ("Left" if str(hemi_key).endswith("Left") else None)
    if hemi is None:
        return None
    contact = None
    if sense_id:
        tail = str(sense_id).split(".")[-1]
        contact = _EVENT_SENSE_CONTACT.get(tail)
    if contact is None:
        contact = _EVENT_HEMI_DEFAULT_CONTACT.get(hemi)
    if contact is None:
        return None
    name = f"{contact}_{hemi.upper()}"
    return name if name in _MAIN_BIPOLAR else None


def _event_psd_rows(participant_uid):
    """Harvest EVERY PatientControllerEvent PSD (incl. the auto 'Streaming' markers) as poolable
    PSD rows for the per-channel biomarker scan.

    Unlike `_load_patient_events` (timeline display, which drops 'Streaming' and pools hemispheres
    without channel identity), this assigns each per-hemisphere FFT block to its canonical bipolar
    channel (`_event_block_channel`) so the spectra join the same per-channel pool as TD/Montage.
    The onboard-FFT vs Welch scale offset is absorbed by the within-(channel, source) z-score, since
    every row here is tagged `source=EVENT_PSD_SOURCE`. No .bdat decode — the spectra live on the
    ORM row `metadata`, one subdict per hemisphere with `DateTime` / `Frequency` / `FFTBinData`.

    Returns a list of {"channel", "source", "t": epoch_s, "freq", "power"} rows — the SAME schema
    `_welch_rows_into` emits, ready for `streaming_psd.psd_rows_to_matrix`.
    """
    import datetime as _dt
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    rows = []
    for r in models.Recording.find_all(source__in=SourceFiles, type=PATIENT_EVENT_TYPE):
        md = getattr(r, "metadata", None)
        if not isinstance(md, dict):
            continue
        for hemi_key, hb in md.items():
            if not isinstance(hb, dict):
                continue
            ch = _event_block_channel(hemi_key, hb.get("SenseID"))
            if ch is None:
                continue
            freq = hb.get("Frequency")
            power = hb.get("FFTBinData")
            if not (isinstance(freq, (list, tuple)) and isinstance(power, (list, tuple))
                    and len(freq) == len(power) and len(freq) > 0):
                continue
            t = None
            if hb.get("DateTime"):
                try:
                    t = _dt.datetime.fromisoformat(
                        str(hb["DateTime"]).replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    t = None
            if t is None:
                t = getattr(r, "date", None)
            if t is None:
                continue
            rows.append({"channel": ch, "source": EVENT_PSD_SOURCE, "t": float(t),
                         "freq": np.asarray(freq, dtype=float),
                         "power": np.asarray(power, dtype=float)})
    return rows


def _event_psd_index(participant_uid):
    """Lightweight {t, channel, source} index of the patient-event PSDs (incl. 'Streaming'), one
    entry per (event, hemisphere block) assigned to its canonical bipolar channel — the SAME set
    `_event_psd_rows` pools into the matrix, minus the freq/power arrays. Feeds `psd_scan_index` so
    the imported event PSDs render as tick marks on their contact lanes and the live binarization
    preview counts them, mirroring the backend pool (TD + montage + Patient event)."""
    import datetime as _dt
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    out = []
    for r in models.Recording.find_all(source__in=SourceFiles, type=PATIENT_EVENT_TYPE):
        md = getattr(r, "metadata", None)
        if not isinstance(md, dict):
            continue
        ev_name = (getattr(r, "name", "") or "").strip() or "Event"
        for hemi_key, hb in md.items():
            if not isinstance(hb, dict):
                continue
            ch = _event_block_channel(hemi_key, hb.get("SenseID"))
            if ch is None:
                continue
            freq = hb.get("Frequency"); power = hb.get("FFTBinData")
            if not (isinstance(freq, (list, tuple)) and isinstance(power, (list, tuple))
                    and len(freq) == len(power) and len(freq) > 0):
                continue
            t = None
            if hb.get("DateTime"):
                try:
                    t = _dt.datetime.fromisoformat(
                        str(hb["DateTime"]).replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    t = None
            if t is None:
                t = getattr(r, "date", None)
            if t is None:
                continue
            out.append({"t": float(t), "channel": ch, "source": EVENT_PSD_SOURCE,
                        "name": ev_name})
    return out


def _load_montage_psd_events(participant_uid, dedup_times=None, tol_s=5.0):
    """Load NeuralActivitySnapshot montage sweeps as montage-PSD marker events, de-duplicated
    against the montage/survey PSD recordings that ALREADY render on the timeline.

    A NeuralActivitySnapshot is an automatic ~20 s montage survey: full-band Welch PSDs over
    reference-montage channels (`PSD[i] = {Frequency, Power, ...}`). ~80% of them coincide (within
    a few seconds) with a MedtronicBrainSenseSurvey/Montages recording already shown as PSD ticks,
    so to avoid double-counting we DROP any snapshot whose StartTime is within `tol_s` of a time in
    `dedup_times` (the montage/survey PSD record StartTimes). The remainder — montage sweeps with no
    matching survey/montage recording — are surfaced as their own markers.

    Returns events normalized for `availability.event_markers`:
        [{"name": "Montage PSD", "t": epoch_s, "psds": [(freq, power), ...]}, ...]
    """
    snaps = _load_recordings(participant_uid, ["NeuralActivitySnapshot"])
    dedup = sorted(float(t) for t in (dedup_times or []) if t is not None)
    import bisect
    def _is_dup(t):
        if not dedup:
            return False
        i = bisect.bisect_left(dedup, t)
        for j in (i - 1, i):
            if 0 <= j < len(dedup) and abs(dedup[j] - t) <= tol_s:
                return True
        return False
    out = []
    for s in snaps:
        if not isinstance(s, dict):
            continue
        t0 = availability._to_epoch(s.get("StartTime"))
        if t0 is None or _is_dup(t0):
            continue
        psds = []
        for p in (s.get("PSD") or []):
            if isinstance(p, dict):
                f, m = p.get("Frequency"), p.get("Power")
                if f is not None and m is not None and len(f) == len(m) and len(f) > 0:
                    psds.append((list(f), list(m)))
        out.append({"name": "Montage PSD", "t": float(t0), "psds": psds})
    return out


# The six main bipolar sensing pairs (per hemisphere). The exploratory spectral scan is restricted
# to these — ring/segment montages and reference-electrode channels are dropped (they aren't the
# closed-loop sensing channels and don't map to a single bipolar pair). DESIGN: channel is the gate.
_MAIN_BIPOLAR = {
    "ZERO_THREE_LEFT", "ZERO_THREE_RIGHT", "ONE_THREE_LEFT", "ONE_THREE_RIGHT",
    "ZERO_TWO_LEFT", "ZERO_TWO_RIGHT",
}

# Bump when the channel-canonicalization rule below changes — folded into the PSD-matrix cache
# signature so a rule change forces a re-Welch instead of serving the stale pre-fix matrix.
_CHANNEL_CANON_VERSION = "v2_ring_aware"


def _canon_channel(name):
    """Normalize a Medtronic channel name to the canonical bipolar form used by `_MAIN_BIPOLAR`.

    The same physical bipolar pair is spelled differently across products:
      * TD streaming / Stim+Baseline montages:  `ZERO_THREE_LEFT`         (already canonical)
      * BrainSense Survey / montage sweeps:      `ZERO_AND_THREE_LEFT_RING`

    Before this normalizer the per-channel scan tested membership with an EXACT string match, so the
    Survey product's ring-named channels never matched and its 202 recordings contributed ZERO rows
    to the pool (the pool only looked healthy because Stim/Baseline montages re-export three of the
    same pairs under the short spelling). Stripping `_AND_` and the `_RING` suffix maps the ring
    names onto the canonical pairs (`ZERO_AND_THREE_LEFT_RING` -> `ZERO_THREE_LEFT`); already-short
    names are unchanged (idempotent). Returns the canonical upper-case name.
    """
    u = str(name).upper().replace("_AND_", "_")
    if u.endswith("_RING"):
        u = u[:-len("_RING")]
    return u

# Single-worker pool that warms the PSD-matrix cache off the request thread (eager compute while the
# user reviews the availability timeline). Daemon threads so it never blocks process shutdown.
_PSD_WARM_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="psd-warm")


def _assemble_psd_rows(participant_uid, td_list, psd_list):
    """Gather EVERY full-spectrum PSD for the main bipolar channels, one row per (recording, channel).

    Two full-spectrum sources carry the main bipolar pairs:
      * TD streaming (BrainSenseTimeDomain + IndefiniteStream): raw 250 Hz time domain -> Welch PSD.
      * Montage/survey (Survey + Baseline + Stim Montages): also raw time domain -> Welch PSD; these
        sweep all six bipolar pairs.
    (NeuralActivitySnapshot and patient-event PSDs use reference-montage / per-hemisphere identities
    that don't correspond to a single bipolar pair, so they're excluded from the per-channel scan —
    they remain timeline markers.)

    Returns a list of {"channel", "source", "t": epoch_s, "freq", "power"} — the input to
    `streaming_psd.psd_rows_to_matrix`. The Welch transform here is the expensive part that the
    cache exists to avoid repeating.
    """
    from .routines import streaming_psd as _sp
    rows = []
    _welch_rows_into(rows, td_list, "TD streaming", _sp)
    _welch_rows_into(rows, psd_list, "Montage/survey", _sp)
    # Patient-event PSDs (ORM metadata, no decode) — keeps this legacy path consistent with the
    # cached assembly so a matrix built either way carries the same "Patient event" source.
    try:
        rows.extend(_event_psd_rows(participant_uid))
    except Exception:
        pass
    return rows


def _welch_rows_into(rows, recs, source_label, _sp):
    """Welch every main-bipolar channel of each loaded recording dict, appending one
    {"channel", "source", "t", "freq", "power"} row per (recording-instance, channel) to `rows`.

    Single source of truth for the row schema: BOTH the legacy whole-participant assembly
    (`_assemble_psd_rows`) and the per-recording cache (`_recording_psd_rows`) build rows through
    here, so a matrix assembled from the cache is byte-identical to one assembled the old way.
    """
    for r in recs or []:
        if not isinstance(r, dict):
            continue
        names = list(r.get("ChannelNames") or [])
        # Test membership on the CANONICAL form so ring-named survey channels are kept, but carry the
        # RAW name forward (Welch selects channels by raw name from the signal below).
        keep = [(i, n) for i, n in enumerate(names) if _canon_channel(n) in _MAIN_BIPOLAR]
        if not keep:
            continue
        data = np.asarray(r.get("Data"))
        if data.ndim != 2:
            continue
        # welch expects (n_ch, n_samples); montage/TD Data is (n_samples, n_ch).
        sig = data.T if data.shape[0] != len(names) else data
        fs = float(r.get("SamplingRate") or 250.0)
        t0 = availability._to_epoch(r.get("StartTime"))
        if t0 is None:
            continue
        keep_names = [n for _, n in keep]
        try:
            psd = _sp.welch_psd_for_instance(sig, names, fs, keep_names)  # (1, k, F)
        except Exception:
            continue
        psd = np.asarray(psd)
        # Duration (s) actually used by Welch for this recording = min(window, available). Reported
        # downstream as mean +/- SD so the clinician knows the TD epoch length feeding each PSD.
        nsamp = int(sig.shape[-1])
        used_dur = float(min(_sp.WELCH_MAX_SECONDS, nsamp / fs)) if fs > 0 else float("nan")
        for j, n in enumerate(keep_names):
            # Store the CANONICAL channel so ring-named survey rows pool with the short-named TD/Stim
            # rows for the same physical bipolar pair (e.g. ZERO_AND_THREE_LEFT_RING -> ZERO_THREE_LEFT).
            rows.append({"channel": _canon_channel(n), "source": source_label,
                         "t": float(t0), "freq": _sp.F_SET, "power": psd[0, j, :],
                         "dur": used_dur})


def _psd_sample_index(td_list, psd_list):
    """Lightweight index of the scan's pooled-PSD samples: one entry per (recording, channel) the
    full-spectrum scan would include, WITHOUT the expensive Welch transform.

    Uses the IDENTICAL channel filter as `_assemble_psd_rows` (membership in `_MAIN_BIPOLAR`, same
    source labels), so the set of (t, channel, source) entries here equals the rows that feed the
    pooled PSD matrix — modulo the rare degenerate spectrum Welch drops (<4 finite bins), which
    effectively never occurs on real recordings. This lets the frontend replicate the backend's
    nearest-PRO match + binarization LIVE as the match-window slider moves, so the binarization
    histogram and the timeline coloring stay faithful to `matched_sample_counts` without a recompute.

    Returns a list of {"t": epoch_s, "channel": "<CANON>_<HEMI>", "source": str}.
    """
    out = []

    def _index(recs, source_label):
        for r in recs or []:
            if not isinstance(r, dict):
                continue
            names = list(r.get("ChannelNames") or [])
            keep = [n for n in names if _canon_channel(n) in _MAIN_BIPOLAR]
            if not keep:
                continue
            t0 = availability._to_epoch(r.get("StartTime"))
            if t0 is None:
                continue
            for n in keep:
                out.append({"t": float(t0), "channel": _canon_channel(n), "source": source_label})

    _index(td_list, "TD streaming")
    _index(psd_list, "Montage/survey")
    return out


def _psd_cache_dir():
    try:
        from django.conf import settings
        base = getattr(settings, "DATASERVER_PATH", None) or os.environ.get("DATASERVER_PATH") or "/tmp/"
    except Exception:
        base = os.environ.get("DATASERVER_PATH") or "/tmp/"
    d = os.path.join(base, "cache", "biomarker_psd")
    os.makedirs(d, exist_ok=True)
    return d


def _psd_rows_cache_dir():
    """Directory for the PER-RECORDING PSD-row cache (one .npz per recording instance).

    Distinct from `_psd_cache_dir` (the whole-participant assembled matrix). The per-recording cache
    is keyed by the recording's DB identity (uid + hashed), BOTH of which are columns on the
    Recording row — so we can tell whether a recording's spectra are already cached WITHOUT opening
    its .bdat file. That is what lets the compute path skip the ~190 s cold decode of recordings it
    has already Welch'd: only the genuinely-new files are loaded.
    """
    base_dir = os.path.dirname(_psd_cache_dir())   # .../cache
    d = os.path.join(base_dir, "biomarker_psd_rows")
    os.makedirs(d, exist_ok=True)
    return d


def _recording_psd_cache_path(rec_uid, rec_hash):
    """Cache path for one recording's PSD rows. Keyed by uid + a short slice of the stored hash, so
    re-uploading the same data (new uid) or a content change (new hash) both miss and recompute.
    The Welch epoch length is also in the key: changing it produces different spectra, so the file
    name carries it (w<sec>) and a window change misses the old cache instead of serving stale PSDs."""
    from .routines import streaming_psd as _sp
    h = (str(rec_hash or "") or "nohash")[:16]
    w = str(_sp.WELCH_MAX_SECONDS).replace(".", "p")
    # Channel-canon rule is in the key too: a Survey recording previously cached with ZERO kept rows
    # (ring names dropped) must miss and re-Welch under the ring-aware rule instead of serving empty.
    return os.path.join(_psd_rows_cache_dir(), f"{rec_uid}_{h}_w{w}_{_CHANNEL_CANON_VERSION}.npz")


def _save_recording_psd_rows(path, rows):
    """Persist one recording's PSD rows (the per-channel spectra) to a compact .npz.

    `rows` is a list of {"channel","source","t","freq","power"} for a SINGLE recording instance.
    Stored as parallel arrays; an empty list is still written (a valid 0-row cache entry) so a
    recording that legitimately yields no main-bipolar spectra is not re-decoded every time.
    """
    chans = np.asarray([str(r["channel"]) for r in rows], dtype=object)
    srcs = np.asarray([str(r["source"]) for r in rows], dtype=object)
    ts = np.asarray([float(r["t"]) for r in rows], dtype=float)
    durs = np.asarray([float(r.get("dur", np.nan)) for r in rows], dtype=float)
    powers = np.asarray([np.asarray(r["power"], dtype=float) for r in rows], dtype=float) \
        if rows else np.zeros((0, 0), dtype=float)
    freq = np.asarray(rows[0]["freq"], dtype=float) if rows else np.zeros((0,), dtype=float)
    # np.savez APPENDS ".npz" if the name lacks it, so the temp name must already end in ".npz"
    # (else savez writes "<tmp>.npz" and the os.replace below moves a nonexistent file). Keep ".npz".
    tmp = path[:-4] + ".tmp.npz" if path.endswith(".npz") else path + ".tmp.npz"
    np.savez(tmp, channel=chans, source=srcs, t=ts, dur=durs, power=powers, freq=freq,
             n=np.asarray([len(rows)]))
    os.replace(tmp, path)   # atomic — a concurrent reader never sees a half-written file


def _load_recording_psd_rows(path):
    """Reload one recording's PSD rows from its .npz, reconstructing the row dicts (or None on miss/
    error so the caller recomputes). Returns a possibly-empty list when the cache entry is valid."""
    try:
        z = np.load(path, allow_pickle=True)
        n = int(z["n"][0])
        if n == 0:
            return []
        freq = z["freq"]
        chans, srcs, ts, powers = z["channel"], z["source"], z["t"], z["power"]
        durs = z["dur"] if "dur" in z.files else None   # older cache entries lack dur
        return [{"channel": str(chans[i]), "source": str(srcs[i]), "t": float(ts[i]),
                 "freq": freq, "power": powers[i],
                 "dur": (float(durs[i]) if durs is not None else float("nan"))}
                for i in range(n)]
    except Exception as e:
        _log.warning("Biomarkers: per-recording PSD cache read failed (%s); will recompute", e)
        return None


def _recording_rows_for_psd(participant_uid):
    """ORM-only: the Recording rows that feed the PSD matrix (TD streaming + montage/survey), with
    just the identity columns needed to consult the per-recording cache — NO .bdat decode.

    Returns [{"rec": <Recording>, "uid": str, "hash": str, "source": str}], where `source` is the
    SAME label `_assemble_psd_rows` uses ("TD streaming" / "Montage/survey"), so cache hits and the
    freshly-Welch'd rows carry identical source strings.
    """
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return []
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return []
    out = []
    for types, source_label in ((TIMEDOMAIN_TYPES, "TD streaming"),
                                (AVAILABILITY_PSD_TYPES, "Montage/survey")):
        for rec in models.Recording.find_all(source__in=SourceFiles, type__in=types):
            out.append({"rec": rec, "uid": rec.uid, "hash": getattr(rec, "hashed", ""),
                        "source": source_label})
    return out


def _assemble_psd_rows_cached(participant_uid):
    """Assemble the full PSD-row list for a participant using the per-recording cache, decoding +
    Welch'ing ONLY the recordings whose spectra are not already on disk.

    This is the load-skipping fast path behind `_cached_psd_matrix`: a participant whose recordings
    are all cached pays zero .bdat decodes (the ~190 s cold load disappears); a partially-warm
    participant pays only for the new files. The resulting rows are identical to
    `_assemble_psd_rows(td_list, psd_list)` because both go through `_welch_rows_into`.

    Returns (rows, n_cached, n_computed) — the row counts let callers log/verify the cache hit rate.
    """
    from .routines import streaming_psd as _sp
    entries = _recording_rows_for_psd(participant_uid)
    if not entries:
        return [], 0, 0

    rows = []
    n_cached = 0
    missing = []   # entries needing a decode+Welch
    for e in entries:
        path = _recording_psd_cache_path(e["uid"], e["hash"])
        cached = _load_recording_psd_rows(path) if os.path.exists(path) else None
        if cached is not None:
            rows.extend(cached)
            n_cached += 1
        else:
            missing.append(e)

    n_computed = 0
    if missing:
        # Decode only the misses, concurrently (same threaded decode as _load_recordings), then
        # Welch each recording's dict(s) in isolation and cache its rows keyed by that recording.
        def _decode(e):
            rec = e["rec"]
            try:
                data = Database.loadSourceFile(rec.pointer, rec.hashed)
            except Exception:
                _log.warning("Biomarkers: failed to decode recording %r for PSD cache; skipping",
                             getattr(rec, "pointer", "?"), exc_info=True)
                return e, None
            dicts = [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]
            return e, dicts

        workers = max(1, min(len(missing), _loader_threads()))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for e, dicts in pool.map(_decode, missing):
                rec_rows = []
                if dicts:
                    _welch_rows_into(rec_rows, dicts, e["source"], _sp)
                rows.extend(rec_rows)
                n_computed += 1
                # Persist this recording's rows (even if empty) so it is never re-decoded.
                try:
                    _save_recording_psd_rows(_recording_psd_cache_path(e["uid"], e["hash"]), rec_rows)
                except Exception as ex:
                    _log.warning("Biomarkers: per-recording PSD cache write failed (%s)", ex)

    # Patient-event PSDs (incl. Streaming markers): read off ORM metadata, no decode/Welch, so they
    # need no per-recording cache. Appended on every assembly — newly-ingested files with event
    # markers therefore enter the pool automatically (the matrix signature below tracks them).
    try:
        ev_rows = _event_psd_rows(participant_uid)
        rows.extend(ev_rows)
        if ev_rows:
            _log.info("Biomarkers: appended %d patient-event PSD rows for %s", len(ev_rows),
                      participant_uid)
    except Exception as ex:
        _log.warning("Biomarkers: patient-event PSD harvest failed (%s); pool excludes events", ex)

    return rows, n_cached, n_computed


def _psd_matrix_signature(td_list, psd_list):
    """Content signature over the recordings feeding the matrix — StartTime + channel count per rec.
    Changes iff the underlying recordings change, so a stale cache is never silently reused.

    Legacy signature, computed from the LOADED recording dicts. Retained for back-compat; the
    primary path now uses `_psd_matrix_signature_orm`, which needs no file load."""
    import hashlib
    parts = []
    for src, recs in (("td", td_list), ("psd", psd_list)):
        for r in recs or []:
            if isinstance(r, dict):
                parts.append(f"{src}:{availability._to_epoch(r.get('StartTime'))}:"
                             f"{len(r.get('ChannelNames') or [])}")
    parts.sort()
    return hashlib.sha1(("|".join(parts)).encode()).hexdigest()[:16]


def _psd_matrix_signature_orm(participant_uid):
    """Content signature over the PSD-feeding recordings, computed from the DB rows ALONE (uid +
    hashed) — NO .bdat decode. Changes iff the set of recordings (or any one's content hash)
    changes, so the assembled-matrix cache is invalidated exactly when it must be, without paying
    the ~190 s cold load just to compute the key.

    Returns (signature_hex, entries) where `entries` is the `_recording_rows_for_psd` list, so the
    caller can reuse it for the cache-aware assembly without a second ORM round-trip.
    """
    import hashlib
    from .routines import streaming_psd as _sp
    entries = _recording_rows_for_psd(participant_uid)
    parts = sorted(f"{e['source']}:{e['uid']}:{str(e['hash'] or '')[:16]}" for e in entries)
    # The Welch epoch length is a property of the matrix CONTENT (different window -> different PSDs),
    # so fold it into the signature: changing WELCH_MAX_SECONDS invalidates the cache and forces a
    # re-Welch. Without this, a window change would silently serve stale spectra from the old cache.
    parts.append(f"welch_s:{_sp.WELCH_MAX_SECONDS}")
    # Channel-canonicalization rule is part of the matrix CONTENT (it decides which channels enter
    # and under what canonical name), so a rule change must invalidate the cache and force a re-Welch.
    parts.append(f"chan_canon:{_CHANNEL_CANON_VERSION}")
    # Patient-event PSDs also feed the pool, so their recordings must invalidate the matrix cache
    # too — otherwise a newly-ingested file that adds event markers would be silently missed. Hash
    # the event recordings' (uid, hash) the same way; no decode (the PSDs live on the row metadata).
    try:
        Participant = models.Participant.find(uid=participant_uid)
        SourceFiles = models.SourceFile.find_all(owner=Participant) if Participant else []
        ev_parts = sorted(f"event:{getattr(r, 'uid', '')}:{str(getattr(r, 'hashed', '') or '')[:16]}"
                          for r in models.Recording.find_all(source__in=SourceFiles,
                                                             type=PATIENT_EVENT_TYPE)) if SourceFiles else []
        parts = parts + ev_parts
    except Exception as ex:
        _log.warning("Biomarkers: event signature component failed (%s); cache may miss new events", ex)
    return hashlib.sha1(("|".join(parts)).encode()).hexdigest()[:16], entries


def _cached_psd_matrix(participant_uid, td_list=None, psd_list=None):
    """Load the per-channel PSD matrix for this participant from disk, or build it and persist it.

    Two-level cache:
      1. Assembled-matrix npz, keyed by participant + an ORM-derived content signature
         (`_psd_matrix_signature_orm`). A hit returns the matrix with ZERO file decodes.
      2. On a matrix miss, assemble via `_assemble_psd_rows_cached`, which decodes + Welch's ONLY
         the recordings whose per-recording spectra are not already cached. So ingesting one new
         file re-Welch's just that file (not all ~330), and the cold ~190 s load disappears once the
         per-recording cache is warm.

    `td_list`/`psd_list` are accepted for call-site back-compat but no longer needed (the assembly
    is keyed off the DB). Returns the `psd_rows_to_matrix` dict (or None if no PSDs).
    """
    from .routines import streaming_psd as _sp
    sig, _entries = _psd_matrix_signature_orm(participant_uid)
    path = os.path.join(_psd_cache_dir(), f"{participant_uid}_{sig}.npz")
    if os.path.exists(path):
        try:
            z = np.load(path, allow_pickle=True)
            return {"logX": z["logX"], "t": z["t"],
                    "channel": z["channel"].astype(object), "source": z["source"].astype(object),
                    "f_set": z["f_set"]}
        except Exception as e:
            _log.warning("Biomarkers: PSD matrix cache read failed (%s); recomputing", e)

    rows, n_cached, n_computed = _assemble_psd_rows_cached(participant_uid)
    if n_computed or n_cached:
        _log.info("Biomarkers: PSD rows assembled for %s — %d from per-recording cache, %d Welch'd",
                  participant_uid, n_cached, n_computed)
    mat = _sp.psd_rows_to_matrix(rows)
    if mat is None:
        return None
    try:
        np.savez(path, logX=mat["logX"], t=mat["t"],
                 channel=np.asarray(mat["channel"], dtype=str),
                 source=np.asarray(mat["source"], dtype=str), f_set=mat["f_set"])
    except Exception as e:
        _log.warning("Biomarkers: PSD matrix cache write failed (%s)", e)
    return mat


def warm_psd_cache(participant_uid):
    """Build/refresh the per-recording PSD cache (and the assembled matrix) for a participant.

    Safe to call off the request thread or from ingestion: decodes + Welch's only the recordings not
    already cached, persists each, and writes the assembled-matrix npz. Idempotent and non-fatal.
    """
    try:
        return _cached_psd_matrix(participant_uid)
    except Exception as e:
        _log.warning("Biomarkers: warm_psd_cache failed for %s (%s)", participant_uid, e)
        return None


def _derive_chan_order(td_recordings):
    order = []
    for r in td_recordings:
        for ch in r.get("ChannelNames", []) or []:
            if ch not in order:
                order.append(ch)
    return order


def _adaptive_is_active(status):
    """True only when the device's adaptive (closed-loop) therapy is actually CONFIGURED & running.

    Medtronic stores the state as an ADBSStatusDef enum string. "NOT_CONFIGURED" (and a falsy/empty
    value) means closed loop is OFF — the programmed LFP threshold is then meaningless and must NOT be
    drawn. Anything else (e.g. ADBS_RUNNING / SUSPENDED but configured) means a threshold is in force.
    """
    if not status:
        return False
    s = str(status).split(".")[-1].upper()   # tolerate "ADBSStatusDef.ADBS_RUNNING" or bare token
    return s not in ("NOT_CONFIGURED", "OFF", "DISABLED", "NONE", "")


def _programmed_adaptive_thresholds(participant):
    """Latest PROGRAMMED adaptive-DBS detection threshold per hemisphere — ONLY when closed loop is
    active on that hemisphere. Returns {hemi: {lower, upper, measured_lower, measured_upper, status,
    date}} for hemispheres whose most-recent therapy group has adaptive therapy configured & running.

    Source: the Percept therapy history (Server.models.Therapy.ElectricalTherapy), where each group's
    AdaptiveTherapy carries sensing["Thresholds"]["LFPThresholds"]=[lower, upper] (device LFP-power
    units, the SAME units as the chronic biomarker) and adaptive["Status"] (the ADBS on/off state).
    Hemisphere is taken from the group's stimulation electrode target. Returns {} when no therapy
    metadata exists or nothing is active — the frontend then draws no programmed-threshold line.

    Defensive throughout: any failure returns {} so the biomarker report never breaks on therapy data.
    """
    if participant is None:
        return {}
    try:
        from Server.models.Therapy import ElectricalTherapy
        from Server.models import SourceFile
    except Exception:
        return {}
    try:
        source_files = list(SourceFile.find_all(owner=participant))
        if not source_files:
            return {}
        groups = list(ElectricalTherapy.find_all(therapy__source__in=source_files))
    except Exception:
        return {}

    def _hemi_of_group(g):
        # Hemisphere from the group's stimulation electrode target / channel names (LEFT/RIGHT token).
        try:
            for st in g.stimulation_settings.all():
                info = st.get_info()
                el = info.get("Electrode") or {}
                blob = " ".join(str(x) for x in (
                    el.get("Hemisphere", ""), el.get("Target", ""), el.get("CustomName", ""),
                    el.get("Name", ""), info.get("Contact", ""))).upper()
                if "LEFT" in blob:
                    return "Left"
                if "RIGHT" in blob:
                    return "Right"
        except Exception:
            pass
        return None

    def _date_of(g):
        try:
            return g.therapy.date
        except Exception:
            return None

    best = {}   # hemi -> (date, payload)
    for g in groups:
        try:
            adaptives = list(g.adaptive_settings.all())
        except Exception:
            adaptives = []
        if not adaptives:
            continue
        hemi = _hemi_of_group(g)
        gdate = _date_of(g)
        for a in adaptives:
            if a is None:
                continue
            adaptive = getattr(a, "adaptive", {}) or {}
            sensing = getattr(a, "sensing", {}) or {}
            status = adaptive.get("Status")
            if not _adaptive_is_active(status):
                continue
            thr = (sensing.get("Thresholds") or {})
            lfp = thr.get("LFPThresholds") or []
            meas = thr.get("MeasuredLFP") or []
            if not lfp or len(lfp) < 2:
                continue
            try:
                lower = float(lfp[0]); upper = float(lfp[1])
            except Exception:
                continue
            if not (lower or upper):    # [0, 0] sentinel = not really programmed
                continue
            h = hemi or "Unknown"
            payload = {
                "lower": lower, "upper": upper,
                "measured_lower": (float(meas[0]) if len(meas) > 0 and meas[0] is not None else None),
                "measured_upper": (float(meas[1]) if len(meas) > 1 and meas[1] is not None else None),
                "status": str(status).split(".")[-1],
                "date": (gdate.isoformat() if hasattr(gdate, "isoformat") else gdate),
            }
            prev = best.get(h)
            # Keep the most recent active program per hemisphere.
            if prev is None or (gdate is not None and prev[0] is not None and gdate >= prev[0]) or prev[0] is None:
                best[h] = (gdate, payload)
    return {h: p for h, (d, p) in best.items()}


def _recorded_powers(powerdomain_list, region_map=None):
    """Which band-power channels were actually recorded — the '<contact> Power' columns of the
    BrainSense Power-Domain recordings, formatted numerically (e.g. 'L 0⁻3⁺') with region from
    device metadata when available, plus the sensing-band CENTER FREQUENCY when the device stored
    it. Each entry: {raw, label, region, center_hz}. The card displays 'L 0⁻3⁺ (GPi) @ 22.5 Hz'
    so the clinician sees which BAND was sensed, not just which contact pair. Frequency extraction
    lives in analytics.power_center_freqs (Django-free, unit-tested).
    """
    center_hz = analytics.power_center_freqs(powerdomain_list)
    seen = {}
    for r in powerdomain_list or []:
        for nm in r.get("ChannelNames", []) or []:
            s = str(nm)
            if "POWER" in s.upper():
                contact = s.rsplit(" ", 1)[0] if " " in s else s   # strip the trailing " Power"
                if contact not in seen:
                    fmt = analytics.format_channel(contact, region=(region_map or {}).get(contact))
                    chz = center_hz.get(contact)
                    # Flag a sensing band at/above the biomarker frequency cap so the card can warn
                    # that it falls outside the validated theta/alpha/beta/low-gamma range.
                    above = bool(chz is not None and chz >= pipeline.MAX_BIOMARKER_FREQ_HZ)
                    seen[contact] = {"raw": contact, "label": fmt["short"], "region": fmt["region"],
                                     "center_hz": chz, "above_cap": above}
    return list(seen.values())


def _region_map(participant, chan_order):
    """Map each raw sensing-channel name (e.g. 'ZERO_THREE_LEFT') to a brain region inferred from
    the PARTICIPANT'S DEVICE METADATA (Electrode.custom_name / target), not a static map. The
    hemisphere is taken from the channel name and matched to the electrode whose name/target names
    that hemisphere. Returns {} when no electrode metadata is available (callers fall back)."""
    if participant is None:
        return {}
    try:
        from Server.models.Device import Electrode
    except Exception:
        return {}
    hemi_region = {}
    for e in Electrode.objects.filter(owner=participant):
        reg = (getattr(e, "custom_name", "") or getattr(e, "target", "") or "").strip()
        if not reg:
            continue
        ru = reg.upper()
        hemi = "LEFT" if ("LEFT" in ru or ru.startswith("L ")) else (
               "RIGHT" if ("RIGHT" in ru or ru.startswith("R ")) else "")
        if hemi:
            hemi_region.setdefault(hemi, reg)
    out = {}
    for raw in chan_order or []:
        ru = str(raw).upper()
        h = "LEFT" if "LEFT" in ru else ("RIGHT" if "RIGHT" in ru else "")
        if h and h in hemi_region:
            out[raw] = hemi_region[h]
    return out


def _pt_config_dir():
    """Directory holding per-patient `<name>_config.json` field maps. Defaults to the
    live-mounted `<BRAVO>/pt_config`; override with the BRAVO_PT_CONFIG_DIR env var."""
    env = os.environ.get("BRAVO_PT_CONFIG_DIR")
    if env:
        return env
    # this file: <BRAVO>/modules/Biomarkers/bravo_service.py -> BRAVO base is three dirs up.
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "pt_config")


def _safe_config_name(value):
    """Reduce a request-supplied config selector to a bare filename component that cannot escape
    the pt_config directory. `PtConfig`/`RedcapRecordId`/participant name are authenticated-user
    input that gets interpolated into a filesystem path; without this, values like
    `../../../etc/foo`, an absolute path, or one containing a path separator would let a caller
    read arbitrary JSON files on the server (e.g. a REDCap config holding the API token). We keep
    only the basename and reject anything that still contains a separator, is empty, or is a
    dot-entry — so only files that live DIRECTLY inside the pt_config dir are reachable."""
    if value is None:
        return None
    name = os.path.basename(str(value).strip())
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        return None
    return name


def _load_pt_config(participant, request_data):
    """Locate and parse a participant's pt_config (the same file the library-mode pipeline reads
    for channel order; it also carries the REDCap field map). Resolution order:
    explicit `PtConfig` in the request, then `<dir>/<RedcapRecordId>_config.json`, then
    `<dir>/<participant name>_config.json`. Returns the dict, or None if no file is found.

    All candidates are confined to `cfg_dir`: the request-supplied selectors are reduced to a bare
    basename (see `_safe_config_name`) and every resolved path is verified to sit inside `cfg_dir`
    before it is opened, so no `PtConfig`/`RedcapRecordId` value can traverse out of that dir."""
    cfg_dir = _pt_config_dir()
    cfg_root = os.path.realpath(cfg_dir)
    candidates = []
    explicit = _safe_config_name(request_data.get("PtConfig"))
    if explicit:
        candidates += [os.path.join(cfg_dir, explicit),
                       os.path.join(cfg_dir, f"{explicit}_config.json")]
    rid = _safe_config_name(request_data.get("RedcapRecordId"))
    if rid:
        candidates.append(os.path.join(cfg_dir, f"{rid}_config.json"))
    if participant is not None and getattr(participant, "name", ""):
        pname = _safe_config_name(participant.name)
        if pname:
            candidates.append(os.path.join(cfg_dir, f"{pname}_config.json"))
    for path in candidates:
        if not path:
            continue
        # Defence in depth: even after basename-sanitising, confirm the real path stays under
        # cfg_root before touching the filesystem (guards against symlinks in the dir, too).
        real = os.path.realpath(path)
        if real != cfg_root and not real.startswith(cfg_root + os.sep):
            continue
        if os.path.isfile(real):
            with open(real, "r") as fp:
                return json.load(fp)
    return None


def _resolve_field_map(request_data, participant):
    """A REDCap field map for `process_redcap`: an inline `RedcapFieldMap` in the request takes
    precedence, else the participant's pt_config file. None if neither is available."""
    return request_data.get("RedcapFieldMap") or _load_pt_config(participant, request_data)


def _load_pros(request_data, participant=None):
    """Resolve the tidy PRO DataFrame (canonical columns: `date_time_s1_daily`, `nrs`, `vas`, ...),
    NORMALIZED to a canonical UTC time column at this single ingestion choke-point.

    REDCap delivers survey timestamps as the participant's naive California-local wall-clock string.
    Every downstream consumer that re-parses that raw string risks forgetting the DST-aware
    local->UTC correction (that is exactly how `availability.pain_series` drifted 7-8 h while
    `_pro_match_arrays` stayed correct — FIXHANDOUT_pro_timezone_mismatch). To make a naive local
    string un-representable downstream, we compute the correct UTC instant ONCE here, in a derived
    `_pro_time_utc` column, and every reader (`_pro_match_arrays`, `availability.pain_series`,
    `pain_scores_for_participant`, ...) consumes that column instead of re-localizing.
    """
    df = _load_pros_raw(request_data, participant)
    return _normalize_pro_times(df)


def _load_pros_raw(request_data, participant=None):
    """Resolve the tidy PRO DataFrame from its source (no time normalization — see `_load_pros`).

    Priority:
      1. `ProcessedPRO` in the request body (a list of already-tidy dicts).
      2. A REDCap pull (REDCAP_API_URL / REDCAP_API_TOKEN set). If a field map is available
         (inline `RedcapFieldMap` or the participant's pt_config), the raw export is mapped to
         tidy columns via `redcap_client.process_redcap`; otherwise the raw rows are returned
         filtered only by `RedcapRecordId` (legacy fallback).
    Returns None when no PRO source is configured.
    """
    if request_data.get("ProcessedPRO"):
        return pd.DataFrame(request_data["ProcessedPRO"])
    if os.environ.get("REDCAP_API_URL") and os.environ.get("REDCAP_API_TOKEN"):
        df = redcap_client.pull_redcap()  # token via env vars
        field_map = _resolve_field_map(request_data, participant)
        if field_map:
            return redcap_client.process_redcap(df, field_map)
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


def _demo_run(source, request_data=None):
    request_data = request_data or {}
    recordings, chronic, pro, chan_order = _demo_inputs()
    td = recordings if source in ("timedomain", "both") else []
    ch = chronic if source in ("powerdomain", "both") else None
    pro, label_metric, kmeans_features = _resolve_biomarker_metric(request_data, pro)
    train_days, step_days, sliding, window_months, window_step_months = _window_params(request_data)
    demo_train_days = train_days if train_days is not None else 3   # demo spans ~14 days
    demo_test_days = step_days if step_days is not None else 2
    run = pipeline.run_biomarker(td, pro, chan_order, source=source, chronic=ch,
                                 train_days=demo_train_days, gap_days=1, test_days=demo_test_days,
                                 sliding=sliding,
                                 label_metric=label_metric, kmeans_features=kmeans_features)
    out = _serialize_run(run, _compute_analytics(run, ch, pro, label_metric=label_metric,
                                                 kmeans_features=kmeans_features,
                                                 train_days=train_days, step_days=step_days,
                                                 sliding=sliding), label_metric=label_metric)
    out["message"] = "DEMO DATA — synthetic timeline (no real Percept/REDCap loaded)."
    out["label_metric"] = label_metric
    out["available_metrics"] = BIOMARKER_METRICS
    out["sliding_window"] = sliding
    out["window_months"] = window_months
    out["window_step_months"] = window_step_months
    # Demo: a synthetic ACTIVE closed-loop program on the Left hemisphere, so the programmed-threshold
    # overlay is visible in demo mode. The Right hemisphere has no active program (line not drawn).
    out["programmed_thresholds"] = {
        "Left": {"lower": 1900.0, "upper": 2600.0, "measured_lower": 1850.0,
                 "measured_upper": 2650.0, "status": "ADBS_RUNNING", "date": None},
    }
    return out


def _run_parallel(tasks):
    """Run a dict of {key: zero-arg callable} concurrently (threads) and return {key: result}.
    Each task is guarded independently so one failing analytic stores {'error': ...} under its key
    instead of sinking the rest. numpy/pandas/sklearn release the GIL on the heavy ops, so these
    run truly in parallel."""
    if not tasks:
        return {}
    out = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), _loader_threads())) as pool:
        futures = {key: pool.submit(fn) for key, fn in tasks.items()}
        for key, fut in futures.items():
            try:
                out[key] = fut.result()
            except Exception as e:
                out[key] = {"error": str(e)}
    return out


def _compute_analytics(run, chronic, pro_df, label_metric="nrs",
                       kmeans_features=("left_leg_vas", "mpq_sum"),
                       label_strategy="tertile", low_pct=33.3333, high_pct=66.6667,
                       train_days=None, step_days=None, sliding=True, region_map=None,
                       match_tolerance_min=None, psd_matrix=None, pro_match=None,
                       aggregate="all", max_per_rating=3, refractory_min=2.0,
                       match_direction="prior"):
    """Build the notebook-style analytics (sliding-window AUC/R, ROC, LFP/Otsu histogram, KMeans
    cluster scatter, and the streaming correlation spectrum). The independent pieces run
    concurrently; each is guarded so an analytics failure never breaks the main timeline response.
    """
    result = {"timedomain": None, "powerdomain": None}

    td = run.get("timedomain")
    if td is not None:
        try:
            det = td["detail"]
            tl = td.get("timeline")
            times = [str(x) for x in tl["time"]] if (tl is not None and "time" in tl) else []
            td_window_days = train_days if train_days is not None else 30
            td_step_days = step_days if step_days is not None else 7
            # Inject times into det so corr_spectrum can build per-session scatter data.
            det["times"] = times
            # PRO<->PSD match offsets (signed minutes) carried on the td timeline, for the matched-
            # sample count readout. Present only when time-window matching ran.
            match_dt = (tl["td_match_dt_min"].to_numpy()
                        if (tl is not None and "td_match_dt_min" in tl) else None)
            # DESIGN §8b/§8c: the exploratory scan runs on the POOLED full-spectrum PSDs (TD
            # streaming + montage/survey), per main bipolar channel, each PSD matched to the nearest
            # continuous PRO within the window — NOT just the TD streaming sessions. Built from the
            # cached per-channel matrix (Welch already done) + the PRO times/values, so a compute
            # only pays for the cheap z-score + match + scan.
            pooled = None
            if psd_matrix is not None and pro_match is not None:
                try:
                    pooled = streaming_psd.build_pooled_detail_from_matrix(
                        psd_matrix, pro_match[0], pro_match[1], tolerance_min=match_tolerance_min,
                        aggregate=aggregate, max_per_rating=max_per_rating,
                        refractory_min=refractory_min, match_direction=match_direction)
                except Exception as e:
                    _log.warning("Biomarkers: pooled PSD detail failed (%s)", e)
            scan_src = pooled if pooled is not None else det
            # Matched counts come from the POOLED labels when available (all-source matches), with the
            # signed offsets the pooled matcher recorded; else fall back to the TD timeline offsets.
            if pooled is not None:
                count_task = lambda: analytics.matched_sample_counts(
                    pooled.get("labels"), strategy=label_strategy, low_pct=low_pct, high_pct=high_pct,
                    match_dt_min=None, tolerance_min=match_tolerance_min)
            else:
                count_task = lambda: analytics.matched_sample_counts(
                    det.get("labels"), strategy=label_strategy, low_pct=low_pct, high_pct=high_pct,
                    match_dt_min=match_dt, tolerance_min=match_tolerance_min)
            td_tasks = {
                "corr_spectrum": lambda: analytics.corr_spectrum(det, region_map=region_map),
                "psd_spectra": lambda: analytics.psd_spectra(det, region_map=region_map),
                "spectral_feature_importance": lambda: analytics.spectral_feature_importance(
                    scan_src, strategy=label_strategy, low_pct=low_pct, high_pct=high_pct,
                    region_map=region_map),
                "matched_sample_counts": count_task,
                "pool_meta": lambda: (pooled or {}).get("pool_meta"),
                # PSD spectrogram removed from the UI (added little over the spectrum + mean-PSD
                # panels); no longer computed to keep the response lean.
            }
            # The sliding R-vs-frequency-over-time HEATMAP is computed ONLY in sliding mode (a window
            # is selected). With no window (all data) the card shows the static R-vs-frequency
            # spectrum (corr_spectrum) with peaks highlighted instead.
            if sliding:
                td_tasks["sliding_corr_spectrum"] = lambda: analytics.td_sliding_corr_spectrum(
                    det, times, window_days=td_window_days, step_days=td_step_days, region_map=region_map)
            result["timedomain"] = _run_parallel(td_tasks)
        except Exception as e:
            result["timedomain"] = {"error": str(e)}

    if chronic is not None and pro_df is not None and len(pro_df) > 0:
        try:
            # Reuse the branch's full-resolution cv_df if available (avoids a second KMeans +
            # smoothing over 100k+ rows); fall back to building it when running analytics alone.
            pr = run.get("powerdomain")
            cv_df = pr.get("cv_df") if isinstance(pr, dict) and pr.get("cv_df") is not None else None
            if cv_df is None:
                cv_df = adapter.bravo_chronic_to_lfp_df(chronic, pro_df, label_metric=label_metric,
                                                        kmeans_features=kmeans_features,
                                                        label_strategy=label_strategy,
                                                        low_pct=low_pct, high_pct=high_pct)
            sw_kwargs = {"sliding": sliding}
            if train_days is not None:
                sw_kwargs["train_days"] = train_days
            if step_days is not None:
                sw_kwargs["step_days"] = step_days
            result["powerdomain"] = _run_parallel({
                "sliding_window": lambda: analytics.sliding_window_analytics(cv_df, **sw_kwargs),
                "roc": lambda: analytics.roc_analysis(cv_df),
                "lfp_distribution": lambda: analytics.lfp_distribution(cv_df),
                "power_pain_scatter": lambda: analytics.power_pain_scatter(cv_df, label_metric),
                "cluster_scatter": lambda: analytics.cluster_scatter(cv_df, kmeans_features=kmeans_features),
                "pain_binarization": lambda: analytics.pain_binarization(
                    cv_df, label_metric, kmeans_features=kmeans_features, pro_df=pro_df,
                    strategy=label_strategy, low_pct=low_pct, high_pct=high_pct),
            })
            # Per-channel analytics (e.g. Left LFP vs Right LFP) — pipeline.run_powerdomain_branch
            # already split the chronic input by ChannelNames[0]; here we run the same panel-driving
            # analytics on each per-channel cv_df so the card can toggle between them.
            per_ch = pr.get("per_channel") if isinstance(pr, dict) else None
            if per_ch:
                per_ch_analytics = {}
                for ch_label, ch_data in per_ch.items():
                    ch_cv = ch_data.get("cv_df")
                    if ch_cv is None or len(ch_cv) == 0:
                        continue
                    ch_tasks = {
                        "sliding_window": (lambda d=ch_cv: analytics.sliding_window_analytics(d, **sw_kwargs)),
                        "roc": (lambda d=ch_cv: analytics.roc_analysis(d)),
                        "lfp_distribution": (lambda d=ch_cv: analytics.lfp_distribution(d)),
                        "power_pain_scatter": (lambda d=ch_cv: analytics.power_pain_scatter(d, label_metric)),
                        # Per-(channel, frequency) decoding: ROC + Otsu + binarization split for EACH
                        # sensing band present in this contact's frame (chronic + streaming pooled at
                        # the same band, never across bands). Drives the frequency sub-selector and the
                        # power-domain binarization preview.
                        "frequency_decode": (lambda d=ch_cv: pipeline._decode_by_frequency(d, label_metric)),
                    }
                    per_ch_analytics[ch_label] = _run_parallel(ch_tasks)
                    # Carry the channel summary alongside so the panel can display per-channel AUC.
                    per_ch_analytics[ch_label]["summary"] = ch_data.get("summary") or {}
                result["powerdomain"]["per_channel"] = per_ch_analytics
            # Surface the chronic-trend sensing CENTER FREQUENCY per hemisphere (stamped on each
            # chronic recording at decode time from the GROUP-level config; merged onto the loaded
            # dict in _load_recordings). The chronic trend is a band-power-at-a-fixed-frequency
            # series, so the report should state which frequency -- a different value than the
            # streaming power-domain center frequencies in recorded_powers. Guarded so it never
            # breaks the response; empty when no chronic recording carried a frequency.
            if isinstance(result.get("powerdomain"), dict):
                chronic_hz = {}
                # Per-recording (start_time, hz, channel) tuples, grouped by hemisphere, so we can
                # both (a) keep the latest hz per hemisphere (legacy chronic_center_hz) and (b) emit
                # a TIME-ORDERED change timeline marking where the sensing center frequency or the
                # source channel switches during the record — the frontend draws a dashed marker at
                # each change so a mid-record reconfiguration is unmistakable.
                by_hemi = {}
                for c in (chronic or []):
                    if not isinstance(c, dict) or c.get("Source") != "chronic":
                        continue
                    hz = c.get("CenterFrequencyHz")
                    chans = c.get("ChannelNames") or []
                    chan = str(chans[0]) if chans else ""
                    hemi = chan.split(" ")[0] if chan else ""
                    if hz is not None and hemi:
                        chronic_hz[hemi] = hz
                    if hemi:
                        ts = adapter._to_datetime(c.get("StartTime"))
                        by_hemi.setdefault(hemi, []).append(
                            {"t": ts, "hz": hz, "channel": chan})
                if chronic_hz:
                    result["powerdomain"]["chronic_center_hz"] = chronic_hz
                # Build the change timeline: within each hemisphere, sort by start time and keep only
                # the points where (hz, channel) differs from the previous one (the first record is
                # always emitted as the initial config). Each entry: {hemi, t (ISO), center_hz,
                # channel, changed: ["frequency"|"channel"...]}. Empty when nothing changes.
                changes = []
                for hemi, recs in by_hemi.items():
                    recs = [r for r in recs if r["t"] is not None and pd.notna(r["t"])]
                    recs.sort(key=lambda r: r["t"])
                    prev = None
                    for r in recs:
                        if prev is None:
                            changes.append({"hemi": hemi, "t": r["t"].isoformat(),
                                            "center_hz": r["hz"], "channel": r["channel"],
                                            "changed": ["initial"]})
                        else:
                            diff = []
                            if r["hz"] != prev["hz"]:
                                diff.append("frequency")
                            if r["channel"] != prev["channel"]:
                                diff.append("channel")
                            if diff:
                                changes.append({"hemi": hemi, "t": r["t"].isoformat(),
                                                "center_hz": r["hz"], "channel": r["channel"],
                                                "changed": diff})
                        prev = r
                # Only surface the timeline if there is at least one real (post-initial) change —
                # otherwise the single static config is already conveyed by chronic_center_hz.
                if any(ch["changed"] != ["initial"] for ch in changes):
                    changes.sort(key=lambda ch: ch["t"])
                    result["powerdomain"]["sensing_config_changes"] = changes
        except Exception as e:
            result["powerdomain"] = {"error": str(e)}

    return result


_DAYS_PER_MONTH = 30.44


# Clamp ceiling for request-supplied window sizes. 10 years is comfortably longer than any
# Percept implant record, while bounding the windowing work an authenticated caller can schedule.
_MAX_WINDOW_MONTHS = 120.0


def _months_to_days(value):
    """Parse a months value (float) -> whole days (>=1), or (None, None) if absent/invalid.

    Request-supplied (`WindowMonths`/`WindowStep`), so guard the conversion: a non-finite value
    (`inf`/`nan`) would otherwise raise OverflowError/ValueError out of `int()`, and an absurdly
    large value would schedule a runaway amount of windowing work. Require months > 0 and finite,
    and clamp to `_MAX_WINDOW_MONTHS`."""
    if value is None or value == "":
        return None, None
    try:
        months = float(value)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(months) or months <= 0:
        return None, None
    months = min(months, _MAX_WINDOW_MONTHS)
    return max(1, int(round(months * _DAYS_PER_MONTH))), months


def _window_params(request_data):
    """Resolve the sliding-window controls from the request.

    Returns (train_days, step_days, sliding, window_months, window_step_months):
      * window_months / train_days: `WindowMonths` -> the sliding-window TRAINING duration
        (train_days = round(months * 30.44)). None -> callers keep their own default.
      * window_step_months / step_days: `WindowStep` -> how far the window advances each step
        (also the detector's per-window test-fold size). None -> defaults.
      * sliding: `SlidingWindow` bool (default True). False -> the power-domain detector and the
        sliding-window analytic run on ALL data at once (no temporal windows).
    """
    sliding = request_data.get("SlidingWindow", True)
    if isinstance(sliding, str):
        sliding = sliding.strip().lower() not in ("false", "0", "no", "off", "")
    sliding = bool(sliding)
    return _window_params_body(request_data, sliding)


# Pain-score binarization strategies exposed to the card. "tertile" (default) splits the metric
# into low/high tertiles and EXCLUDES the ambiguous middle (best detector target on RCS08);
# "median" keeps every day at a 50/50 split; "kmeans" is the legacy 2-cluster notebook labeler.
# See docs/binarization_recommendation_RCS08.md.
BINARIZATION_STRATEGIES = [
    {"key": "tertile", "label": "Tertile (low/high, drop middle)"},
    {"key": "percentile", "label": "Percentile (adjustable cuts)"},
    {"key": "median",  "label": "Median split"},
    {"key": "kmeans",  "label": "KMeans (legacy)"},
]
DEFAULT_BINARIZATION = "tertile"


def _label_strategy_params(request_data):
    """Resolve the binarization strategy + percentile cuts from the request.

    Returns (label_strategy, low_pct, high_pct). `LabelStrategy` selects the labeler (default
    'tertile'); `PercentileLow`/`PercentileHigh` override the tertile cuts when the strategy is
    'tertile'/'percentile'. Unknown strategies fall back to the default.
    """
    strat = (request_data.get("LabelStrategy") or DEFAULT_BINARIZATION)
    valid = {s["key"] for s in BINARIZATION_STRATEGIES} | {"percentile", "cutoff"}
    if strat not in valid:
        strat = DEFAULT_BINARIZATION
    try:
        low = float(request_data.get("PercentileLow", 33.3333))
        high = float(request_data.get("PercentileHigh", 66.6667))
    except (TypeError, ValueError):
        low, high = 33.3333, 66.6667
    if not (0 <= low < high <= 100):
        low, high = 33.3333, 66.6667
    return strat, low, high


# PRO timestamp column (REDCap daily survey clock time). Carries real clock times (not midnight),
# so it supports fine-grained PRO<->PSD time matching.
_PRO_TIME_COL = "date_time_s1_daily"

# REDCap stores survey timestamps as the participant's LOCAL wall-clock time (DST-aware: the REDCap
# server records local time, so a summer 2pm and a winter 2pm both read "14:00" in the export). The
# study is entirely in California, so the correct UTC instant is obtained by localizing each naive
# string to America/Los_Angeles and converting to UTC — this applies +7 h (PDT) or +8 h (PST)
# automatically from the tz database's real DST transition dates. The DEVICE side needs no such fix:
# per the Medtronic Percept white paper, all report data (BrainSense PSD/TD, patient events) is
# already stored in UTC (ISO-8601), and an internal consistency check confirmed the stored epochs
# match true CA wall-clock to <1 min in every DST era. So ONLY the PRO clock is corrected here.
_PRO_LOCAL_TZ = "America/Los_Angeles"


def _pro_timestamps_utc(pro_df):
    """Parse the PRO timestamp column as DST-aware California-local time and return a tz-NAIVE UTC
    pandas datetime Series (NaT where unparseable).

    The raw REDCap strings (e.g. '2025-07-20 18:17:46') are local wall-clock with no offset; parsing
    them as UTC (the historical behaviour) placed every pain score 7-8 h too early, smearing the
    PSD<->pain match. Here we localize to America/Los_Angeles (handling DST + ambiguous/nonexistent
    fall-back/spring-forward instants gracefully) then convert to UTC, dropping the tz so the result
    is directly comparable to the device's naive-UTC epochs."""
    ts_local = pd.to_datetime(pro_df[_PRO_TIME_COL], errors="coerce")
    try:
        ts_utc = (ts_local.dt.tz_localize(_PRO_LOCAL_TZ, ambiguous="NaT", nonexistent="shift_forward")
                  .dt.tz_convert("UTC").dt.tz_localize(None))
    except (TypeError, AttributeError):
        # Already tz-aware (defensive): just convert.
        ts_utc = ts_local.dt.tz_convert("UTC").dt.tz_localize(None)
    return ts_utc


# Canonical UTC PRO-time column name added by `_normalize_pro_times` at ingestion. Every reader that
# needs a PRO instant must consume THIS column (tz-naive UTC datetime64), never re-parse the raw
# local string. Centralizing the localization here is the architectural fix from
# FIXHANDOUT_pro_timezone_mismatch (so the next reader can't reintroduce the 7-8 h smear).
_PRO_TIME_UTC_COL = "_pro_time_utc"


def _normalize_pro_times(pro_df):
    """Add the canonical `_pro_time_utc` column (DST-aware CA-local -> tz-naive UTC) to `pro_df`,
    in place + returned. No-op when `pro_df` is None/empty or lacks the raw timestamp column, or
    when the canonical column is already present (idempotent — safe to call more than once)."""
    if pro_df is None or len(pro_df) == 0:
        return pro_df
    if _PRO_TIME_UTC_COL in pro_df.columns:
        return pro_df
    if _PRO_TIME_COL in pro_df.columns:
        pro_df[_PRO_TIME_UTC_COL] = _pro_timestamps_utc(pro_df)
    return pro_df


def _pro_times_utc_series(pro_df):
    """Return the tz-naive UTC PRO datetime Series, preferring the canonical normalized column when
    present (the ingestion-normalized form) and falling back to a fresh localized parse for
    DataFrames built outside `_load_pros` (e.g. standalone tests). Single read path for every
    consumer so the live and offline epochs are bit-identical."""
    if pro_df is not None and _PRO_TIME_UTC_COL in getattr(pro_df, "columns", []):
        return pd.to_datetime(pro_df[_PRO_TIME_UTC_COL], errors="coerce")
    return _pro_timestamps_utc(pro_df)


def _pro_match_arrays(pro_df, label_metric):
    """Extract (timestamps_epoch_s, metric_values) for PRO<->PSD time matching.

    Returns (np.ndarray, np.ndarray) of equal length over the rows that have BOTH a parseable
    timestamp and a finite metric value, or None if unavailable. Timestamps are DST-corrected
    California-local -> UTC (see `_pro_timestamps_utc`)."""
    if pro_df is None or len(pro_df) == 0 or label_metric not in pro_df.columns \
            or (_PRO_TIME_COL not in pro_df.columns and _PRO_TIME_UTC_COL not in pro_df.columns):
        return None
    ts = _pro_times_utc_series(pro_df)
    val = pd.to_numeric(pro_df[label_metric], errors="coerce")
    ok = ts.notna() & val.notna()
    if ok.sum() == 0:
        return None
    t_ep = (ts[ok].view("int64").to_numpy() / 1e9)
    return t_ep, val[ok].to_numpy(dtype=float)


# Default PRO<->PSD match window (minutes) when the request does not specify one. Exploratory:
# a daily PRO is matched to the nearest streaming/PSD session whose timestamp falls within this
# many minutes. The frontend slider sends `MatchToleranceMin`; None disables time-matching and
# falls back to the legacy same-calendar-day aggregation.
DEFAULT_MATCH_TOLERANCE_MIN = 60.0  # was 15. Pain reports anchor neural data on a minutes-to-hours
# timescale, not minutes — a PSD 30 min from a rating is still informative about that rating. The
# narrow 15-min window dropped 80% of the otherwise-usable pool on RCS08 (see AUDIT_stream_*).
# Coupled with the new direction='pro_first' default, this lifts PRO coverage to 290/682 (42.5%) of
# the matched discovery pool (RCS08, vas, ±60 min) — matching the offline validation pool.


def _int_param(request_data, key, *, default, lo=None, hi=None):
    """Parse an integer request param, clamped to [lo, hi]; missing/invalid -> default."""
    if key not in request_data:
        return default
    try:
        v = int(round(float(request_data.get(key))))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _float_param(request_data, key, *, default, lo=None, hi=None):
    """Parse a float request param, clamped to [lo, hi]; missing/invalid -> default."""
    if key not in request_data:
        return default
    try:
        v = float(request_data.get(key))
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _match_tolerance_param(request_data):
    """Resolve the PRO<->PSD match window (minutes) from the request.

    `MatchToleranceMin` is a positive number of minutes (the frontend tolerance slider). A missing
    key uses DEFAULT_MATCH_TOLERANCE_MIN; an explicit 0 / negative / non-numeric value disables
    time-matching (returns None -> legacy same-day aggregation).
    """
    if "MatchToleranceMin" not in request_data:
        return DEFAULT_MATCH_TOLERANCE_MIN
    try:
        v = float(request_data.get("MatchToleranceMin"))
    except (TypeError, ValueError):
        return DEFAULT_MATCH_TOLERANCE_MIN
    return v if v > 0 else None


def _window_params_body(request_data, sliding):

    train_days, window_months = _months_to_days(request_data.get("WindowMonths"))
    step_days, window_step_months = _months_to_days(request_data.get("WindowStep"))
    return train_days, step_days, sliding, window_months, window_step_months


def _build_availability(participant_uid, *, chronic_list, powerdomain_list, td_list,
                        pro_df, label_metric, region_map):
    """Assemble the data-availability-timeline payload for the new BiomarkerDataTimeline component.

    Reuses recordings already loaded for the decoder (td/chronic/powerdomain) and additionally loads
    the PSD-bearing montage/survey products (which the decoder doesn't use). Returns:
        {records, pain, stim, freq_bands, span}
    where `records` are per-channel availability records, `pain`/`stim` are the shared-axis series,
    `freq_bands` are the categorical legend bands actually present, and `span` is [min_t, max_t].
    Guarded so any failure yields an empty payload rather than breaking the main timeline response.
    """
    try:
        # td_list is a flat decoded list mixing BrainSenseTimeDomain + IndefiniteStream; the loader
        # discards the source type, so re-split by self-tag when present (else treat all as TD —
        # both are the same density-gated lane anyway). Montage/survey PSD types are loaded once and
        # passed under a single representative type key (all map to the "psd" lane).
        bs, ind = [], []
        for r in td_list or []:
            if not isinstance(r, dict):
                continue
            (ind if (r.get("Source") == "indefinite" or r.get("IndefiniteStream")) else bs).append(r)
        psd_list = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
        recs_by_type = {
            "MedtronicBrainSenseTimeDomain": bs,
            "MedtronicIndefiniteStream": ind,
            "MedtronicChronicBrainSense": list(chronic_list or []),
            "MedtronicBrainSensePowerDomain": list(powerdomain_list or []),
            "MedtronicBaselineMontages": [r for r in (psd_list or []) if isinstance(r, dict)],
        }
        records = availability.extract_availability(recs_by_type, region_map=region_map)
        # Patient-event PSDs (incl. 'Streaming') are imported into the per-channel scan pool, so they
        # must also render as PSD TICKS on their contact lanes (DESIGN: "a PSD mark at those
        # contacts"). Append one synthetic dtype="psd" record per (event, hemisphere block) on its
        # assigned bipolar channel — same record schema extract_availability emits, product tagged
        # "patient_event" so the lane draws them as ticks alongside montage/survey PSDs.
        try:
            for ev in _event_psd_index(participant_uid):
                ch = ev["channel"]
                fmt = availability.analytics.format_channel(ch, region=region_map.get(ch))
                records.append({
                    "channel": ch, "label": fmt.get("short", ch),
                    "hemisphere": availability._hemisphere(ch),
                    "dtype": "psd", "product": "patient_event",
                    "event_name": ev.get("name", "Event"),   # the marker's own name (e.g. "Streaming")
                    "t_start": float(ev["t"]), "dur_s": 30.0,
                    "meta": {"center_hz": None, "peak_hz": None, "n": None},
                })
            records.sort(key=lambda x: (x["channel"], x["t_start"]))
        except Exception as e:
            _log.warning("Biomarkers: event PSD records failed (%s)", e)
        pain = availability.pain_series(pro_df, label_metric)
        stim = availability.stim_series(chronic_list)
        # REAL inline LSB: the actual per-sample band-power series (streaming ~2 Hz + chronic
        # ~10-min) per channel, each sample tagged with its sensing center freq, so the timeline
        # draws the true trace (not a placeholder). Keyed by raw channel; frontend normalizes.
        lsb = availability.lsb_series(chronic_list, powerdomain_list, region_map=region_map)
        # Compact the per-sample LSB into render-cheap geometry (chronic line + per-session blocks)
        # so the calendar-scale timeline stays responsive while zooming; the frontend draws this.
        lsb_overview = availability.lsb_overview(lsb)
        bands = availability.present_freq_bands(records)
        # Patient-annotated events (labeled button presses) — demarcated on the timeline.
        event_list = _load_patient_events(participant_uid)
        events = availability.event_markers(event_list)
        # Montage-PSD events: NeuralActivitySnapshot montage sweeps NOT already represented by a
        # montage/survey PSD recording (de-duplicated against those StartTimes so we don't double-
        # count). Surfaced as their own marker row, separate from the labeled patient events.
        psd_times = [availability._to_epoch(r.get("StartTime")) for r in (psd_list or [])
                     if isinstance(r, dict)]
        montage_events = availability.event_markers(
            _load_montage_psd_events(participant_uid, dedup_times=psd_times))
        ts = [r["t_start"] for r in records] + pain["t"] + stim["t"] \
            + [e["t"] for e in events.get("events", [])] \
            + [e["t"] for e in montage_events.get("events", [])]
        span = [min(ts), max(ts)] if ts else []
        # Inspector samples: decimated real PSD/TD/LSB per channel for the right-hand detail panels.
        # Only for channels that actually have data (cap to keep the payload bounded); the frontend
        # selects one channel at a time client-side.
        td_all = recs_by_type["MedtronicBrainSenseTimeDomain"] + recs_by_type["MedtronicIndefiniteStream"]
        psd_all = recs_by_type["MedtronicBaselineMontages"]
        samples = {}
        chans = sorted({r["channel"] for r in records})
        for ch in chans[:12]:
            samples[ch] = availability.inspector_samples(
                ch, td_recs=td_all, psd_recs=psd_all,
                chronic_recs=chronic_list, powerdomain_recs=powerdomain_list)
        # Scan-sample index: the (t, channel, source) of every full-spectrum PSD the exploratory
        # scan pools (same `_MAIN_BIPOLAR` filter as `_assemble_psd_rows`), so the frontend can
        # replicate the nearest-PRO match + binarization LIVE as the match-window slider moves.
        psd_scan_index = _psd_sample_index(td_all, psd_all)
        # Patient-event PSDs (incl. 'Streaming') are imported into the per-channel pool, so index
        # them here too — they render as ticks on their contact lanes and the live binarization
        # preview counts them, matching the backend pool (TD + montage + Patient event).
        try:
            psd_scan_index = psd_scan_index + _event_psd_index(participant_uid)
        except Exception as e:
            _log.warning("Biomarkers: event PSD index failed (%s)", e)
        return {"records": records, "pain": pain, "stim": stim, "freq_bands": bands,
                "span": span, "samples": samples, "lsb_overview": lsb_overview,
                "events": events, "montage_events": montage_events,
                "psd_scan_index": psd_scan_index}
    except Exception as e:
        _log.warning("Biomarkers: availability payload failed: %s", e, exc_info=True)
        return {"records": [], "pain": {"metric": label_metric, "t": [], "y": []},
                "stim": {"t": [], "y": []}, "freq_bands": [], "span": [], "lsb_overview": {},
                "events": {"events": [], "n": 0},
                "montage_events": {"events": [], "n": 0}, "psd_scan_index": []}


def availability_for_participant(request_data):
    """Lightweight DATA-AVAILABILITY payload for one participant — no biomarker computation.

    This powers the always-on exploration timeline (BiomarkerDataTimeline), which must render the
    moment the page opens, BEFORE (and independent of) the expensive "Compute biomarker now" run.
    It loads only what the availability extractor needs (TD / chronic / power-domain / montage-survey
    PSD recordings + REDCap PROs + chronic stim) and reuses `_build_availability` verbatim, so the
    timeline here is byte-identical to the `availability` block returned by the full run.

    Returns {availability:{records,pain,stim,freq_bands,span,samples}, available_metrics,
             label_metric, message?}. Never raises — missing inputs yield an empty payload with a
    friendly `message` the card renders as an empty-state.
    """
    participant_uid = request_data["ParticipantId"]
    Participant = models.Participant.find(uid=participant_uid)

    # Demo participant -> synthetic availability (so the card renders before real data exists).
    if Participant is not None and getattr(Participant, "mrn", "") == DEMO_MRN:
        recordings, chronic, pro, chan_order = _demo_inputs()
        pro, label_metric, _ = _resolve_biomarker_metric(request_data, pro)
        region_map = {c: ("GPi" if "LEFT" in c.upper() else "VIM") for c in chan_order}
        for c in ([chronic] if isinstance(chronic, dict) else (chronic or [])):
            if isinstance(c, dict):
                c.setdefault("Source", "chronic")
        av = _build_availability(
            participant_uid, chronic_list=([chronic] if isinstance(chronic, dict) else (chronic or [])),
            powerdomain_list=[], td_list=recordings, pro_df=pro,
            label_metric=label_metric, region_map=region_map)
        return {"availability": av, "available_metrics": BIOMARKER_METRICS,
                "label_metric": label_metric,
                "message": "DEMO DATA — synthetic availability timeline."}

    # Real participant: load only the recordings the availability extractor consumes.
    td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES)
    chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES)
    powerdomain_list = _load_recordings(participant_uid, POWERDOMAIN_TYPES)
    for c in chronic_list:
        if isinstance(c, dict):
            c.setdefault("Source", "chronic")
    pro_df = _load_pros(request_data, Participant)
    pro_df, label_metric, _ = _resolve_biomarker_metric(request_data, pro_df)

    chan_order = _derive_chan_order(td)
    recorded_powers = _recorded_powers(powerdomain_list)
    region_map = _region_map(Participant, list(chan_order) + [p["raw"] for p in recorded_powers])

    av = _build_availability(
        participant_uid, chronic_list=chronic_list, powerdomain_list=powerdomain_list,
        td_list=td, pro_df=pro_df, label_metric=label_metric, region_map=region_map)

    # Eagerly warm the per-channel PSD matrix WHILE the user reviews the just-loaded availability
    # timeline, so the expensive transform is already on disk by the time they click "Start
    # exploratory analysis". `warm_psd_cache` consults the per-recording cache and decodes + Welch's
    # ONLY the recordings not already cached (the DB-keyed assembly needs no preloaded lists). Runs
    # in a background thread; failure is non-fatal (the compute path rebuilds if the cache is absent).
    try:
        _PSD_WARM_POOL.submit(warm_psd_cache, participant_uid)
    except Exception as e:
        _log.warning("Biomarkers: PSD cache warm dispatch failed (%s)", e)

    msg = None
    if not av.get("records"):
        msg = ("No Percept recordings decoded for this participant yet — upload sessions to populate "
               "the availability timeline.")
    return {"availability": av, "available_metrics": BIOMARKER_METRICS,
            "label_metric": label_metric, "message": msg}


def run_for_participant(request_data):
    """Assemble inputs from the DB + REDCap and run the biomarker pipeline for one participant.

    Returns a dict: {source, channels, timeline (records), summary, message}. `message` is
    non-empty (and timeline empty) when required inputs are missing -- the card renders that
    as a friendly state instead of erroring.
    """
    participant_uid = request_data["ParticipantId"]
    source = request_data.get("source", "both")
    # "powerdomain" is the canonical name for the band-power-over-time source (complementary to
    # "timedomain"). It merges the ~10-min Chronic timeline with the per-session Power-Domain band
    # power. "chronic" is accepted as a back-compat alias.
    if source == "chronic":
        source = "powerdomain"
    if source not in ("timedomain", "powerdomain", "both"):
        source = "both"

    # Demo participant -> synthetic timeline (lets the card render before real data exists).
    Participant = models.Participant.find(uid=participant_uid)
    if Participant is not None and getattr(Participant, "mrn", "") == DEMO_MRN:
        return _demo_run(source, request_data)

    td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES) if source in ("timedomain", "both") else []

    # Power domain = Chronic ~10-min LFP power + per-session Power-Domain band power, concatenated
    # (raw units) into one chronic-shaped list so they're compared apples-to-apples.
    power_list = []
    powerdomain_list = []
    chronic_list = []
    if source in ("powerdomain", "both"):
        chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES)
        powerdomain_list = _load_recordings(participant_uid, POWERDOMAIN_TYPES)
        # Tag each Chronic recording with its sensing modality so the merged-series two-source
        # batch/scale confound can be diagnosed downstream (the power-domain dicts self-tag).
        for c in chronic_list:
            if isinstance(c, dict):
                c.setdefault("Source", "chronic")
        power_list = list(chronic_list) + adapter.bravo_powerdomain_to_chronic_like(powerdomain_list)

    pro_df = _load_pros(request_data, Participant)

    missing = []
    if source in ("timedomain", "both") and not td:
        missing.append("time-domain BrainSense recordings")
    if source in ("powerdomain", "both") and not power_list:
        missing.append("power-domain recordings (Chronic BrainSense Timeline or Power Domain)")
    if pro_df is None or len(pro_df) == 0:
        missing.append("REDCap PRO data (set REDCAP_API_URL/REDCAP_API_TOKEN, or pass ProcessedPRO)")
    if missing:
        return {"source": source, "channels": [], "timeline": [], "summary": {},
                "message": "Cannot compute biomarker — missing: " + "; ".join(missing) + "."}

    chan_order = _derive_chan_order(td)
    chronic = power_list if power_list else None

    pro_df, label_metric, kmeans_features = _resolve_biomarker_metric(request_data, pro_df)
    label_strategy, low_pct, high_pct = _label_strategy_params(request_data)
    match_tol_min = _match_tolerance_param(request_data)
    # Per-rating CAP for the exploratory scan: how many PSDs one pain rating may absorb per channel,
    # and the refractory gap (min) enforced among the kept set, so a streaming BURST around one survey
    # can't double-count. `MaxPerRating` (>=1) and `RefractoryMin` (>=0) come from the frontend.
    # max_per_rating=1 reduces to the old "one per rating" behavior (the single nearest-prior PSD).
    # Match direction defaults to "prior" (forecasting: the PSD must precede the rating).
    max_per_rating = _int_param(request_data, "MaxPerRating", default=3, lo=1, hi=50)
    refractory_min = _float_param(request_data, "RefractoryMin", default=2.0, lo=0.0, hi=720.0)
    # Three-way match direction (PSD<->PRO):
    #   pro_first (default for discovery): walk PROs, claim up to max_per_rating PSDs/channel each
    #     within tolerance. Maximizes PRO coverage -- the right framing for discovery, where each
    #     PRO is the unit of independence.
    #   nearest: PSD-first symmetric, each PSD matched to the closest PRO either direction.
    #   prior:   PSD-first FORECASTING semantics (PSD must precede the PRO). Kept for the
    #     threshold-deployment view where causal prediction is the right semantics.
    _md = str(request_data.get("MatchDirection", "pro_first")).lower()
    if _md in ("pro_first", "pro-first", "pro"):
        match_direction = "pro_first"
    elif _md == "nearest":
        match_direction = "nearest"
    else:
        match_direction = "prior"
    # `aggregate` retained for back-compat with the detail builder, but the cap subsumes it: a cap of
    # 1 IS one-per-rating, so callers no longer send the old Aggregate toggle. Keep "all" here so the
    # cap (not a pre-aggregation collapse) governs sample independence, with rating-grouped AUC on top.
    aggregate = "all"
    train_days, step_days, sliding, window_months, window_step_months = _window_params(request_data)
    rb_kwargs = {"sliding": sliding, "label_strategy": label_strategy,
                 "low_pct": low_pct, "high_pct": high_pct,
                 "match_tolerance_min": match_tol_min}
    if train_days is not None:
        rb_kwargs["train_days"] = train_days
    if step_days is not None:
        rb_kwargs["test_days"] = step_days   # detector advances by (and tests on) one step

    recorded_powers = _recorded_powers(powerdomain_list)
    # Region map covers both TD sensing channels and the recorded power-domain contacts.
    region_map = _region_map(Participant, list(chan_order) + [p["raw"] for p in recorded_powers])
    for p in recorded_powers:   # backfill region now that the map is built
        p["region"] = region_map.get(p["raw"], p["region"])

    run = pipeline.run_biomarker(td, pro_df, chan_order, source=source, chronic=chronic,
                                 label_metric=label_metric, kmeans_features=kmeans_features,
                                 **rb_kwargs)

    # Pooled per-channel PSD matrix (TD streaming + montage/survey), cached on disk so the expensive
    # Welch is computed once (eagerly, when the availability timeline loaded) and reused here. The
    # DB-keyed cache decodes only recordings not already Welch'd, so no full reload is needed here.
    # The cheap match-to-PRO + scan reruns per compute with the chosen tolerance.
    psd_matrix = _cached_psd_matrix(participant_uid)
    pro_match = _pro_match_arrays(pro_df, label_metric)

    out = _serialize_run(run, _compute_analytics(run, chronic, pro_df, label_metric=label_metric,
                                                 kmeans_features=kmeans_features,
                                                 label_strategy=label_strategy,
                                                 low_pct=low_pct, high_pct=high_pct,
                                                 train_days=train_days, step_days=step_days,
                                                 sliding=sliding, region_map=region_map,
                                                 match_tolerance_min=match_tol_min,
                                                 psd_matrix=psd_matrix, pro_match=pro_match,
                                                 aggregate=aggregate, max_per_rating=max_per_rating,
                                                 refractory_min=refractory_min,
                                                 match_direction=match_direction),
                         label_metric=label_metric)
    out["label_metric"] = label_metric
    out["aggregate"] = aggregate
    out["max_per_rating"] = max_per_rating
    out["refractory_min"] = refractory_min
    out["match_direction"] = match_direction
    out["available_metrics"] = BIOMARKER_METRICS
    out["label_strategy"] = label_strategy
    out["available_strategies"] = BINARIZATION_STRATEGIES
    out["percentile_low"] = low_pct
    out["percentile_high"] = high_pct
    out["match_tolerance_min"] = match_tol_min
    out["sliding_window"] = sliding
    out["window_months"] = window_months
    out["window_step_months"] = window_step_months
    out["recorded_powers"] = recorded_powers
    # Device's CURRENTLY-PROGRAMMED adaptive-DBS detection threshold per hemisphere — present ONLY
    # when closed-loop stimulation is active on that hemisphere (else {}). Lets the card overlay
    # "what's set on the device now" against the data-derived recommendation, in the same LFP-power
    # units. Empty dict => no closed-loop program => the frontend draws no programmed line.
    out["programmed_thresholds"] = _programmed_adaptive_thresholds(Participant)
    # Data-availability timeline payload (new BiomarkerDataTimeline component). Reuses the recordings
    # already loaded for the decoder + montage/survey PSD products; real pain (REDCap) + stim
    # (chronic per-sample mA) on the shared time axis. Guarded inside _build_availability.
    out["availability"] = _build_availability(
        participant_uid, chronic_list=chronic_list if source in ("powerdomain", "both") else [],
        powerdomain_list=powerdomain_list, td_list=td, pro_df=pro_df,
        label_metric=label_metric, region_map=region_map)
    # Honesty flag (rigor fix #5): the power-domain detector currently pools all recorded power
    # channels into ONE threshold. If they span >1 anatomical target/hemisphere (e.g. Left GPi +
    # Right medial thalamus) and/or the raw 10-min Chronic vs per-session Power-Domain scales,
    # a single pooled threshold mixes physiologically distinct signals — surface that to the user.
    distinct_regions = sorted({(p.get("region") or "").strip() for p in recorded_powers if p.get("region")})
    out["powerdomain_pooled_warning"] = (
        f"Power-domain biomarker pools {len(distinct_regions)} targets/hemispheres "
        f"({', '.join(distinct_regions)}) into one threshold at raw (un-normalized) scale; "
        f"interpret per target rather than as a single combined biomarker."
        if len(distinct_regions) > 1 else None)
    return out


# Cap the timeline returned for plotting. The power-domain merge can produce 100k+ rows (2 Hz
# Power-Domain over long sessions), which is far more than a browser can plot and would bloat the
# response to ~100 MB. The detector, summary, and analytics already ran on FULL resolution; this
# only thins what is sent for the chart.
_TIMELINE_MAX_POINTS = 6000


def _split_cv_by_contact(cv, contact_epochs):
    """Split a chronic channel's cv_df into one segment per recording contact (DISPLAY only).

    contact_epochs is [{"t0": ms, "t1": ms, "contact": str}, ...] from the dated GroupHistory
    schedule. Each cv row's timestamp is assigned to whichever epoch contains it; consecutive epochs
    of the SAME contact are merged into one display row (so a contact used in two separate windows
    still reads as one labeled row spanning both, with a gap the frontend breaks on). Returns
    [(contact, cv_segment, seg_t0_ms, seg_t1_ms), ...] in contact-first-seen order, or [] if the
    split is degenerate (no epochs, or everything lands in one contact — caller then keeps the
    single undivided row).
    """
    if cv is None or not hasattr(cv, "__len__") or len(cv) == 0 or not contact_epochs:
        return []
    try:
        # Force millisecond resolution explicitly: pandas 2.x carries variable datetime resolution
        # (s/ms/us/ns), so a bare .astype("int64") can yield seconds and silently mis-scale the epoch
        # comparison against the ms-based contact schedule. Go through numpy datetime64[ms].
        ts_ms = (pd.to_datetime(cv["timestamp"], utc=True).dt.tz_convert(None)
                 .to_numpy().astype("datetime64[ms]").astype("int64"))
    except Exception:
        return []
    eps = sorted(contact_epochs, key=lambda e: e.get("t0", 0))

    def contact_at(ms):
        cur = None
        for e in eps:
            if e.get("t0", 0) <= ms:
                cur = e.get("contact")
            else:
                break
        return cur if cur is not None else eps[0].get("contact")

    contacts = np.array([contact_at(int(m)) for m in ts_ms], dtype=object)
    uniq = [c for c in dict.fromkeys(contacts.tolist()) if c]
    if len(uniq) <= 1:
        return []   # nothing to split — caller keeps the single row
    rows = []
    for contact in uniq:
        mask = (contacts == contact)
        cv_seg = cv[mask]
        if len(cv_seg) == 0:
            continue
        seg_ms = ts_ms[mask]
        rows.append((contact, cv_seg, int(seg_ms.min()), int(seg_ms.max())))
    return rows


def _freq_epochs_in_window(freq_epochs, t0_ms, t1_ms):
    """Clip frequency epochs to [t0_ms, t1_ms] so a contact row's ribbon only shows the bands that
    were programmed while that contact was active. Returns a new clipped list (epoch-ms)."""
    if not freq_epochs:
        return []
    out = []
    for e in freq_epochs:
        a, b = e.get("t0"), e.get("t1")
        if a is None or b is None:
            continue
        lo, hi = max(a, t0_ms), min(b, t1_ms)
        if hi >= lo:
            out.append({"t0": lo, "t1": hi, "hz": e.get("hz")})
    return out


def _serialize_power_channels(run, label_metric="nrs"):
    """Per-channel power-domain timeseries for the stacked timeline — ONE entry per sensing channel,
    so the card can plot each contact on its OWN row instead of pooling them into a single trend.

    pipeline.run_powerdomain_branch already split the chronic-shaped power input by ChannelNames[0]
    into run['powerdomain']['per_channel'], each carrying its OWN full-resolution cv_df (timestamps,
    Savitzky-Golay-smoothed band power, that channel's own fitted threshold) and a summary tagging
    hemisphere / kind / threshold. We reuse those frames verbatim (no recompute) — only the display
    series is stride-thinned via adapter.decimate_for_plot.

    Pooling has no implementation meaning (you program ONE contact at a time on the Percept RC), so
    when individual bipolar contacts (kind=='contact') are present we return ONLY those — the
    per-hemisphere 'aggregate' entries are themselves a cross-contact pool and are dropped. If the
    data has no contact-level split (only hemisphere aggregates), we fall back to those so the row
    still renders.
    """
    pr = run.get("powerdomain") if isinstance(run, dict) else None
    per_ch = pr.get("per_channel") if isinstance(pr, dict) else None
    if not per_ch:
        return []
    items = []
    empties = []   # channels with no analyzable cv_df — surfaced as labeled placeholder rows (not dropped)
    for ch_label, ch_data in per_ch.items():
        summ = ch_data.get("summary") or {}
        cv = ch_data.get("cv_df")
        if cv is None or not hasattr(cv, "__len__") or len(cv) == 0:
            # A per-channel analytics failure (run_chronic_threshold raising on too-few pain-aligned
            # samples, single-class labels, etc.) leaves cv_df=None. Silently dropping the channel
            # makes a recorded contact VANISH from the timeline (it still appears in the Recorded
            # power channels table), which hides that the contact exists but couldn't be analyzed.
            # Emit a placeholder so the row renders with the reason instead of disappearing.
            empties.append((ch_label, summ))
            continue
        items.append((ch_label, summ, cv))

    # Select by SOURCE MODALITY, not just name, so we keep two physically distinct, implementable
    # series and drop only a true cross-contact pool:
    #   * powerdomain streaming CONTACTS — per-session BrainSense band power per bipolar contact.
    #   * chronic AROUND-THE-CLOCK streams — the BrainSense Timeline ~10-min LFP power log, one
    #     channel per hemisphere (a single physical sensing config sampled 24/7, NOT a pool).
    # Dropped: powerdomain hemisphere AGGREGATES (kind=='aggregate') — those ARE a cross-contact pool.
    def _is_chronic(s):
        return s.get("source_modality") == "chronic"
    def _is_stream_contact(s):
        return s.get("source_modality") == "powerdomain" and s.get("kind") == "contact"
    chosen = [it for it in items if _is_chronic(it[1]) or _is_stream_contact(it[1])]
    # Fallback for older runs without source tags: keep contacts, else everything (so a row renders).
    if not chosen:
        chosen = [it for it in items if it[1].get("kind") == "contact"] or items

    out = []
    for ch_label, summ, cv in chosen:
        thr = summ.get("best_threshold")
        thr = float(thr) if thr is not None and np.isfinite(thr) else None
        sm = summ.get("source_modality")
        contact_epochs = summ.get("contact_epochs") or []
        freq_epochs = summ.get("freq_epochs") or []

        # CONTACT SPLIT (display only). A chronic hemisphere channel is actually a sequence of
        # bipolar contacts over time (the programmed sensing contact is reprogrammed between
        # sessions). When a dated contact schedule is available, split the hemisphere's cv series
        # into one DISPLAY row per contact — each carrying only the samples recorded while that
        # contact was programmed, plus the freq epochs that fall in its windows. The analytics
        # summary (threshold/AUC) is per-hemisphere and is attached unchanged to every split row;
        # this is a presentation split, not an analytics split. Streaming/powerdomain channels and
        # chronic channels with no contact schedule fall through to a single undivided row.
        contact_rows = _split_cv_by_contact(cv, contact_epochs) if (sm == "chronic" and contact_epochs) else None

        if contact_rows:
            for contact, cv_seg, seg_t0, seg_t1 in contact_rows:
                cv_plot = adapter.decimate_for_plot(cv_seg, _TIMELINE_MAX_POINTS)
                t = pd.to_datetime(cv_plot["timestamp"]).astype(str).tolist()
                bp = [None if not np.isfinite(v) else float(v)
                      for v in cv_plot["LFP_smoothed"].to_numpy(dtype=float)]
                pain = ([None if not np.isfinite(v) else float(v)
                         for v in cv_plot[label_metric].to_numpy(dtype=float)]
                        if label_metric in cv_plot.columns else None)
                seg_fe = _freq_epochs_in_window(freq_epochs, seg_t0, seg_t1)
                out.append({
                    "channel": f"{(summ.get('hemisphere') or '?')[:1]} {contact}",
                    "hemisphere": summ.get("hemisphere"),
                    "contact": contact,
                    "kind": "contact",
                    "source_modality": sm,
                    "around_the_clock": (sm == "chronic"),
                    "center_hz": (seg_fe[-1]["hz"] if seg_fe else summ.get("center_hz")),
                    "freq_epochs": seg_fe,
                    "threshold": thr,
                    "auc": summ.get("auc_in_sample"),
                    "n_samples": int(len(cv_seg)),
                    "time": t,
                    "band_power": bp,
                    "pain": pain,
                })
            continue

        cv_plot = adapter.decimate_for_plot(cv, _TIMELINE_MAX_POINTS)
        t = pd.to_datetime(cv_plot["timestamp"]).astype(str).tolist()
        bp = [None if not np.isfinite(v) else float(v)
              for v in cv_plot["LFP_smoothed"].to_numpy(dtype=float)]
        pain = ([None if not np.isfinite(v) else float(v)
                 for v in cv_plot[label_metric].to_numpy(dtype=float)]
                if label_metric in cv_plot.columns else None)
        # Contact label for a streaming/powerdomain contact row is the trailing token of its channel
        # label ("L 0-3" -> "0-3"), so it can be folded into the matching chronic contact row below.
        row_contact = summ.get("contact")
        if row_contact is None and summ.get("kind") == "contact":
            parts = str(ch_label).split()
            row_contact = parts[-1] if parts else None
        out.append({
            "channel": str(ch_label),
            "hemisphere": summ.get("hemisphere"),
            "contact": row_contact,
            "kind": summ.get("kind"),
            "source_modality": sm,
            # "chronic" = ~10-min around-the-clock BrainSense Timeline; "powerdomain" = streaming.
            "around_the_clock": (sm == "chronic"),
            "center_hz": summ.get("center_hz"),
            # Time-segmented center-frequency epochs [{t0, t1, hz}] for the frequency ribbon under the
            # power row (the programmed sensing band changes between sessions).
            "freq_epochs": freq_epochs,
            "threshold": thr,
            "auc": summ.get("auc_in_sample"),
            "n_samples": summ.get("n_samples"),
            "time": t,
            "band_power": bp,
            "pain": pain,
        })
    # Placeholder rows for channels whose per-channel analytics produced no usable frame. These carry
    # empty_reason so the frontend renders a labeled empty row ("no analyzable pain-aligned data:
    # <reason>") instead of the contact silently vanishing from the timeline. Only emit a placeholder
    # for a channel that is NOT already present as a real row (avoid duplicate labels), and skip
    # cross-contact 'aggregate' pools (those are intentionally dropped, not a missing implementable
    # channel).
    present = {d["channel"] for d in out}
    for ch_label, summ in empties:
        if str(ch_label) in present:
            continue
        if summ.get("kind") == "aggregate":
            continue
        sm = summ.get("source_modality")
        out.append({
            "channel": str(ch_label),
            "hemisphere": summ.get("hemisphere"),
            "kind": summ.get("kind"),
            "source_modality": sm,
            "around_the_clock": (sm == "chronic"),
            "center_hz": summ.get("center_hz"),
            "freq_epochs": summ.get("freq_epochs") or [],
            "threshold": None,
            "auc": None,
            "n_samples": summ.get("n_samples"),
            "time": [],
            "band_power": [],
            "pain": None,
            "empty_reason": str(summ.get("error") or "no pain-aligned samples to fit a detector"),
        })
    # DISPLAY: chronic and streaming are kept as SEPARATE rows per contact (one chronic 24/7 row and,
    # if present, one on-demand streaming row for the same bipolar contact). They are NOT merged into a
    # single row: streaming for a contact is typically programmed at a single sensing band while the
    # chronic 24/7 log for that contact cycles through several bands over time, so overlaying them in
    # one row would hide that structure. COMBINING chronic + streaming happens only for DECODING —
    # per (channel, frequency) in the analytics path — not in this display serializer.

    # Stable order: hemisphere (Left, then Right), chronic-before-streaming within a hemisphere, then
    # channel label — so rows read top-to-bottom by target, around-the-clock log first.
    out.sort(key=lambda d: ((d.get("hemisphere") or "Z"),
                            0 if d.get("source_modality") == "chronic" else 1,
                            str(d.get("channel"))))
    return out


def _serialize_run(run, analytics_data=None, label_metric="nrs"):
    """Convert a run_biomarker result into the JSON-able dict the card consumes.

    INVARIANT: `analytics_data` (from _compute_analytics) and `run[...]['summary']` are computed
    UPSTREAM on FULL-resolution data and are passed through here verbatim. This function ONLY thins
    `run['combined']` for plotting (via adapter.decimate_for_plot) — it must never recompute a
    metric from the thinned frame. Callers MUST evaluate _compute_analytics(run, ...) BEFORE
    calling _serialize_run (Python arg-eval order guarantees this at the existing call sites).
    """
    combined = run["combined"]
    n_full = len(combined) if hasattr(combined, "__len__") else 0
    if hasattr(combined, "to_dict"):
        # PLOT-ONLY decimation on a COPY — full-resolution run['combined'] is left untouched.
        combined_plot = adapter.decimate_for_plot(combined, _TIMELINE_MAX_POINTS).copy()
        # Stringify datetime/date columns so DRF's JSON renderer can serialize them.
        for col in combined_plot.columns:
            dtype = str(combined_plot[col].dtype)
            if "datetime" in dtype or "date" in dtype or col in ("time", "date"):
                combined_plot[col] = combined_plot[col].astype(str)
        combined_plot = combined_plot.replace({np.nan: None})
        records = combined_plot.to_dict(orient="records")
        channels = list(combined_plot.columns)
    else:
        records, channels = [], []

    return {
        "source": run["source"],
        "channels": channels,
        "timeline": records,
        "timeline_points": len(records),
        "timeline_points_full": n_full,   # full-resolution row count (pre-decimation)
        # Per-channel power series — one entry per sensing contact so the card plots each on its OWN
        # row (no cross-channel pooling, which has no implementation meaning). Empty for timedomain-only
        # runs or when no per-channel split exists.
        "power_channels": _serialize_power_channels(run, label_metric=label_metric),
        "summary": {
            "timedomain": run["timedomain"]["summary"] if run.get("timedomain") else None,
            "powerdomain": run["powerdomain"]["summary"] if run.get("powerdomain") else None,
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


def _demo_stages():
    """Trial stages over the demo window (pre-op / Stage 0 / 1 / 2), colored like the
    full_trend_pain_score notebook. Real patients supply stage boundaries via pt_config."""
    midnight = 1_699_920_000.0

    def iso(day):
        return pd.Timestamp(midnight + day * 86_400, unit="s").isoformat()

    return [
        {"key": "preop", "name": "Pre-op (baseline)", "color": "#9E9E9E", "start": iso(0), "end": iso(7)},
        {"key": "stage0", "name": "Stage 0", "color": "#FA8072", "start": iso(7), "end": iso(14)},
        {"key": "stage1", "name": "Stage 1", "color": "#FFCA28", "start": iso(14), "end": iso(22)},
        {"key": "stage2", "name": "Stage 2", "color": "#26C6DA", "start": iso(22), "end": iso(31)},
    ]


def _band_decide_verdict(g, h):
    """Badge text from the glmer + stim-stability results.

    Uses the RAW glmer p (a single-click validate is one test; the band x channel q lives on the
    scan side). alpha=0.05 mirrors the scan FDR; bands that survived FDR on the scan arrive here
    with q<0.05, so this is a per-band reaffirmation in the mixed-effects frame, with the
    stim-stability flag deciding which validated label shows.
    """
    if not g.get("available"):
        return "unavailable"
    if g.get("separation"):
        return "failed (separation)"
    if g.get("singular"):
        return "failed (singular random effect)"
    p = g.get("p")
    if p is None or not isinstance(p, (int, float)) or p >= 0.05:
        return "candidate (mixed-effects n.s.)"
    if h.get("available") and h.get("stim_stable") is False:
        return "VALIDATED (stim-dependent)"
    return "VALIDATED (stim-stable)"


def _validate_band_core(request_data):
    """Shared heavy-lifting core for the per-band validation + BandCandidate emission.

    Resolves the participant, PRO metric, binarization, and PSD<->PRO match params from the
    request; builds the same pooled td_detail the scan uses (so the band feature is defined
    identically); then runs the mixed-effects logistic (glmer) and the band x stim-era LRT.

    Returns a rich intermediate dict consumed by BOTH `validate_band_for_participant` (which
    trims it to the click-panel shape) and `build_band_candidate` (which assembles the full
    §6 BandCandidate). On any failure returns {available: False, reason: ...}.
    """
    participant_uid = request_data.get("ParticipantId")
    channel = request_data.get("Channel")
    center_hz_raw = request_data.get("CenterHz")
    if not (participant_uid and channel and center_hz_raw is not None):
        return {"available": False, "reason": "ParticipantId, Channel, and CenterHz required"}
    try:
        center_hz = float(center_hz_raw)
    except (TypeError, ValueError):
        return {"available": False, "reason": "CenterHz must be numeric"}
    band_width_hz = float(request_data.get("BandWidthHz", 5.0))

    Participant = models.Participant.find(uid=participant_uid)
    if Participant is None:
        return {"available": False, "reason": f"participant {participant_uid} not found"}
    # Demo participant: no real glmer to run; tell the UI to skip the click-validate panel.
    if getattr(Participant, "mrn", "") == DEMO_MRN:
        return {"available": False, "reason": "demo participant (no real data for validation)"}

    pro_df = _load_pros(request_data, Participant)
    if pro_df is None or len(pro_df) == 0:
        return {"available": False, "reason": "no PRO data"}
    pro_df, label_metric, composite_parts = _resolve_biomarker_metric(request_data, pro_df)
    pm = _pro_match_arrays(pro_df, label_metric)
    if pm is None:
        return {"available": False, "reason": f"no matchable PRO values for metric={label_metric}"}

    # Build the same pooled td_detail the scan uses so the band feature is defined identically.
    # The assembled matrix is {logX (N,F), t (N,), channel (N,), source (N,), f_set (F,)} — there
    # is no "rows" key (that was the pre-matrix row-list representation). Gate on the actual sample
    # count instead, or this bails "no PSD samples" on a perfectly valid cached matrix.
    mat = _cached_psd_matrix(participant_uid)
    if mat is None or np.asarray(mat.get("t")).size == 0 \
            or np.asarray(mat.get("logX")).size == 0:
        return {"available": False, "reason": "no PSD samples for this participant"}
    label_strategy, low_pct, high_pct = _label_strategy_params(request_data)
    match_tol_min = _match_tolerance_param(request_data)
    max_per_rating = _int_param(request_data, "MaxPerRating", default=3, lo=1, hi=50)
    refractory_min = _float_param(request_data, "RefractoryMin", default=2.0, lo=0.0, hi=720.0)
    # Three-way match direction (PSD<->PRO):
    #   pro_first (default for discovery): walk PROs, claim up to max_per_rating PSDs/channel each
    #     within tolerance. Maximizes PRO coverage -- the right framing for discovery, where each
    #     PRO is the unit of independence.
    #   nearest: PSD-first symmetric, each PSD matched to the closest PRO either direction.
    #   prior:   PSD-first FORECASTING semantics (PSD must precede the PRO). Kept for the
    #     threshold-deployment view where causal prediction is the right semantics.
    _md = str(request_data.get("MatchDirection", "pro_first")).lower()
    if _md in ("pro_first", "pro-first", "pro"):
        match_direction = "pro_first"
    elif _md == "nearest":
        match_direction = "nearest"
    else:
        match_direction = "prior"
    from .routines import streaming_psd as sp
    pooled = sp.build_pooled_detail_from_matrix(
        mat, pm[0], pm[1],
        tolerance_min=float(match_tol_min), aggregate="all",
        max_per_rating=max_per_rating, refractory_min=refractory_min,
        match_direction=match_direction)
    if not pooled or pooled.get("psd") is None:
        return {"available": False, "reason": "matched-detail builder returned nothing"}

    # Mixed-effects logistic (definitive per-candidate inference).
    glmer = analytics.band_mixedmodel_inference(
        pooled, channel, center_hz, band_width_hz=band_width_hz,
        strategy=label_strategy, low_pct=low_pct, high_pct=high_pct)
    # Stim-state heterogeneity (band x stim-era LRT). Needs the chronic stim series.
    chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES)
    try:
        from .routines import availability as _av
        stim = _av.stim_series(chronic_list) if chronic_list else None
    except Exception:
        stim = None
    hetero = analytics.band_stim_stability(
        pooled, channel, center_hz, stim_series=stim, band_width_hz=band_width_hz,
        strategy=label_strategy, low_pct=low_pct, high_pct=high_pct)

    return {
        "available": True,
        "participant_uid": participant_uid,
        "Participant": Participant,
        "channel": channel,
        "center_hz": center_hz,
        "band_width_hz": band_width_hz,
        "label_metric": label_metric,
        "is_composite": (label_metric == COMPOSITE_METRIC),
        "composite_parts": list(composite_parts) if label_metric == COMPOSITE_METRIC else None,
        "label_strategy": label_strategy,
        "low_pct": low_pct,
        "high_pct": high_pct,
        "match_tol_min": match_tol_min,
        "max_per_rating": max_per_rating,
        "refractory_min": refractory_min,
        "match_direction": match_direction,
        "pm": pm,
        "pooled": pooled,
        "stim_series": stim,
        "glmer": glmer,
        "stim": hetero,
        "verdict": _band_decide_verdict(glmer, hetero),
    }


def validate_band_for_participant(request_data):
    """Run the click-triggered VALIDATION bundle for one band on one participant.

    Inputs (in request_data): ParticipantId, Channel (raw or short name), CenterHz, plus the same
    LabelMetric/BinarizationStrategy/LowPct/HighPct/MatchToleranceMin/MaxPerRating/RefractoryMin
    /MatchDirection knobs the scan uses (so the band feature is defined identically to what the
    scan dot represents). Optional BandWidthHz (default 5.0).

    Output: {
      'available': True,
      'channel': '...', 'center_hz': N.N, 'band_lo': N.N, 'band_hi': N.N,
      'glmer': {                      # from analytics.band_mixedmodel_inference, OR + CI + q
         'available', 'odds_ratio', 'or_lo', 'or_hi', 'p', 'q_glmer',
         'n', 'n_clusters', 'separation', 'singular', 'note', ...
      },
      'stim': {                       # from analytics.band_stim_stability
         'available', 'chisq', 'lrt_p', 'stim_stable', 'or_by_era', 'era_counts',
         'thresholds_mA', ...
      },
      'verdict': 'VALIDATED (stim-stable)' | 'VALIDATED (stim-dependent)' |
                 'candidate (FDR n.s.)' | 'failed (separation/singular)' | 'unavailable',
    }
    Degrades to {available: False, reason: ...} when the participant has no matched data or pymer4
    isn't installed; the frontend renders an empty-state caption rather than erroring.
    """
    core = _validate_band_core(request_data)
    if not core.get("available"):
        return core

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    center_hz = core["center_hz"]
    band_width_hz = core["band_width_hz"]
    return {
        "available": True,
        "channel": core["channel"],
        "center_hz": _ff(center_hz),
        "band_lo": _ff(center_hz - band_width_hz / 2.0),
        "band_hi": _ff(center_hz + band_width_hz / 2.0),
        "band_width_hz": _ff(band_width_hz),
        "label_metric": core["label_metric"],
        "glmer": core["glmer"],
        "stim": core["stim"],
        "verdict": core["verdict"],
    }


# --- Percept RC device-mapping constants (DESIGN_biomarker_pipeline_v2 §1) ----------------------
ADAPTIVE_LO_HZ = 8.0    # Percept PD-mode adaptive sensing floor
ADAPTIVE_HI_HZ = 30.0   # Percept PD-mode adaptive sensing ceiling
# Empirical LFP-Power LSB <-> µV² rule of thumb (Medtronic) and measured RCS08 ratio (§4). The
# measured constant is normalization-dependent — trusted no better than ~3×; Phase C measures it
# per overlapping session and flags divergence. Carried here only as the schema default.
LSB_RULE_OF_THUMB = 0.01


def _band_credible_ci(or_lo, or_hi, min_width=0.10):
    """v2 credible-CI rule: OR-space CI width > min_width (default 0.10).

    The 5 narrow-CI v2 candidates carry saturated-random-effect Wald CIs (width < 0.005) that are
    not trustworthy; Phase B re-validates these by cluster bootstrap. Returns (credible_bool,
    ci_width_or_None)."""
    try:
        if or_lo is None or or_hi is None:
            return None, None
        w = float(or_hi) - float(or_lo)
        if not np.isfinite(w):
            return None, None
        return bool(w > float(min_width)), float(w)
    except (TypeError, ValueError):
        return None, None


def _suggested_percept_mode(polarity, adaptive_valid):
    """Map (polarity, adaptive-validity) to a Percept RC control mode + a plain-language reason.

    Percept adaptive ramps stim UP when band power exceeds the upper threshold (§1). So:
      * positive-direction biomarker (higher power -> higher pain) maps naturally onto Dual/Single
        adaptive — more pain drives more stim, no inversion needed.
      * negative-direction biomarker (higher power -> LOWER pain) needs the inverse control law,
        which Percept implements only as 'Single Threshold Inverse' — a SENSING-ONLY mode, not
        closed-loop. So a negative biomarker is not directly deployable in adaptive mode without a
        custom feature mapping (e.g. invert/negate the feature on a custom band).
    Returns (suggested_mode|None, reason).
    """
    if not adaptive_valid:
        return None, (f"center freq outside the {ADAPTIVE_LO_HZ:.0f}–{ADAPTIVE_HI_HZ:.0f} Hz "
                      "adaptive sensing range — needs a custom sensing band before adaptive use")
    if polarity == "positive":
        return "Dual", ("positive-direction biomarker maps onto Dual/Single adaptive directly "
                        "(stim ramps up as the biomarker rises)")
    return None, ("negative-direction biomarker (higher power → lower pain) requires the inverse "
                  "control law; Percept adaptive supports inverse only as sensing-only 'Single "
                  "Threshold Inverse' — deploy via a custom/negated feature, not stock adaptive")


def build_band_candidate(request_data):
    """Assemble a serializable BandCandidate object (DESIGN_biomarker_pipeline_v2 §6) for ONE
    validated (channel, band) — the contract handed from the discovery/Biomarkers view to the
    Closed-Loop Simulation / threshold-deployment view.

    Reuses `_validate_band_core` (identical pooled-detail + glmer + stim-stability machinery as the
    click-validate panel), so the committed band is defined byte-identically to the scan dot the
    user clicked. Phase A populates identity, label provenance, device-control mapping, evidence,
    and pool-bias provenance; the threshold (`threshold_lsb`), the unit-conversion FYI
    (`conversion_check`), and the labeled time-series handoff (`timeseries_ref`) are filled by the
    deployment view in later phases and ship here as honest nulls/stubs.

    Output: {available: True, band_candidate: {...§6 schema...}, verdict, glmer, stim} OR
    {available: False, reason: ...}.
    """
    core = _validate_band_core(request_data)
    if not core.get("available"):
        return core

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None

    channel = core["channel"]
    center_hz = core["center_hz"]
    band_width_hz = core["band_width_hz"]
    glmer = core["glmer"]
    hetero = core["stim"]
    verdict = core["verdict"]

    # ---- identity ----
    fmt = analytics.format_channel(channel)
    hemisphere = fmt.get("hemisphere") or ("Left" if "LEFT" in str(channel).upper()
                                           else "Right" if "RIGHT" in str(channel).upper() else None)
    # Percept FFT-bin snap: Dual-threshold uses a 256-pt FFT on 250 Hz -> 250/256 ≈ 0.977 Hz bins;
    # Single uses 64-pt -> 250/64 ≈ 3.906 Hz bins. We snap the center to the Dual grid (the closed-
    # loop default) and note the assumption so the sim module can re-snap for Single if needed.
    fs = 250.0
    bin_dual = fs / 256.0
    snapped_center = round(center_hz / bin_dual) * bin_dual
    snapped_note = (f"snapped to Dual-threshold 256-pt FFT grid ({bin_dual:.3f} Hz bins); "
                    f"{center_hz:.2f} → {snapped_center:.2f} Hz. Re-snap to 64-pt "
                    f"({fs/64.0:.3f} Hz) for Single-threshold mode.")

    # ---- device-control mapping ----
    adaptive_valid = bool(ADAPTIVE_LO_HZ <= center_hz <= ADAPTIVE_HI_HZ)
    adaptive_reason = ("within the 8–30 Hz adaptive sensing range" if adaptive_valid
                       else (f"{center_hz:.1f} Hz outside the 8–30 Hz adaptive range — "
                             f"{'below the 8 Hz floor' if center_hz < ADAPTIVE_LO_HZ else 'above the 30 Hz ceiling'}"))
    odds = glmer.get("odds_ratio")
    coef = glmer.get("coef")
    # Polarity = sign of corr(band power, pain). OR>1 (or coef>0) => higher power tracks higher
    # pain => positive; OR<1 => negative. Fall back to coef sign when OR is unavailable.
    polarity = None
    if isinstance(odds, (int, float)) and np.isfinite(odds):
        polarity = "positive" if odds > 1.0 else "negative"
    elif isinstance(coef, (int, float)) and np.isfinite(coef):
        polarity = "positive" if coef > 0 else "negative"
    suggested_mode, mode_reason = _suggested_percept_mode(polarity, adaptive_valid)

    # ---- credible-CI flag (v2 rule) ----
    credible_ci, ci_width = _band_credible_ci(glmer.get("or_lo"), glmer.get("or_hi"))

    # ---- label provenance ----
    pm = core["pm"]
    pro_vals = np.asarray(pm[1], dtype=float) if pm is not None else np.array([])
    pl = analytics._binarize_labels(pro_vals, strategy=core["label_strategy"],
                                    low_pct=core["low_pct"], high_pct=core["high_pct"])
    n_labeled = int(np.isfinite(pl).sum())
    n_pos = int(np.nansum(pl == 1.0))
    n_neg = int(np.nansum(pl == 0.0))
    metric_label = next((m["label"] for m in BIOMARKER_METRICS
                         if m["key"] == core["label_metric"]), core["label_metric"])

    # ---- evidence: per-era ORs + stim eras from the LRT result ----
    or_by_era = hetero.get("or_by_era") if hetero.get("available") else None
    era_counts = hetero.get("era_counts") if hetero.get("available") else None
    stim_thresholds = hetero.get("thresholds_mA") if hetero.get("available") else None

    band_candidate = {
        # ---- identity (the atomic device unit) ----
        "hemisphere": hemisphere,
        "contact": fmt.get("raw") or str(channel),
        "contact_label": fmt.get("short") or fmt.get("label"),
        "center_freq_hz": _ff(center_hz),
        "bandwidth_hz": _ff(band_width_hz),
        "band_lo_hz": _ff(center_hz - band_width_hz / 2.0),
        "band_hi_hz": _ff(center_hz + band_width_hz / 2.0),
        "snapped_center_freq_hz": _ff(snapped_center),
        "snapped_bin_note": snapped_note,

        # ---- label provenance (REDCap PRO, NOT events) ----
        "label": {
            "pro_metric": core["label_metric"],
            "pro_metric_label": metric_label,
            "is_composite": core["is_composite"],
            "composite_parts": core["composite_parts"],
            "binarization": {
                "strategy": core["label_strategy"],
                "pain_cutoff": None,
                "low_pct": _ff(core["low_pct"]),
                "high_pct": _ff(core["high_pct"]),
                "daily_broadcast": False,
            },
            "join": "pro_first" if core["match_direction"] == "pro_first" else core["match_direction"],
            "match_tolerance_min": _ff(core["match_tol_min"]),
            "n_labeled_days": n_labeled,
            "n_pos_days": n_pos,
            "n_neg_days": n_neg,
        },

        # ---- device-control mapping ----
        "adaptive_valid": adaptive_valid,
        "adaptive_valid_reason": adaptive_reason,
        "polarity": polarity,
        "suggested_mode": suggested_mode,
        "suggested_mode_reason": mode_reason,

        # ---- threshold, in DEPLOYMENT-STREAM LSB (set by Phase B/C deployment view) ----
        "threshold_lsb": {"upper": None, "lower": None},
        "threshold_basis": "not yet set — assign in the threshold-deployment view (Phase B cut-point + Phase C LSB anchoring)",

        # ---- unit sanity check (FYI, confidence-rated; §4 — filled by Phase C) ----
        "conversion_check": {
            "ratio_uV2_per_lsb": None,
            "n_overlap_sessions": 0,
            "scatter_cv": None,
            "rule_of_thumb": LSB_RULE_OF_THUMB,
            "fold_off_rule": None,
            "diverges": None,
            "confidence": "low",
            "note": "empirical LSB↔µV² ratio measured in Phase C from concurrent streaming-TD + device-LSB at ~0 mA",
        },

        # ---- evidence (cluster-robust mixed-effects; stim-context aware) ----
        "evidence": {
            "discovery_method": "glmer logistic (lme4 via pymer4), pain_high ~ band_power + (1|weekly_era)",
            "odds_ratio": _ff(odds),
            "or_lo": _ff(glmer.get("or_lo")),
            "or_hi": _ff(glmer.get("or_hi")),
            "ci_width_or": _ff(ci_width),
            "credible_ci": credible_ci,
            "p_glmer": _ff(glmer.get("p")),
            "z_glmer": _ff(glmer.get("z")),
            "coef": _ff(coef),
            "n_matched_samples": glmer.get("n"),
            "n_clusters": glmer.get("n_clusters"),
            "separation": glmer.get("separation"),
            "singular": glmer.get("singular"),
            "stim_stable": (hetero.get("stim_stable") if hetero.get("available") else None),
            "stim_lrt_p": _ff(hetero.get("lrt_p")) if hetero.get("available") else None,
            "or_by_era": or_by_era,
            "per_stream_n": {"matched_total": glmer.get("n")},
            "mixed_model_effect": _ff(coef),
            "stim_off_only": False,
        },

        # ---- confounds / honesty about the pool (§5) ----
        "provenance": {
            "selection_biased": True,
            "selection_note": ("candidate pool is intuition-narrowed and non-uniform by construction "
                               "(e.g. right 0-3 ~26 Hz over-sampled by design); cross-candidate "
                               "ranking must treat the pool as biased"),
            "stim_context_eras": era_counts,        # OFF/LOW/HIGH sample counts (full montage/freq/mA reconstruction is a §5 TODO)
            "stim_era_thresholds_mA": stim_thresholds,
            "stim_era_heterogeneity_tested": bool(hetero.get("available")),
            "match_direction": core["match_direction"],
        },

        # ---- handoff to the Closed-Loop Simulation module (set when the labeled series is exported) ----
        "timeseries_ref": None,

        # ---- top-level verdict echo (for the sign-off card) ----
        "verdict": verdict,
        "schema_version": "bandcandidate_v1",
    }

    return {
        "available": True,
        "band_candidate": band_candidate,
        "verdict": verdict,
        "glmer": glmer,
        "stim": hetero,
    }


def band_deployment_roc(request_data):
    """Rating-clustered deployment ROC + cut-point table for ONE committed band (Phase B).

    Reuses `_validate_band_core` so the band feature + pooled detail are byte-identical to the
    committed BandCandidate, then runs `analytics.deployment_roc` on that detail. The match
    direction defaults to **prior/forecasting** here (the controller can only act on PSDs that
    PRECEDE a rating), unlike the discovery scan's `pro_first` — the frontend exposes a toggle to
    switch back to `pro_first` for the full-pool AUC. Pass `MatchDirection` to override.

    Inputs: same as /emitBandCandidate, plus optional NBoot (bootstrap replicates, default 500).
    Output: {available, channel, center_hz, band_lo, band_hi, label_metric, match_direction,
             roc:{auc, auc_lo, auc_hi, fpr[], tpr[], thr[], operating_point, ...}} or
            {available: False, reason: ...}.
    """
    # Deployment default = causal forecasting unless the caller is explicit.
    rd = dict(request_data)
    if not rd.get("MatchDirection"):
        rd["MatchDirection"] = "prior"
    core = _validate_band_core(rd)
    if not core.get("available"):
        return core

    n_boot = _int_param(rd, "NBoot", default=500, lo=50, hi=5000)
    roc = analytics.deployment_roc(
        core["pooled"], core["channel"], core["center_hz"],
        band_width_hz=core["band_width_hz"], strategy=core["label_strategy"],
        low_pct=core["low_pct"], high_pct=core["high_pct"], n_boot=n_boot)

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    center_hz = core["center_hz"]; band_width_hz = core["band_width_hz"]
    return {
        "available": roc.get("available", False),
        "reason": roc.get("reason"),
        "channel": core["channel"],
        "center_hz": _ff(center_hz),
        "band_lo": _ff(center_hz - band_width_hz / 2.0),
        "band_hi": _ff(center_hz + band_width_hz / 2.0),
        "band_width_hz": _ff(band_width_hz),
        "label_metric": core["label_metric"],
        "match_direction": core["match_direction"],
        "roc": roc,
    }


def _sensing_hz_for_pd(pd_rec, contact):
    """Resolve a PowerDomain recording's sensing center frequency for a contact, from its
    Descriptor.Therapy snapshot (the TD streaming recording carries no Therapy)."""
    d = pd_rec.get("Descriptor")
    th = d.get("Therapy") if isinstance(d, dict) else None
    if not isinstance(th, dict):
        return None
    side = "Left" if "LEFT" in str(contact).upper() else "Right"
    try:
        return analytics.sensing_center_hz(th.get(side))
    except Exception:
        return None


def band_lsb_and_power(request_data):
    """Phase C: anchor a Phase-B cut-point to deployable device units and report power / sample-size.

    Three products, in order of how much weight the clinician should put on them:
      1) **Percentile-anchored Timeline LSB threshold** (the deployable number): take where the
         cut-point sits as a percentile of the matched-sample band-power feature, then read the
         device's OWN Timeline LSB at that same percentile, restricted to samples the device sensed
         in this band. This sidesteps BOTH the z-scoring of the feature AND the fragile µV²↔LSB
         conversion — it is in the LSB units the clinician programs. Returns unavailable (honestly)
         when the device never sensed this band (e.g. off the 8–30 Hz adaptive range).
      2) **Empirical µV²/LSB ratio** (FYI cross-check): measured from concurrent on-demand TD + LSB
         at ~0 mA, confidence-rated. NOT used for the deployable threshold.
      3) **Power / sample-size**: AUC power on the count of independent ratings + the ratings needed
         for 80% power — the 'is there enough pain-rating data yet?' readout.

    Inputs: same as /queryDeploymentROC, plus Cutpoint (the oriented log-power threshold chosen in
    Phase B) and MatchDirection (defaults to prior). Output: {available, threshold_lsb{...},
    lsb_ratio{...}, power{...}, percentile, ...}.
    """
    rd = dict(request_data)
    if not rd.get("MatchDirection"):
        rd["MatchDirection"] = "prior"
    core = _validate_band_core(rd)
    if not core.get("available"):
        return core

    pooled = core["pooled"]; channel = core["channel"]
    center_hz = core["center_hz"]; band_width_hz = core["band_width_hz"]

    # ---- 1) percentile of the cut-point in the matched-sample feature distribution ----
    cutpoint = _float_param(rd, "Cutpoint", default=None)
    feat = analytics._band_feature_from_detail(pooled, channel, center_hz, band_width_hz)
    percentile = None; n_feat = 0
    if feat is not None:
        bp = np.asarray(feat[0], dtype=float)
        bp = bp[np.isfinite(bp)]
        n_feat = int(bp.size)
        if cutpoint is not None and n_feat > 0:
            percentile = float((bp <= float(cutpoint)).mean() * 100.0)

    # ---- device Timeline LSB for this channel, restricted to this band's sensing ----
    chronic_list = _load_recordings(core["participant_uid"], CHRONIC_TYPES)
    pd_list = _load_recordings(core["participant_uid"], POWERDOMAIN_TYPES)
    from modules.Biomarkers.routines import availability as _av
    lsb = _av.lsb_series(chronic_list, pd_list)
    half = band_width_hz / 2.0
    threshold_lsb = {"available": False, "reason": "not computed"}
    band_lsb_vals = None
    series = lsb.get(channel) or lsb.get(analytics.format_channel(channel)["short"])
    if series is not None:
        y = np.asarray(series.get("y"), dtype=float)
        hz = np.asarray(series.get("center_hz"), dtype=float)
        bmask = np.isfinite(y) & np.isfinite(hz) & (hz >= center_hz - half) & (hz < center_hz + half)
        band_lsb_vals = y[bmask]
    if band_lsb_vals is not None and band_lsb_vals.size >= 20 and percentile is not None:
        thr_lsb = float(np.percentile(band_lsb_vals, percentile))
        threshold_lsb = {
            "available": True, "method": "percentile-anchored on device Timeline LSB",
            "upper_lsb": round(thr_lsb, 1), "lower_lsb": None,
            "percentile": round(percentile, 1),
            "n_timeline_samples": int(band_lsb_vals.size),
            "device_lsb_p10": round(float(np.percentile(band_lsb_vals, 10)), 1),
            "device_lsb_median": round(float(np.median(band_lsb_vals)), 1),
            "device_lsb_p90": round(float(np.percentile(band_lsb_vals, 90)), 1),
            "note": ("Threshold to PROGRAM, in device LSB. Anchored by matching the cut-point's "
                     "percentile in the matched-sample distribution to the device's own Timeline LSB "
                     "at the same percentile (band-restricted) — no µV²↔LSB conversion needed."),
        }
    else:
        n_band = int(band_lsb_vals.size) if band_lsb_vals is not None else 0
        threshold_lsb = {
            "available": False,
            "reason": (f"device sensed this band only {n_band} times"
                       if percentile is not None
                       else "no Phase-B cut-point supplied (Cutpoint param)"),
            "n_timeline_samples": n_band,
            "hint": ("This band is likely off the device's programmed sensing range (the Percept "
                     "adaptive band is 8–30 Hz); a percentile anchor needs Timeline LSB recorded in "
                     "this band."),
        }

    # ---- 2) empirical µV²/LSB ratio (FYI) ----
    td_list = _load_recordings(core["participant_uid"], ["MedtronicBrainSenseTimeDomain"])
    lsb_ratio = analytics.empirical_lsb_ratio(td_list, pd_list, _sensing_hz_for_pd)

    # ---- 3) power / sample-size on the clustered effective n ----
    n_boot = _int_param(rd, "NBoot", default=300, lo=50, hi=5000)
    roc = analytics.deployment_roc(pooled, channel, center_hz, band_width_hz=band_width_hz,
                                   strategy=core["label_strategy"], low_pct=core["low_pct"],
                                   high_pct=core["high_pct"], n_boot=n_boot)
    power = {"available": False, "reason": "ROC unavailable"}
    if roc.get("available"):
        # independent-rating effective n at the observed prevalence.
        n_clu = int(roc.get("n_clusters") or 0)
        prev = roc.get("prevalence")
        if n_clu >= 4 and prev is not None and 0 < prev < 1:
            n_pos_eff = int(round(n_clu * prev)); n_neg_eff = n_clu - n_pos_eff
            power = analytics.auc_power(roc["auc"], n_pos_eff, n_neg_eff)

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    return {
        "available": True,
        "channel": channel, "center_hz": _ff(center_hz), "band_width_hz": _ff(band_width_hz),
        "label_metric": core["label_metric"], "match_direction": core["match_direction"],
        "cutpoint_feature": _ff(cutpoint), "percentile": _ff(percentile), "n_matched_samples": n_feat,
        "threshold_lsb": threshold_lsb,
        "lsb_ratio": lsb_ratio,
        "power": power,
        "auc": _ff(roc.get("auc")) if roc.get("available") else None,
        "auc_lo": _ff(roc.get("auc_lo")) if roc.get("available") else None,
        "auc_hi": _ff(roc.get("auc_hi")) if roc.get("available") else None,
    }


def band_deployment_roc_by_era(request_data):
    """Phase D: refit the deployment ROC + cut-point WITHIN each stim era (OFF/LOW/HIGH).

    Reuses _validate_band_core (same band feature + pooled detail + chronic stim trajectory as the
    committed candidate), then runs analytics.deployment_roc_by_era. Defaults MatchDirection to
    causal 'prior' like the pooled deployment ROC. Inputs: same as /queryDeploymentROC.
    """
    rd = dict(request_data)
    if not rd.get("MatchDirection"):
        rd["MatchDirection"] = "prior"
    core = _validate_band_core(rd)
    if not core.get("available"):
        return core
    n_boot = _int_param(rd, "NBoot", default=300, lo=50, hi=5000)
    by_era = analytics.deployment_roc_by_era(
        core["pooled"], core["channel"], core["center_hz"], core.get("stim_series"),
        band_width_hz=core["band_width_hz"], strategy=core["label_strategy"],
        low_pct=core["low_pct"], high_pct=core["high_pct"], n_boot=n_boot)

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    center_hz = core["center_hz"]; band_width_hz = core["band_width_hz"]
    return {
        "available": by_era.get("available", False),
        "reason": by_era.get("reason"),
        "channel": core["channel"], "center_hz": _ff(center_hz),
        "band_width_hz": _ff(band_width_hz),
        "label_metric": core["label_metric"], "match_direction": core["match_direction"],
        "by_era": by_era,
    }


def deployment_summary(request_data):
    """Phase E: one authoritative Deploy-to-Percept review payload for a committed band.

    Calls _validate_band_core ONCE and runs every deployment analytic on the shared pooled detail
    (the ROC, the per-era refit, the LSB anchor, the power readout) so the sign-off card is a single
    fetch rather than re-deriving from four panel states. Assembles an explicit GATES list (the
    hard yes/no checks a clinician signs against) and a CAVEATS list (soft warnings). Inputs: same
    as /queryLsbPower (Channel, CenterHz, Cutpoint, ...).

    Output: {available, identity{...}, device_control{...}, evidence{...}, threshold{...},
             power{...}, portability{...}, gates[...], caveats[...], match_direction, verdict}.
    """
    rd = dict(request_data)
    if not rd.get("MatchDirection"):
        rd["MatchDirection"] = "prior"
    core = _validate_band_core(rd)
    if not core.get("available"):
        return core

    pooled = core["pooled"]; channel = core["channel"]
    center_hz = core["center_hz"]; band_width_hz = core["band_width_hz"]
    g = core.get("glmer") or {}; st = core.get("stim") or {}
    verdict = core.get("verdict")
    n_boot = _int_param(rd, "NBoot", default=300, lo=50, hi=5000)

    # ROC + per-era refit on the shared detail.
    roc = analytics.deployment_roc(pooled, channel, center_hz, band_width_hz=band_width_hz,
                                   strategy=core["label_strategy"], low_pct=core["low_pct"],
                                   high_pct=core["high_pct"], n_boot=n_boot)
    by_era = analytics.deployment_roc_by_era(
        pooled, channel, center_hz, core.get("stim_series"), band_width_hz=band_width_hz,
        strategy=core["label_strategy"], low_pct=core["low_pct"], high_pct=core["high_pct"],
        n_boot=n_boot)

    # Cut-point -> percentile -> device-LSB threshold (Phase C logic, inline on the shared detail).
    cutpoint = _float_param(rd, "Cutpoint", default=None)
    feat = analytics._band_feature_from_detail(pooled, channel, center_hz, band_width_hz)
    percentile = None
    if feat is not None and cutpoint is not None:
        bp = np.asarray(feat[0], dtype=float); bp = bp[np.isfinite(bp)]
        if bp.size:
            percentile = float((bp <= float(cutpoint)).mean() * 100.0)
    chronic_list = _load_recordings(core["participant_uid"], CHRONIC_TYPES)
    pd_list = _load_recordings(core["participant_uid"], POWERDOMAIN_TYPES)
    from modules.Biomarkers.routines import availability as _av
    lsb = _av.lsb_series(chronic_list, pd_list)
    half = band_width_hz / 2.0
    series = lsb.get(channel) or lsb.get(analytics.format_channel(channel)["short"])
    thr_lsb = None; n_tl = 0
    if series is not None:
        y = np.asarray(series.get("y"), dtype=float); hz = np.asarray(series.get("center_hz"), dtype=float)
        bm = np.isfinite(y) & np.isfinite(hz) & (hz >= center_hz - half) & (hz < center_hz + half)
        vals = y[bm]; n_tl = int(vals.size)
        if vals.size >= 20 and percentile is not None:
            thr_lsb = round(float(np.percentile(vals, percentile)), 1)

    # Power on the clustered effective n.
    power = {"available": False, "reason": "ROC unavailable"}
    if roc.get("available"):
        n_clu = int(roc.get("n_clusters") or 0); prev = roc.get("prevalence")
        if n_clu >= 4 and prev is not None and 0 < prev < 1:
            n_pos = int(round(n_clu * prev)); power = analytics.auc_power(roc["auc"], n_pos, n_clu - n_pos)

    # Device-control mapping (same as build_band_candidate).
    or_val = g.get("odds_ratio"); coef = g.get("coef")
    if isinstance(or_val, (int, float)) and np.isfinite(or_val) and or_val > 0:
        polarity = "positive" if or_val > 1 else "negative"
    elif isinstance(coef, (int, float)) and np.isfinite(coef):
        polarity = "positive" if coef > 0 else "negative"
    else:
        polarity = "unknown"
    snapped = round(center_hz / (250.0 / 256.0)) * (250.0 / 256.0)   # Dual 256-pt FFT grid
    adaptive_valid = bool(ADAPTIVE_LO_HZ <= center_hz <= ADAPTIVE_HI_HZ)
    suggested_mode, mode_reason = _suggested_percept_mode(polarity, adaptive_valid)
    credible, _ci_width = _band_credible_ci(g.get("or_lo"), g.get("or_hi"))

    # ---- GATES (hard checks the clinician signs against) ----
    gates = []
    gates.append({"key": "validated", "label": "Band validated (mixed-effects)",
                  "pass": bool(verdict and "VALIDATED" in str(verdict)), "detail": verdict})
    gates.append({"key": "adaptive_band", "label": "In Percept adaptive range (8–30 Hz)",
                  "pass": adaptive_valid,
                  "detail": f"center {round(center_hz,1)} Hz (band {round(center_hz-half,1)}–{round(center_hz+half,1)} Hz)"})
    gates.append({"key": "deployable_threshold", "label": "Deployable LSB threshold available",
                  "pass": thr_lsb is not None,
                  "detail": (f"power ≥ {thr_lsb} LSB" if thr_lsb is not None
                             else f"device sensed this band {n_tl} times")})
    gates.append({"key": "credible_ci", "label": "Credible effect-size CI",
                  "pass": bool(credible), "detail": f"OR CI [{g.get('or_lo')}, {g.get('or_hi')}]"})
    # Stim-stability gate: consistent with the verdict badge. The verdict labels a band
    # "stim-dependent" only when the LRT EXPLICITLY finds instability; an unavailable LRT (e.g. a
    # singular fit on a tiny OFF stratum under the prior match-direction) is treated as not-dependent.
    # The gate mirrors that, but the detail is transparent about whether the LRT actually ran.
    if st.get("available"):
        stim_pass = bool(st.get("stim_stable"))
        stim_detail = (f"band×era LRT p={st.get('lrt_p')} ({'stable' if stim_pass else 'stim-dependent'})")
    else:
        # LRT did not converge on this path; fall back to the verdict's determination.
        stim_pass = bool(verdict and "stim-stable" in str(verdict))
        stim_detail = ("LRT did not converge on this match-direction; "
                       + ("treated as stim-stable per the band's validated verdict"
                          if stim_pass else "stim-stability unconfirmed"))
    gates.append({"key": "stim_stable", "label": "Stim-stable (band×era LRT n.s.)",
                  "pass": stim_pass, "detail": stim_detail})
    gates.append({"key": "powered", "label": "Adequately powered (≥80%)",
                  "pass": bool(power.get("available") and not power.get("more_data_needed")),
                  "detail": (f"power {round(power.get('power_current',0)*100)}%, "
                             f"need {power.get('n_ratings_needed')} ratings"
                             if power.get("available") else "n/a")})

    # ---- CAVEATS (soft warnings) ----
    caveats = []
    if not adaptive_valid:
        caveats.append("Band is OUTSIDE the 8–30 Hz Percept adaptive sensing range — not deployable "
                       "as an adaptive control band without re-anchoring to an in-range band.")
    if polarity == "negative":
        caveats.append("Negative polarity (band power DOWN with pain): Dual/Single-threshold adaptive "
                       "would ramp the wrong way. Requires the inverse control law or a re-signed feature.")
    if by_era.get("available"):
        if (by_era.get("auc_spread") or 0) > 0.10 or (by_era.get("cutpoint_spread") or 0) > 0.5:
            caveats.append(f"Per-era fragility: AUC swings {round(by_era.get('auc_spread') or 0,2)} / "
                           f"cut-point swings {round(by_era.get('cutpoint_spread') or 0,2)} across "
                           "OFF/LOW/HIGH — the threshold may not hold once stim changes.")
    if power.get("available") and power.get("more_data_needed"):
        caveats.append(f"Underpowered: ~{(power.get('n_ratings_needed',0) - power.get('n_ratings_current',0))} "
                       "more independent pain ratings needed for 80% power.")
    caveats.append("Selection bias: this band was chosen from a sweep on the same data; the OR/AUC are "
                   "optimistic. Out-of-sample / prospective confirmation is the honest test.")

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    return {
        "available": True,
        "match_direction": core["match_direction"], "verdict": verdict,
        "identity": {
            "participant": core.get("Participant"), "hemisphere": analytics.format_channel(channel)["hemisphere"],
            "contact": channel, "contact_label": analytics.format_channel(channel)["label"],
            "region": analytics.format_channel(channel)["region"],
            "center_freq_hz": _ff(center_hz), "bandwidth_hz": _ff(band_width_hz),
            "band_lo_hz": _ff(center_hz - half), "band_hi_hz": _ff(center_hz + half),
            "snapped_center_freq_hz": _ff(snapped),
            "pro_metric": core["label_metric"], "binarization": core["label_strategy"],
        },
        "device_control": {
            "adaptive_valid": adaptive_valid, "polarity": polarity,
            "suggested_mode": suggested_mode, "suggested_mode_reason": mode_reason,
        },
        "threshold": {
            "available": thr_lsb is not None, "upper_lsb": thr_lsb,
            "percentile": round(percentile, 1) if percentile is not None else None,
            "cutpoint_feature": _ff(cutpoint), "n_timeline_samples": n_tl,
            "method": "percentile-anchored on device Timeline LSB",
        },
        "evidence": {
            "auc": _ff(roc.get("auc")), "auc_lo": _ff(roc.get("auc_lo")), "auc_hi": _ff(roc.get("auc_hi")),
            "odds_ratio": _ff(or_val), "or_ci_low": _ff(g.get("or_lo")),
            "or_ci_high": _ff(g.get("or_hi")), "credible_ci": bool(credible),
            "p_glmer": _ff(g.get("p")), "n_matched_samples": g.get("n"),
            "n_clusters": roc.get("n_clusters") if roc.get("available") else None,
            "operating_point": roc.get("operating_point") if roc.get("available") else None,
        },
        "power": power,
        "portability": ({"available": True, "auc_spread": _ff(by_era.get("auc_spread")),
                         "cutpoint_spread": _ff(by_era.get("cutpoint_spread")),
                         "n_eras_estimable": by_era.get("n_eras_estimable"),
                         "era_counts": by_era.get("era_counts"),
                         "eras": {k: {"auc": _ff(v.get("auc")) if v.get("available") else None,
                                      "available": v.get("available", False)}
                                  for k, v in (by_era.get("eras") or {}).items()}}
                        if by_era.get("available") else {"available": False, "reason": by_era.get("reason")}),
        "gates": gates, "caveats": caveats,
        "n_gates_passed": int(sum(1 for x in gates if x["pass"])), "n_gates": len(gates),
    }


def pain_scores_for_participant(request_data):
    """Return the participant's pain-score reports over time, per metric, JSON-able for the card.

    Demo participant -> synthetic; otherwise REDCap PROs (env vars) or `ProcessedPRO` in the body.
    """
    from .routines.analytics import _f

    participant_uid = request_data["ParticipantId"]
    Participant = models.Participant.find(uid=participant_uid)
    demo = Participant is not None and getattr(Participant, "mrn", "") == DEMO_MRN

    pro = _demo_pain_scores() if demo else _load_pros(request_data, Participant)
    if pro is None or len(pro) == 0:
        return {"metrics": [], "n_reports": 0,
                "message": "No pain-score reports found. Set REDCAP_API_URL / REDCAP_API_TOKEN "
                           "(or pass ProcessedPRO) to load this patient's REDCap surveys."}

    if _PRO_TIME_COL not in pro.columns and _PRO_TIME_UTC_COL not in pro.columns:
        return {"metrics": [], "n_reports": 0,
                "message": "PRO data has no 'date_time_s1_daily' timestamp column."}

    # Canonical UTC instant (prefers the ingestion-normalized _pro_time_utc column; DST-aware
    # CA-local -> UTC), so the pain trace shares the device's UTC time axis.
    t = _pro_times_utc_series(pro)
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

    stages = _demo_stages() if demo else (request_data.get("Stages") or [])

    return {"metrics": metrics, "n_reports": int(t.notna().sum()), "correlation": correlation,
            "stages": stages,
            "message": "DEMO DATA — synthetic pain-score reports." if demo else ""}
