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
import re
import json
import math
import pickle
import logging
import threading
import time as _time
import contextlib as _contextlib
import contextvars as _contextvars
import functools as _functools
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from Server import models
from modules import Database
from modules.HelperFunctions import json_compliant_handler

from . import pipeline
from . import adapter
from .routines import redcap_client
from .routines import analytics
from .routines import availability
from .routines import band_results_tables
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
PATIENT_EVENT_TYPE = "PatientControllerEvent"
AVAILABILITY_PSD_TYPES = ["MedtronicBrainSenseSurvey", "MedtronicBaselineMontages",
                          "MedtronicStimulationMontages"]

# ── PSD-source taxonomy — single source of truth (verified on RCS08 JSONs, 2026-06-27) ────────────
# Several products carry a frequency-domain PSD. They differ along TWO axes that the pipeline must not
# conflate:
#
#   (1) UNITS / POOLING identity — what scale the spectrum is in, hence which rows z-score together and
#       which conversion applies. Patient-triggered events carry the device's ONBOARD FFT
#       (Frequency/FFTBinData on the ORM row metadata). CS-3 (paired montage fit, RCS08 2026-06-27)
#       established this is LINEAR µV magnitude, the SAME unit as the montage device-PSD (LFPMagnitude),
#       but BASELINE-SUBTRACTED so sub-noise-floor bins read slightly negative (~1/3 of bins, down to
#       ~−1 quantum); LFPMagnitude clamps those ≥0. Paired FFTBinData↔LFPMagnitude slope≈1, ratio≈1.04
#       (≈ identity after clamping negatives to 0). The onboard-FFT band power sits ~6 dB (×4.79) above
#       a Welch-of-time-domain band power on the same channel — a constant absorbed by the within-
#       (channel, pooling_source) z-score in psd_rows_to_matrix for the SCAN, and applied explicitly as
#       the bridge constant for LSB (see CS-3 below). Montage/survey PSDs are the same LFPMagnitude unit.
#
#   (2) LSB ROUTE — decided by whether the product ALSO carries time-domain (TD). LSB lives only in the
#       PROGRAMMED products (on-demand BrainSenseLfp streaming + Timeline). A product WITH TD gets LSB
#       from the direct, validated TD→LSB transform (analytics.td_to_lsb, k=352.62). A PSD-ONLY product
#       (patient-triggered snapshot events) has no TD, so it gets LSB only via the PSD→LSB BRIDGE (CS-3):
#       the montage TD↔PSD law composed with the TD→LSB transform. Montage/survey products are the
#       bridge's CALIBRATION SOURCE — never a consumer of it.
#
# POOLING-source tags (used by the biomarker matrix; events share onboard-FFT units, so they pool as one):
EVENT_PSD_SOURCE = "Patient event"          # any PatientControllerEvent PSD (labeled OR Streaming)
MONTAGE_PSD_SOURCE = "Montage PSD"          # NeuralActivitySnapshot / montage-survey device PSD
#
# DISPLAY categories (timeline lane + legend; distinct identities the user must be able to tell apart):
DISPLAY_PATIENT_EVENT   = "Patient event"        # labeled patient-triggered events (Medication, Pain, …)
DISPLAY_STREAMING_EVENT = "Streaming event PSD"  # auto patient-triggered LFP snapshots fired around surveys
DISPLAY_MONTAGE_SNAPSHOT = "Montage PSD"         # NeuralActivitySnapshot automatic ~20 s montage sweep
#
# The name the device gives auto-fired streaming snapshots (a PatientControllerEvent, NOT a manual label):
STREAMING_EVENT_NAME = "streaming"
#
# Declarative taxonomy: every PSD-bearing source, its origin and routing. Consumed by the event loaders,
# the timeline assembler, and the CS-3 bridge so all paths agree on one classification.
PSD_SOURCE_TAXONOMY = {
    "patient_event": {
        "db_type": PATIENT_EVENT_TYPE, "name_is_streaming": False,
        "origin": "Patient-triggered LFP snapshot, manually labeled button press",
        "units": "onboard FFTBinData (linear µV magnitude, baseline-subtracted; ~6 dB above Welch)",
        "has_td": False, "has_psd": True, "has_lsb": False,
        "lsb_route": "psd_bridge",                 # PSD-only → CS-3 bridge
        "pooling_source": EVENT_PSD_SOURCE, "display": DISPLAY_PATIENT_EVENT,
    },
    "streaming_event": {
        "db_type": PATIENT_EVENT_TYPE, "name_is_streaming": True,
        "origin": "Auto LFP frequency snapshot fired around surveys (name='Streaming')",
        "units": "onboard FFTBinData (linear µV magnitude, baseline-subtracted; ~6 dB above Welch)",
        "has_td": False, "has_psd": True, "has_lsb": False,
        "lsb_route": "psd_bridge",                 # PSD-only → CS-3 bridge
        "pooling_source": EVENT_PSD_SOURCE, "display": DISPLAY_STREAMING_EVENT,
    },
    "montage_snapshot": {
        "db_type": "NeuralActivitySnapshot", "name_is_streaming": None,
        "origin": "Automatic ~20 s montage sweep (full-band PSD over reference montage)",
        "units": "device LFPMagnitude (linear µV) + carries 250 Hz TD",
        "has_td": True, "has_psd": True, "has_lsb": False,
        "lsb_route": "td_transform",               # has TD → direct k=352.62; bridge CALIBRATION source
        "pooling_source": MONTAGE_PSD_SOURCE, "display": DISPLAY_MONTAGE_SNAPSHOT,
    },
}


def _event_display_category(event_name):
    """Map a PatientControllerEvent's name to its DISPLAY category. Auto 'Streaming' snapshots get
    their own category (DISPLAY_STREAMING_EVENT); every other (manually labeled) press is a patient
    event. Both share the EVENT_PSD_SOURCE pooling tag (same onboard-FFT units)."""
    nm = (event_name or "").strip().lower()
    return DISPLAY_STREAMING_EVENT if nm == STREAMING_EVENT_NAME else DISPLAY_PATIENT_EVENT

# ---- Active-sensing config resolver for patient-event PSD channel assignment -----------------
# Each PatientControllerEvent PSD block carries the active sensing contact pair in SenseID when
# the device firmware wrote it. On RCS08, 84% of blocks (2,635/3,119) have SenseID absent.
# The OLD approach guessed RIGHT→ZERO_THREE / LEFT→ONE_THREE statically, dumping ~86% of all
# event PSDs onto R0-3. The NEW approach resolves the active pair from the nearest decoded
# BrainSenseTimeDomain or BrainSensePowerDomain record on the same hemisphere at press time.
# ALL-PAIR sweeps (IndefiniteStream, montage/survey) are EXCLUDED from the resolver; blocks
# that remain unresolvable return None (skipped) — no static guess is ever applied.

_EVENT_SENSE_CONTACT = {
    "ZERO_AND_THREE": "ZERO_THREE", "ONE_AND_THREE": "ONE_THREE",
    "ZERO_AND_TWO": "ZERO_TWO", "ONE_AND_TWO": "ONE_TWO",
}
# How far in seconds to search for a sensing config record relative to an event. 90 days covers
# any realistic inter-session gap on a monthly outpatient programme.
_SENSING_WINDOW_S = 90 * 86400


def _build_sensing_config_index(decoded_recs):
    """Build a per-hemisphere sorted list of (epoch_s, channel) entries from single-channel
    sensing records, for use by the active-sensing event-channel resolver.

    Only records whose ChannelNames map to EXACTLY ONE main-bipolar channel per hemisphere are
    included.  This automatically excludes IndefiniteStream and montage sweeps (which sense every
    contact simultaneously) without needing an explicit type filter.

    Returns:
        {"RIGHT": [(epoch_s, canonical_ch), ...], "LEFT": [...]} sorted ascending by epoch_s.
    """
    idx = {"RIGHT": [], "LEFT": []}
    for r in (decoded_recs or []):
        if not isinstance(r, dict):
            continue
        t = availability._to_epoch(r.get("StartTime"))
        if t is None:
            continue
        names = r.get("ChannelNames") or []
        by_hemi = {}          # hemi -> list of main-bipolar channels in this record
        for nm in names:
            s = str(nm)
            # Strip power-domain suffixes: "ZERO_THREE_LEFT Power" → "ZERO_THREE_LEFT"
            for suf in (" Power", " LFP", " Amplitude", " Stimulation"):
                if s.upper().endswith(suf.upper()):
                    s = s[: -len(suf)].strip()
                    break
            canon = availability._canon_channel(s)
            if canon not in _MAIN_BIPOLAR:
                continue
            h = "RIGHT" if "RIGHT" in canon else "LEFT"
            by_hemi.setdefault(h, []).append(canon)
        # Include only hemispheres with exactly one configured channel (= active sensing pair).
        for h, chans in by_hemi.items():
            if len(chans) == 1:
                idx[h].append((t, chans[0]))
    for hemi in idx:
        idx[hemi].sort()
    return idx


def _build_sensing_config_index_from_rows(psd_rows):
    """Build a per-hemisphere sensing-config index from already-computed Welch PSD rows.

    Companion to _build_sensing_config_index for call sites (e.g. _assemble_psd_rows_cached) where
    decoded recording dicts are not available but the flat {channel, source, t} rows already are.
    Accepts only rows whose source is \"TD streaming\" (single-channel sessions), mirroring the
    decoded-dict version's ChannelNames==1 guard; montage/IndefiniteStream rows carry all six
    contacts and are excluded.

    Returns {"RIGHT": [(epoch_s, ch), ...], "LEFT": [...]} sorted ascending.
    """
    # Group TD-streaming rows by (t_rounded, hemi) and keep only single-channel groups.
    from collections import defaultdict
    by_t_hemi = defaultdict(list)   # (t_rounded, hemi) -> [ch, ...]
    for row in (psd_rows or []):
        if row.get("source") != "TD streaming":
            continue
        ch = row.get("channel")
        t = row.get("t")
        if ch is None or t is None:
            continue
        h = "RIGHT" if "RIGHT" in str(ch).upper() else ("LEFT" if "LEFT" in str(ch).upper() else None)
        if h is None:
            continue
        key = (round(float(t)), h)
        if ch not in by_t_hemi[key]:
            by_t_hemi[key].append(ch)
    idx = {"RIGHT": [], "LEFT": []}
    for (t_r, h), chans in by_t_hemi.items():
        if len(chans) == 1 and chans[0] in _MAIN_BIPOLAR:
            idx[h].append((float(t_r), chans[0]))
    for hemi in idx:
        idx[hemi].sort()
    return idx


def _resolve_event_channel(hemi_key, sense_id, t_event, sensing_index=None):
    """Resolve a patient-event PSD block's canonical bipolar channel.

    Resolution priority:
      1. SenseID when present — the device's own authoritative contact-pair identifier.
      2. Sensing-config index: most-recent record with t_config ≤ t_event within
         _SENSING_WINDOW_S (90 days). Falls back to nearest-after when no prior record exists
         in the window (covers events fired before the first decoded session).
      3. None — the block is skipped; no static hemisphere guess is ever applied.

    Args:
        hemi_key      : e.g. 'HemisphereLocationDef.Right'
        sense_id      : e.g. 'SensingElectrodeConfigDef.ZERO_AND_THREE' or None/''
        t_event       : epoch seconds of the event
        sensing_index : output of _build_sensing_config_index, or None (SenseID-only mode)
    """
    import bisect
    hemi = ("Right" if str(hemi_key).endswith("Right")
            else ("Left" if str(hemi_key).endswith("Left") else None))
    if hemi is None:
        return None
    # Priority 1: explicit SenseID (authoritative)
    if sense_id:
        tail = str(sense_id).split(".")[-1]
        contact = _EVENT_SENSE_CONTACT.get(tail)
        if contact:
            name = f"{contact}_{hemi.upper()}"
            return name if name in _MAIN_BIPOLAR else None
    # Priority 2: active-sensing index lookup
    if sensing_index is not None and t_event is not None:
        entries = sensing_index.get(hemi.upper(), [])   # [(t, ch), ...] sorted asc
        if entries:
            ts = [e[0] for e in entries]
            # Most-recent prior config (t_config ≤ t_event)
            pos = bisect.bisect_right(ts, t_event) - 1
            if pos >= 0 and (t_event - ts[pos]) <= _SENSING_WINDOW_S:
                return entries[pos][1]
            # No prior in window → try nearest-after (event fired before first session)
            pos2 = bisect.bisect_left(ts, t_event)
            if pos2 < len(entries) and (ts[pos2] - t_event) <= _SENSING_WINDOW_S:
                return entries[pos2][1]
    # Priority 3: unresolvable — skip, do not guess
    return None

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
            # Stamp the AUTHORITATIVE DB recording type onto every decoded dict. The .bdat payload
            # carries no type/Source field (BrainSenseTimeDomain and IndefiniteStream decode to the
            # IDENTICAL key set), so the only reliable BrainSense-vs-Indefinite discriminator is the
            # Recording.type from the query — without this, indefinite streams are indistinguishable
            # from BrainSense streaming downstream and silently mislabel.
            rtype = getattr(rec, "type", None)
            if rtype is not None:
                for d in (data if isinstance(data, list) else [data]):
                    if isinstance(d, dict):
                        d.setdefault("RecordingType", rtype)
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

    These are PatientControllerEvent rows — both manually LABELED button presses ("Higher Pain",
    "Tingly/Burning", "Feeling Good", "Medication", ...) AND the auto-fired "Streaming" LFP snapshots
    the patient triggers around each survey. Unlike the .bdat recordings, the event's time and
    per-hemisphere PSD live on the ROW's `metadata` (one subdict per hemisphere, each with `DateTime`,
    `Frequency`, `FFTBinData`), so we read them off the ORM directly — no file decode.

    Streaming events are NO LONGER dropped (2026-06-27, PI): on RCS08 they are the dominant
    PSD-bearing modality (~2477 vs ~221 labeled) and the primary closed-loop signal, so they are
    surfaced as their OWN display category (`category=DISPLAY_STREAMING_EVENT`) rather than being
    discarded or folded into the montage-PSD markers. Each returned event carries a `category` tag
    (DISPLAY_STREAMING_EVENT for Streaming, DISPLAY_PATIENT_EVENT for labeled presses) so the timeline
    can render them as distinct rows/glyphs. The authoritative timestamp is the per-hemisphere
    `DateTime` (ISO-Z); we fall back to the row's `date` if absent.

    Returns [{"name": str, "category": str, "t": epoch_s, "psds": [(freq_list, power_list), ...]}, ...].
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
        if not name:
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
        # Streaming events are surfaced (no longer dropped) under their own display category; labeled
        # presses keep their annotation as the patient-event category. Both share onboard-FFT units.
        out.append({"name": name, "category": _event_display_category(name),
                    "t": float(t), "psds": psds})
    return out


def _event_block_channel(hemi_key, sense_id):
    """SenseID-only shim — kept for backward compat.  Prefer _resolve_event_channel with a
    sensing_index (built by _build_sensing_config_index) for accurate per-block channel lookup
    when SenseID is absent (the common case on RCS08: 84% of blocks lack SenseID)."""
    return _resolve_event_channel(hemi_key, sense_id, t_event=None, sensing_index=None)


def _event_psd_rows(participant_uid, sensing_index=None):
    """Harvest EVERY PatientControllerEvent PSD (incl. the auto 'Streaming' markers) as poolable
    PSD rows for the per-channel biomarker scan.

    Unlike `_load_patient_events` (timeline display, which pools hemispheres without channel
    identity and tags each event a display `category`), this assigns each per-hemisphere FFT block
    to its canonical bipolar channel so the spectra join the same per-channel pool as TD/Montage.
    Channel resolution priority (see `_resolve_event_channel`):
      1. SenseID when present — the device's authoritative contact-pair identifier.
      2. Active-sensing config index (sensing_index from _build_sensing_config_index): the
         most-recent single-channel sensing config for this hemisphere at event time.
      3. Unresolvable → block skipped; no static hemisphere guess is ever applied.
    The onboard-FFT vs Welch scale offset is absorbed by the within-(channel, source) z-score, since
    every row here is tagged `source=EVENT_PSD_SOURCE`. No .bdat decode — the spectra live on the
    ORM row `metadata`, one subdict per hemisphere with `DateTime` / `Frequency` / `FFTBinData`.

    Args:
        sensing_index : optional output of _build_sensing_config_index(decoded_td_recs).
                        Pass it to activate per-timestamp channel resolution for no-SenseID blocks.
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
            freq = hb.get("Frequency")
            power = hb.get("FFTBinData")
            if not (isinstance(freq, (list, tuple)) and isinstance(power, (list, tuple))
                    and len(freq) == len(power) and len(freq) > 0):
                continue
            # Parse event timestamp first so the resolver can do the temporal lookup.
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
            ch = _resolve_event_channel(hemi_key, hb.get("SenseID"),
                                        t_event=float(t), sensing_index=sensing_index)
            if ch is None:
                continue
            rows.append({"channel": ch, "source": EVENT_PSD_SOURCE, "t": float(t),
                         "freq": np.asarray(freq, dtype=float),
                         "power": np.asarray(power, dtype=float)})
    return rows


def _event_psd_index(participant_uid, sensing_index=None):
    """Lightweight {t, channel, source} index of the patient-event PSDs (incl. 'Streaming'), one
    entry per (event, hemisphere block) assigned to its canonical bipolar channel — the SAME set
    `_event_psd_rows` pools into the matrix, minus the freq/power arrays. Feeds `psd_scan_index` so
    the imported event PSDs render as tick marks on their contact lanes and the live binarization
    preview counts them, mirroring the backend pool (TD + montage + Patient event).

    Args:
        sensing_index : optional output of _build_sensing_config_index; enables per-timestamp
                        channel resolution for no-SenseID blocks (the 84% majority on RCS08).
    """
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
            ch = _resolve_event_channel(hemi_key, hb.get("SenseID"),
                                        t_event=float(t), sensing_index=sensing_index)
            if ch is None:
                continue
            out.append({"t": float(t), "channel": ch, "source": EVENT_PSD_SOURCE,
                        "name": ev_name})
    return out

def _event_psd_lsb_blocks(participant_uid, sensing_hz_by_channel=None, sensing_index=None):
    """Build CS-3 PSD->LSB BRIDGE input blocks from the PSD-only patient-triggered snapshot events.

    These events (PatientControllerEvent metadata: per-hemisphere Frequency/FFTBinData) carry a device
    onboard-FFT spectrum but NO time domain, so they are the bridge's sole consumer (montage/survey
    products carry TD -> direct transform; never routed here). Reuses `_event_psd_rows` for the
    channel-assigned {channel, t, freq, power} spectra, then attaches a `center_hz`:
      - the contact's configured sensing center (sensing_hz_by_channel) when known — so the modeled
        event LSB lands on the SAME band the device would deploy; else
      - the event spectrum's own in-[LO,DEPLOYABLE_HI] peak frequency (device acts in that band).
    availability.lsb_series applies analytics.device_psd_to_lsb (k~=73.63) and keeps the result inside
    [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI]; blocks whose center can't be resolved are dropped there.

    Args:
        sensing_index : optional output of _build_sensing_config_index; passed through to
                        _event_psd_rows so no-SenseID blocks get accurate channel assignment.
    Returns a list of {channel, t, freq, power, center_hz}.
    """
    sensing_hz_by_channel = sensing_hz_by_channel or {}
    lo = float(analytics.LSB_VALIDATED_HZ_LO)
    hi = float(analytics.LSB_DEPLOYABLE_HZ_HI)
    blocks = []
    for row in _event_psd_rows(participant_uid, sensing_index=sensing_index):
        ch = row.get("channel")
        freq = row.get("freq"); power = row.get("power")
        if ch is None or freq is None or power is None:
            continue
        center = sensing_hz_by_channel.get(ch) or sensing_hz_by_channel.get(str(ch))
        if center is None:
            # No configured sensing center: fall back to a device-blessed band — the peak of THIS
            # event's clamped magnitude, SEARCHED ONLY within [lo, hi] so the fallback can never pick a
            # high-frequency noise peak the bridge couldn't calibrate. (This is the peak-SEARCH bound;
            # availability.lsb_series applies the SAME [lo, hi] as the FINAL gate on whatever center
            # arrives — sensing-config centers bypass this search but still face that gate, so both the
            # configured and the fallback path are bounded identically. The constants are the single
            # source: analytics.LSB_VALIDATED_HZ_LO / LSB_DEPLOYABLE_HZ_HI.)
            f = np.asarray(freq, dtype=float)
            m = analytics.clamp_device_psd(power)
            band = (f >= lo) & (f <= hi) & np.isfinite(m)
            if band.any():
                center = float(f[band][int(np.argmax(m[band]))])
        if center is None or not np.isfinite(center) or float(center) <= 0:
            continue
        blocks.append({"channel": ch, "t": row.get("t"),
                       "freq": freq, "power": power, "center_hz": float(center)})
    return blocks


# Strip a SensingElectrodeConfigDef.* / HemisphereLocationDef.* enum to its bare token.
_ENUM_TAIL_RE = re.compile(r"\.([A-Za-z_]+)$")


def _montage_psd_lsb_blocks(participant_uid, montage_recordings=None):
    """Build PSD->LSB bridge input blocks from MONTAGE/SURVEY device-PSD snapshots.

    Each MedtronicBrainSenseSurvey / Montage recording carries, in
    `Descriptor.MedtronicPSD`, a per-contact device-onboard PSD spectrum
    (`LFPFrequency` [Hz] + `LFPMagnitude` [linear µV], 100 points), alongside its
    raw 250 Hz TD. The TD already feeds the transform route (k=352.62); this surfaces
    the device PSD as a SEPARATE psd_bridge window so a montage contributes LSB even
    when its TD tile fails the cache quality gate (too short / saturated / >max_missing).

    Calibration: LFPMagnitude is the SAME linear-µV onboard-FFT unit as the
    patient-event FFTBinData, so the SAME bridge constant LSB_PER_DEVICE_PSD≈73.63
    applies (paired same-recording validation: device-PSD LSB / TD-transform LSB
    median 0.993, IQR [0.966,1.020] in 8–30 Hz). Each MedtronicPSD entry is mapped to
    its canonical channel via SensingElectrodes (+ Hemisphere); ring pairs go through
    _EVENT_SENSE_CONTACT, segmented contacts fall to _canon_channel. The whole-recording
    StartTime is the window timestamp (the survey sweep is a near-instant snapshot).

    Returns a list of {channel, t, freq, power, source} — the schema
    raw_lsb_spectrum_cache consumes for its PSD family. `source` is tagged
    MONTAGE_PSD_SOURCE so the cache/hover can distinguish montage from patient-event PSD.
    """
    if montage_recordings is None:
        montage_recordings = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
    blocks = []
    for r in (montage_recordings or []):
        if not isinstance(r, dict):
            continue
        mp = (r.get("Descriptor") or {}).get("MedtronicPSD")
        if not isinstance(mp, list):
            continue
        t0 = availability._to_epoch(r.get("StartTime"))
        if t0 is None:
            continue
        for e in mp:
            if not isinstance(e, dict):
                continue
            freq = e.get("LFPFrequency")
            power = e.get("LFPMagnitude")
            if freq is None or power is None:
                continue
            # Canonical channel from the device sensing config + hemisphere.
            se = str(e.get("SensingElectrodes") or "")
            hemi = str(e.get("Hemisphere") or "")
            mse = _ENUM_TAIL_RE.search(se)
            pair = mse.group(1) if mse else ""
            pair = _EVENT_SENSE_CONTACT.get(pair, pair)   # ring-pair → canonical; segmented unchanged
            h = "LEFT" if "Left" in hemi else ("RIGHT" if "Right" in hemi else "")
            if not pair or not h:
                continue
            ch = _canon_channel(f"{pair}_{h}")
            if not ch:
                continue
            blocks.append({"channel": ch, "t": float(t0),
                           "freq": freq, "power": power, "source": MONTAGE_PSD_SOURCE})
    return blocks


def _pro_lsb_by_channel(pro_times, lsb, td_recordings, event_psd_blocks,
                        sensing_hz_by_channel, *, native_tol_s=120.0):
    """One per-PRO LSB selection series per channel for the timeline (CS-4 consumer of per_pro_lsb).

    For each channel that has a resolvable sensing center, run availability.per_pro_lsb over the PRO
    timestamps with the SAME inputs the inline lsb_series uses:
      * native_lsb_series = that channel's lsb_series entry (NATIVE samples are selected inside
        per_pro_lsb via its modeled-mask, so the modeled/bridge points in the series are ignored for
        the native tier and only the sensed samples can win tier 1);
      * td_recordings = TD-bearing recordings (streaming + montage/survey, all 250 Hz TD) for tier 2;
      * event_psd_recordings = the CS-3 PSD-only event blocks for tier 3.

    The per-channel center is the configured sensing center (sensing_hz_by_channel, canonical key),
    falling back to the channel's own series center_hz (first finite). Channels with no center resolve
    to nothing (the band is undefined). Returns { raw_channel: [ {t,lsb,tier,center_hz,used_s,
    saturated,reason}, ... ] } — one entry per PRO, in PRO order; empty dict when there are no PROs.
    """
    out = {}
    pt = np.asarray([] if pro_times is None else pro_times, dtype=float)
    if pt.size == 0:
        return out
    sensing_hz_by_channel = sensing_hz_by_channel or {}
    # ONE canonical form for every channel's call (Track B step 2): the recordings are grouped by
    # channel and their start times parsed once here, not once per channel and per pain report.
    index = (availability.channel_index(td_recordings, event_psd_blocks)
             if availability.USE_CHANNEL_INDEX else None)
    for raw_ch, series in (lsb or {}).items():
        key = availability._canon_channel(raw_ch)
        # ONE center per channel — the configured sensing center (deployment 'one band' semantics).
        # CAVEAT: if a channel's sensing band was RETUNED over the implant, native samples recorded at
        # an earlier band fall outside [center±half] and silently demote to TD/bridge/None for PROs near
        # that period. The per-PRO center_hz is returned in the payload so this is auditable downstream.
        # `is not None` (not `or`) so a stored 0.0 Hz doesn't silently fall through to the series center.
        center = sensing_hz_by_channel.get(key)
        if center is None:
            center = sensing_hz_by_channel.get(raw_ch)
        if center is None:
            # fall back to the first finite center the inline series carries for this channel
            for hz in (series.get("center_hz") or []):
                if hz is not None and np.isfinite(hz) and float(hz) > 0:
                    center = float(hz); break
        if center is None or not np.isfinite(center) or float(center) <= 0:
            continue
        try:
            out[raw_ch] = availability.per_pro_lsb(
                pt, series, key, float(center), native_tol_s=native_tol_s,
                td_recordings=td_recordings, event_psd_recordings=event_psd_blocks, index=index)
        except Exception as e:
            _log.warning("Biomarkers: per-PRO LSB failed for %s (%s)", raw_ch, e)
    return out


# Default band-center grid for the shared per-pair LSB spectrum: full 0-100 Hz on the half-integer
# grid at 1 Hz step; callers can request a different grid (e.g. the timeline's exact sensing center)
# from the SAME builder, so a timeline marker and a spectral point at one center are identical.
_LSB_SPECTRUM_CENTERS = tuple(float(c) for c in np.arange(2.5, 100.0, 1.0))


# Match-AGNOSTIC raw LSB cache memo (availability.raw_lsb_spectrum_cache). Keyed WITHOUT any PRO set —
# the cache tiles the whole recording independent of ratings, so one entry serves every metric /
# strategy / match policy. Live matching (live_lsb_spectrum_match) runs cheaply on top per request.
_RAW_LSB_CACHE_MEMO = {}
_RAW_LSB_CACHE_MEMO_MAX = 8
_RAW_LSB_CACHE_MEMO_LOCK = threading.Lock()

# Per-participant recording/PSD-block setup memo, for the hover-cell endpoint
# (band_time_sweep_cell_for_participant) alone. Timed live on RCS08: that endpoint was redoing
# ~2s of this exact setup (recordings load + event/montage PSD block building) from scratch on
# EVERY hover, though none of it depends on which cell was hovered -- the parent grid request
# already builds it once. Recordings may be cached with no expiry (decision 22), so a plain
# unbounded-lifetime memo is the right shape here, matching `_RAW_LSB_CACHE_MEMO` above. This memo
# holds NO pain-report data at all -- decision 22 forbids caching those, and `_load_pros` is
# deliberately left OUTSIDE this memo, called fresh on every request as before.
_RECORDINGS_SETUP_MEMO = {}
_RECORDINGS_SETUP_MEMO_MAX = 8
_RECORDINGS_SETUP_MEMO_LOCK = threading.Lock()

#: ==========================================================================================
#: A NARROW, DELIBERATE OVERRIDE OF DECISION 22, authorised by the PI directly on 2026-09-08.
#:
#: WHAT DECISION 22 SAID, AND WHY IT IS NOT BEING CONTRADICTED. Its finding was that no check can
#: prove a remembered pain-report table still current more cheaply than fetching it again. That
#: finding stands and is not worked around: the only content check this module has
#: (`_pro_table_digest`) hashes the table AFTER it has been fetched, so it can dedup a write but
#: can never save the fetch, and there is no metadata-only "has anything changed" call to REDCap
#: here to consult instead. Nothing below pretends otherwise.
#:
#: THE RULE THE PI ASKED FOR INSTEAD, in his own framing: once the Biomarkers module has loaded and
#: everything is on screen, the report table is held; it is fetched again only when someone presses
#: Recompute on the module, or when the page's data is being computed from a new load.
#:
#: HOW THAT RULE IS IMPLEMENTED, with no clock anywhere in it. Every endpoint that BUILDS something
#: -- the module compute (`run_for_participant`, which is what Recompute triggers), the
#: band-by-length grid (`band_time_sweep_for_participant`), the availability timeline, the
#: pain-score preview -- still calls `_load_pros` and therefore still fetches fresh, exactly as
#: before. `_load_pros` hands each such fetch to `_remember_pain_reports`, so THIS cache is always
#: "whatever the most recent real fetch produced". The read-only drill-downs (the hover preview and
#: the pinned cell panel) read it back through `_pain_reports_for_drilldown` instead of fetching.
#: The invalidation rule is therefore the whole of the mechanism: a build replaces the entry, and
#: nothing else has to expire it.
#:
#: WHAT A READER GIVES UP. A rating filed while a grid is already on screen does not reach a hover
#: preview until the next build -- pressing Recompute, changing a matching or binarization setting,
#: or reloading the page. Every number that is stored, exported or reported still comes from a
#: fresh fetch, because every path that produces one is a build.
#:
#: FOUR WORKERS, FOUR CACHES. gunicorn runs four worker processes and this dict is per-process, so
#: a hover that lands on a worker which has not built anything for this participant simply fetches
#: once and seeds itself. That is self-healing and needs no cross-worker invalidation.
#: ==========================================================================================
_PRO_BUILD_CACHE = {}
_PRO_BUILD_CACHE_MAX = 4
_PRO_BUILD_CACHE_LOCK = threading.Lock()

#: Distinguishes "this worker has never fetched for this participant" from "the fetch produced no
#: reports at all", which is a real answer and must not trigger a refetch on every hover.
_PRO_BUILD_CACHE_MISS = object()


def _pro_build_cache_key(request_data, participant):
    """Participant identity alone -- the report table does not depend on any matching setting.

    Returns None for the two asks this cache must never answer: a request carrying its own report
    rows (`ProcessedPRO`) and one carrying an inline field-map override (`RedcapFieldMap`), since
    a table keyed on the participant alone could otherwise answer a differently-mapped question.
    """
    if request_data.get("ProcessedPRO") or request_data.get("RedcapFieldMap"):
        return None
    return _pro_participant_uid(request_data, participant)


def _remember_pain_reports(request_data, participant, df):
    """Hold the table a real fetch just produced, replacing whatever the previous build left."""
    uid = _pro_build_cache_key(request_data, participant)
    if uid is None:
        return
    with _PRO_BUILD_CACHE_LOCK:
        if uid not in _PRO_BUILD_CACHE and len(_PRO_BUILD_CACHE) >= _PRO_BUILD_CACHE_MAX:
            _PRO_BUILD_CACHE.pop(next(iter(_PRO_BUILD_CACHE)))
        _PRO_BUILD_CACHE[uid] = df.copy() if df is not None else None


def _pain_reports_for_drilldown(request_data, participant):
    """The report table the most recent build fetched; a fresh fetch when this worker has none.

    For the read-only drill-downs ONLY (hover preview, pinned cell panel). See the override note
    above for the rule this implements and what it costs.
    """
    uid = _pro_build_cache_key(request_data, participant)
    if uid is not None:
        with _PRO_BUILD_CACHE_LOCK:
            held = _PRO_BUILD_CACHE.get(uid, _PRO_BUILD_CACHE_MISS)
        if held is not _PRO_BUILD_CACHE_MISS:
            return held.copy() if held is not None else None
    return _load_pros(request_data, participant)


def _recordings_setup_cached(participant_uid, td=None):
    """(td, psd_list, event_blocks, montage_blocks, chan_order, channels) for one participant.

    Memoized in-process, and holding no pain-report data of any kind -- the report table has its
    own, separately-ruled cache (`_PRO_BUILD_CACHE`), and mixing the two here would hide which of
    them a given reader is actually relying on.

    `td` lets a caller that has ALREADY loaded the time-domain recordings hand them in rather than
    have them read a second time; the grid build does exactly that. It is only consulted when this
    participant is not in the memo yet.
    """
    with _RECORDINGS_SETUP_MEMO_LOCK:
        cached = _RECORDINGS_SETUP_MEMO.get(participant_uid)
    if cached is not None:
        return cached
    td = td if td is not None else _load_recordings(participant_uid, TIMEDOMAIN_TYPES)
    psd_list = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
    sensing_idx = _build_sensing_config_index(list(td or []))
    event_blocks = _event_psd_lsb_blocks(participant_uid, sensing_index=sensing_idx)
    montage_blocks = _montage_psd_lsb_blocks(participant_uid, montage_recordings=psd_list)
    chan_order = _derive_chan_order(td)
    channels = list(dict.fromkeys(availability._canon_channel(c) for c in (chan_order or [])))
    result = (td, psd_list, event_blocks, montage_blocks, chan_order, channels)
    with _RECORDINGS_SETUP_MEMO_LOCK:
        if len(_RECORDINGS_SETUP_MEMO) >= _RECORDINGS_SETUP_MEMO_MAX:
            _RECORDINGS_SETUP_MEMO.pop(next(iter(_RECORDINGS_SETUP_MEMO)))
        _RECORDINGS_SETUP_MEMO[participant_uid] = result
    return result


# Same shape and same decision-22 justification as _RECORDINGS_SETUP_MEMO above (recordings are
# immutable once exported, so a no-expiry, participant-keyed memo is safe): the chronic/power-domain
# branch had no cache at all, unlike the time-domain branch's _cached_psd_matrix. Holds ONLY
# recording-derived data (chronic_list, powerdomain_list, and their already-concatenated
# power_list), never any pain-report data.
_POWER_LIST_MEMO = {}
_POWER_LIST_MEMO_MAX = 8
_POWER_LIST_MEMO_LOCK = threading.Lock()


def _power_list_cached(participant_uid):
    """(chronic_list, powerdomain_list, power_list) for one participant, memoized in-process.

    `power_list` is `chronic_list` concatenated with `powerdomain_list` converted to chronic-shaped
    entries (adapter.bravo_powerdomain_to_chronic_like) -- exactly the value run_for_participant's
    powerdomain/both branch already built inline before this memo existed, moved here unchanged so
    a second request for the same participant does not reload and re-concatenate it.
    """
    with _POWER_LIST_MEMO_LOCK:
        cached = _POWER_LIST_MEMO.get(participant_uid)
    if cached is not None:
        return cached
    chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES)
    powerdomain_list = _load_recordings(participant_uid, POWERDOMAIN_TYPES)
    for c in chronic_list:
        if isinstance(c, dict):
            c.setdefault("Source", "chronic")
    power_list = list(chronic_list) + adapter.bravo_powerdomain_to_chronic_like(powerdomain_list)
    result = (chronic_list, powerdomain_list, power_list)
    with _POWER_LIST_MEMO_LOCK:
        if len(_POWER_LIST_MEMO) >= _POWER_LIST_MEMO_MAX:
            _POWER_LIST_MEMO.pop(next(iter(_POWER_LIST_MEMO)))
        _POWER_LIST_MEMO[participant_uid] = result
    return result


# Same decision-22 justification as _RECORDINGS_SETUP_MEMO/_POWER_LIST_MEMO above (recordings are
# immutable once exported): availability_for_participant's own three raw loads (td, chronic_list,
# powerdomain_list), memoized in-process. Deliberately a THIRD, narrower memo rather than a reuse
# of the two above: _recordings_setup_cached also builds psd_list/event/montage PSD blocks this
# lightweight endpoint never reads, and _power_list_cached does not carry td. Holds no pain-report
# data of any kind.
_AVAILABILITY_RECORDINGS_MEMO = {}
_AVAILABILITY_RECORDINGS_MEMO_MAX = 8
_AVAILABILITY_RECORDINGS_MEMO_LOCK = threading.Lock()


def _availability_recordings_cached(participant_uid):
    """(td, chronic_list, powerdomain_list) for one participant, memoized in-process."""
    with _AVAILABILITY_RECORDINGS_MEMO_LOCK:
        cached = _AVAILABILITY_RECORDINGS_MEMO.get(participant_uid)
    if cached is not None:
        return cached
    td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES)
    chronic_list = _load_recordings(participant_uid, CHRONIC_TYPES)
    powerdomain_list = _load_recordings(participant_uid, POWERDOMAIN_TYPES)
    for c in chronic_list:
        if isinstance(c, dict):
            c.setdefault("Source", "chronic")
    result = (td, chronic_list, powerdomain_list)
    with _AVAILABILITY_RECORDINGS_MEMO_LOCK:
        if len(_AVAILABILITY_RECORDINGS_MEMO) >= _AVAILABILITY_RECORDINGS_MEMO_MAX:
            _AVAILABILITY_RECORDINGS_MEMO.pop(next(iter(_AVAILABILITY_RECORDINGS_MEMO)))
        _AVAILABILITY_RECORDINGS_MEMO[participant_uid] = result
    return result


# Caches _build_availability's own OUTPUT for availability_for_participant, keyed on every input
# that could change it -- participant, the native-LSB-tolerance knob (the one live-updating control
# this lightweight endpoint reads), the resolved label metric, and a CONTENT DIGEST of the
# pain-report table (never the participant alone) -- so a newly-filed rating is a cache MISS, never
# a stale HIT, honouring decision 22's rule that no pain-derived product may serve stale. No expiry
# beyond that: recordings are immutable once exported and everything else that could change the
# answer is already in the key. `_load_pros` itself is NOT memoized here or anywhere in this
# function -- decision 22 requires it fetched fresh every time, which is also what makes the digest
# in this key trustworthy rather than itself stale.
_AVAILABILITY_RESULT_MEMO = {}
_AVAILABILITY_RESULT_MEMO_MAX = 8
_AVAILABILITY_RESULT_MEMO_LOCK = threading.Lock()


def _availability_result_cached(key, build_fn):
    """Return the cached availability result for `key`, else call `build_fn()`, store it, return it."""
    with _AVAILABILITY_RESULT_MEMO_LOCK:
        cached = _AVAILABILITY_RESULT_MEMO.get(key)
    if cached is not None:
        return cached
    result = build_fn()
    with _AVAILABILITY_RESULT_MEMO_LOCK:
        if key not in _AVAILABILITY_RESULT_MEMO and len(_AVAILABILITY_RESULT_MEMO) >= _AVAILABILITY_RESULT_MEMO_MAX:
            _AVAILABILITY_RESULT_MEMO.pop(next(iter(_AVAILABILITY_RESULT_MEMO)))
        _AVAILABILITY_RESULT_MEMO[key] = result
    return result


def _lsb_spectrum_signature(participant_uid, pro_times, td_recordings, event_psd_blocks, centers,
                            montage_psd_blocks=None):
    """Content signature for the per-pair LSB spectrum: participant + PRO set + the TD/event/montage
    recording identities + the band-center grid. Any change to the PROs, the recordings feeding the
    transform/bridge, or the centers misses the memo and recomputes."""
    import hashlib
    h = hashlib.sha1()
    h.update(str(participant_uid).encode())
    h.update(_pro_set_signature(pro_times).encode())
    # recording identity: StartTime + channel names + sample count is enough to detect a content change
    for tag, recs in (("td", td_recordings or []), ("ev", event_psd_blocks or []),
                      ("mt", montage_psd_blocks or [])):
        h.update(tag.encode())
        for r in recs:
            if not isinstance(r, dict):
                continue
            st = r.get("StartTime") if "StartTime" in r else r.get("t")
            names = r.get("ChannelNames") or r.get("channel") or ""
            data = r.get("Data")
            freq = r.get("freq")
            if data is not None:
                n = np.asarray(data).shape[0]
            elif freq is not None:
                n = np.asarray(freq).size
            else:
                n = 0
            h.update(f"{st}|{names}|{n};".encode())
    h.update(np.asarray(centers, dtype=float).tobytes())
    return h.hexdigest()[:16]


def _stamp_td_product(td_recordings):
    """Tag each decoded TD recording dict with a `product` key (streaming_td / indefinite) IN PLACE so
    the raw cache can label its window source (TD_PRODUCT_SOURCE_LABEL). Decoded payloads carry the
    indefinite/streaming discriminator (`Source`=='indefinite' or an `IndefiniteStream` flag) but no
    `product`; montage/survey TD passed in separately is tagged montage_td. Idempotent."""
    for r in (td_recordings or []):
        if not isinstance(r, dict) or r.get("product"):
            continue
        if r.get("RecordingType") == "MedtronicIndefiniteStream" or r.get("Source") == "indefinite" or r.get("IndefiniteStream"):
            r["product"] = "indefinite"
        else:
            r["product"] = "streaming_td"
    return td_recordings


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# THE SAME 3 s-TILE CACHE, SHARED BETWEEN THE SERVER'S WORKER PROCESSES AND ACROSS RESTARTS
# ─────────────────────────────────────────────────────────────────────────────────────────────────
#: WHY A FILE AND NOT JUST THE TWO MEMOS ABOVE. `_RAW_LSB_CACHE_MEMO` lives in one process's
#: memory, and the server runs FOUR worker processes (boot.sh caps gunicorn at four, because
#: sixteen exhausted the lab machine's memory). Two requests from the same page can land on two
#: different workers, so the memo alone makes "built once" true per worker and not per
#: participant: the first request to reach each worker pays the whole build, and there are four
#: workers. The development server also runs with reload enabled, so every edit to any Python file
#: replaces all four workers and throws every memo away again. That is why the band-by-length-of-
#: signal panel still felt slow after the memo went in.
#:
#: THE MEASUREMENT THAT DECIDED THIS, taken on participant RCS08 through the bridge on 2026-09-06,
#: stage by stage in a genuinely fresh process. Reading and decoding the stored Percept files takes
#: 1.55 s for the time-domain products, 0.36 s for the montage and survey products and 0.35 s for
#: the patient-event spectra. Fetching the pain reports from REDCap takes 0.86 s. Matching the
#: reports against the tiles and computing every statistic the panel shows takes 2.34 s. Cutting
#: the whole recording history into 3 s tiles and computing a 98-band spectrum for each of them
#: takes 37.09 s — that one step is the delay the PI reported. The finished tiles for all six
#: sensing contact pairs (298,953 time-domain tiles and 5,525 device-spectrum windows) hold 245 MB
#: once each window family's rows are stored as one array; they write in 0.10 s and read back in
#: 0.05 s. So a worker that finds the file does in a twentieth of a second what would otherwise
#: take thirty-seven seconds.
#:
#: WHAT IS DELIBERATELY NOT DONE HERE. There is no expiry time. An expiry-based cache serves a
#: stale answer for however long the window lasts and then hides the fact by fixing itself, and
#: this project has already lost a session to that class of confusion. The file is keyed on the
#: identity and content of every recording that feeds it, so a new ingest replaces it immediately
#: and nothing else does.
#:
#: THE PAIN REPORTS ARE NOT IN HERE, AND THAT IS THE POINT. What this file holds is the 3 s tile
#: cache, which `raw_lsb_spectrum_cache` builds with no knowledge of any rating — the same tiles
#: serve every choice of pain score, every match rule and every length of signal. The pain reports
#: are fetched from REDCap on every single request, exactly as before, and matched against the
#: tiles live. So a pain report filed one second ago is in the answer, and this cache cannot make
#: any statement about pain stale. Caching the reports themselves was refused for measured reasons
#: (commit c70e0b0); nothing here revisits that.
_RAW_LSB_SHARED_KIND = "raw_lsb_tiles"

#: Bumped by hand whenever the RULE that produces the tiles changes in a way the constants below
#: do not capture — the tiling itself, the quality gate, the channel assignment. This module also
#: carries `_CHANNEL_CANON_VERSION`, `_TD_CENTERED_VERSION` and `_TD_MISSING_VERSION` for the
#: per-recording spectrum files for the same reason.
_RAW_LSB_RULE_VERSION = "v1_tiles"

#: ===========================================================================================
#: THE STORE ITSELF NOW LIVES IN ONE PLACE: `modules/CacheStore/store.py`.
#:
#: This module used to carry its own directory resolver, loader, writer, sweeper, event counters
#: and lock, and `ClosedLoopDeployment/adapter.py` carried a second copy of all of it. The two
#: shared a root by construction accident rather than by design, and their per-entry limits
#: differed by exactly a factor of four — 1,073,741,824 bytes here against 268,435,456 there — for
#: no stated reason. Stim Optimizer, the slowest endpoint, had no store at all.
#:
#: What is left below is a thin delegation. The names are kept because this module's own tests and
#: three bridge scripts call them, and because a caller should not have to know which file the
#: store lives in. Everything they do now happens once, in the shared store:
#:
#:   * the SAME limit for every kind, and it is the larger of the two. The smaller one, the
#:     closed-loop module's 268,435,456 bytes, is 256 MiB and would NOT have refused today's
#:     245.90 MB tile entry — it leaves 4 to 9 percent to spare. Single-digit headroom on the one
#:     entry the cache exists to hold is the reason, and crossing a limit is SILENT: the write is
#:     refused and the page just becomes slow again;
#:   * the SAME event counters across all three modules, so a page can report what the cache as a
#:     whole is doing rather than what one module's copy of it did;
#:   * a stamp beside every entry saying when and why it was written, readable without opening a
#:     245 MB file;
#:   * a provenance chain on anything written back, and a refusal to hand a module a product its
#:     own output helped produce.
#:
#: THE TILE FILES ALREADY ON DISK ARE STILL FOUND. The shared store keeps this kind's historical
#: directory and its historical file name, because 245.90 MB of tiles are already there and cost
#: 37 seconds to rebuild.
#: ===========================================================================================
# THE IMPORT ROOT DIFFERS BETWEEN THE TWO TEST RUNNERS, so both spellings are tried. The
# container puts `/usr/src/BRAVO` on the path, which makes this package `modules.CacheStore`; the
# host suite runs from `BRAVO/modules` with that directory as the root, which makes it
# `CacheStore`. A single spelling breaks one of the two runners at import time, which is how this
# was found.
try:
    from modules.CacheStore import locks as _locks
    from modules.CacheStore import store as _cache_store
except ImportError:                                   # pragma: no cover - depends on the runner
    from CacheStore import locks as _locks
    from CacheStore import store as _cache_store

#: Tests point this at a directory of their own. It is passed THROUGH to the shared store rather
#: than resolved here, so there is still only one resolver.
_SHARED_CACHE_DIR_OVERRIDE = None

#: Refuse to write an entry larger than this. Tests lower it to check the refusal.
_SHARED_CACHE_MAX_BYTES = _cache_store.MAX_BYTES_DEFAULT

#: Part of the file name, so an older file is never read by newer code.
_SHARED_CACHE_FORMAT = _cache_store.FORMAT_VERSION

#: THE SAME OBJECTS the shared store counts into and locks with, bound by reference rather than
#: copied — so a count read here is the count the store actually made.
_SHARED_CACHE_EVENTS = _cache_store._EVENTS
_SHARED_CACHE_LOCK = _cache_store._LOCK


def shared_cache_dir():
    """Where this module's shared files go, or None when there is nowhere to put them."""
    return _cache_store.kind_dir(_RAW_LSB_SHARED_KIND, root=_SHARED_CACHE_DIR_OVERRIDE)


def _shared_path(kind, participant_uid, signature):
    """The file this signature would be stored at, or None."""
    stem = _cache_store._stem(kind, participant_uid, signature,
                              root=_SHARED_CACHE_DIR_OVERRIDE)
    return None if stem is None else stem + ".pkl"


def _shared_load(kind, participant_uid, signature):
    """The stored product for this signature, or None. Every failure is a miss, never an error."""
    return _cache_store.load(kind, participant_uid, signature,
                             root=_SHARED_CACHE_DIR_OVERRIDE)


def _shared_store(kind, participant_uid, signature, payload):
    """Write the product where the other worker processes can find it. True if it landed."""
    return _cache_store.store(kind, participant_uid, signature, payload,
                              writer="biomarkers", trigger="tile_build",
                              root=_SHARED_CACHE_DIR_OVERRIDE,
                              max_bytes=_SHARED_CACHE_MAX_BYTES)


def shared_cache_stats():
    """What this module's kind holds, and what the store as a whole has done."""
    d = shared_cache_dir()
    entries, total = 0, 0
    if d is not None and os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith(".tmp") or f.endswith(".meta.json"):
                continue
            entries += 1
            try:
                total += os.path.getsize(os.path.join(d, f))
            except OSError:
                pass                 # a concurrent sweep can remove a file between the two calls
    with _SHARED_CACHE_LOCK:
        events = dict(_SHARED_CACHE_EVENTS)
    return {"dir": d, "entries": entries, "bytes": total,
            "max_bytes_per_entry": _SHARED_CACHE_MAX_BYTES, "events": events}


def clear_shared_cache():
    """Remove this module's stored entries, including ones from an older format version."""
    return _cache_store.clear(_RAW_LSB_SHARED_KIND, root=_SHARED_CACHE_DIR_OVERRIDE)



def _raw_lsb_constants_block():
    """Every constant the stored tiles depend on, so editing one of them misses the file.

    A file that outlives the process has to answer a question a memo never faces: the code that
    wrote it may not be the code that reads it. Changing the transform's calibration constant, the
    tile width or the band on which the device spectrum is trusted changes every number in the
    file while leaving every recording untouched, so none of it would show up in a recording key.
    Folding the constants into the key means such an edit misses the file and rebuilds, which is
    the same protection the per-recording spectrum files already get from their own version
    strings in `_recording_psd_cache_path`.
    """
    return (
        _RAW_LSB_RULE_VERSION,
        _CHANNEL_CANON_VERSION,
        float(analytics.RAW_LSB_WINDOW_SECONDS),
        float(analytics.LSB_PER_UV2_TRANSFORM),
        float(analytics.LSB_PER_DEVICE_PSD),
        float(analytics.LSB_VALIDATED_HZ_LO),
        float(analytics.LSB_DEPLOYABLE_HZ_HI),
        float(analytics.TRANSFORM_WIN_SECONDS),
        float(analytics.TRANSFORM_STEP_SECONDS),
        float(availability.PRO_LSB_SATURATION_UV),
    )


def _raw_lsb_recording_identity(participant_uid):
    """Identity AND content of every database row that feeds the tiles, with no file decoded.

    WHY THIS IS A SEPARATE KEY FROM `_lsb_spectrum_signature`. That signature is built from the
    DECODED recordings, which is fine for a memo the decode has already paid for, but it cannot be
    the key of a file: the whole point of the file is to be found before any heavy work is done,
    and the warming entry point below has to be able to ask "is this already built?" without
    reading 569 stored Percept files. This key is built from the database rows alone, which cost
    0.33 s to fetch for RCS08's 4,078 rows.

    WHAT IS IN IT, AND WHAT HAD TO BE ADDED. For the file-backed products — the time-domain
    streams, the indefinite streams and the montage and survey recordings — the row carries a
    content hash (`hashed`), so identity plus that hash plus the type is content-complete, which is
    the same choice `ClosedLoopDeployment.adapter.recording_set_signature` makes and for the same
    stated reason: a re-decode that replaces a recording in place changes neither a count nor a
    latest date, and a count alone would also miss a deletion balanced by an insertion.

    Two things had to be ADDED beyond that, because the tiles depend on inputs `hashed` does not
    cover:

      * THE PATIENT-EVENT ROWS CARRY NO CONTENT HASH AT ALL. Measured on RCS08: 0 of 3,246
        PatientControllerEvent rows have one, because their spectra are not in a stored file — the
        per-hemisphere `Frequency` and `FFTBinData` ARE the row's `metadata`. Keying those rows on
        identity alone would leave every change to a patient-event spectrum invisible to the cache,
        so the whole of each such row's `metadata` is hashed. It costs 0.13 s for all 3,246 rows.
      * THE SENSING FIELDS STAMPED ON A FILE-BACKED ROW AFTER DECODING. `CenterFrequencyHz`,
        `FreqScheduleHz` and `ContactSchedule` are written onto `Recording.metadata` at decode time
        rather than living in the stored file, and they decide which sensing contact pair a
        patient-event spectrum is assigned to. They can therefore change with no change to
        `hashed`, so they are in the key too.
    """
    import hashlib
    Participant = models.Participant.find(uid=participant_uid)
    if not Participant:
        return None
    SourceFiles = models.SourceFile.find_all(owner=Participant)
    if not SourceFiles:
        return None
    types = list(TIMEDOMAIN_TYPES) + list(AVAILABILITY_PSD_TYPES) + [PATIENT_EVENT_TYPE]
    rows = list(models.Recording.find_all(source__in=SourceFiles, type__in=types))
    if not rows:
        return None
    parts = []
    for r in rows:
        rtype = str(getattr(r, "type", ""))
        md = getattr(r, "metadata", None)
        if rtype == PATIENT_EVENT_TYPE:
            extra = repr(md)                        # the row's metadata IS this product's content
        elif isinstance(md, dict):
            extra = "%r|%r|%r" % (md.get("CenterFrequencyHz"), md.get("FreqScheduleHz"),
                                  md.get("ContactSchedule"))
        else:
            extra = ""
        parts.append("%s~%s~%s~%s" % (getattr(r, "uid", ""), getattr(r, "hashed", "") or "",
                                      rtype, extra))
    h = hashlib.sha1()
    for s in sorted(parts):                          # sorted, so row order can never move the key
        h.update(s.encode("utf8", "replace"))
        h.update(b"\x00")
    return (str(participant_uid), len(SourceFiles), len(rows), h.hexdigest()[:20])


def _raw_lsb_shared_signature(participant_uid, centers, *, identity=None):
    """The full key of one stored tile-cache file, or None when it cannot be built.

    The sensing contact pairs are NOT in the key, and do not need to be: the list of pairs is
    derived from the recordings by `_derive_chan_order`, so the recording identity already decides
    it. `_raw_lsb_cache_cached` still checks that every pair it was asked for is present in a file
    it loads and treats a shortfall as a miss, so the one path that could go wrong — a caller
    asking for a pair the stored product does not hold — rebuilds instead of answering short.
    """
    ident = _raw_lsb_recording_identity(participant_uid) if identity is None else identity
    if ident is None:
        return None
    cen = np.asarray(centers, dtype=float)
    import hashlib
    return (ident, hashlib.sha1(cen.tobytes()).hexdigest()[:16], int(cen.size),
            _raw_lsb_constants_block())


# Which fields of a window family are stored in which shape. Storing the per-window rows as one
# array rather than as a list of lists is what brings the RCS08 entry from 272 MB to 245 MB and,
# far more importantly, its read from 0.56 s to 0.05 s: a list of lists has to be rebuilt as
# 29 million separate Python numbers, an array does not.
_RAW_LSB_FLOAT_VECTORS = ("t", "n_finite_s")
_RAW_LSB_BOOL_VECTORS = ("saturated", "ok")
_RAW_LSB_MATRICES = ("lsb",)
_RAW_LSB_BOOL_MATRICES = ("calibrated",)


def _raw_lsb_pack(by_channel):
    """The tile cache in the shape it is stored in. Raises if anything is not as expected.

    The caller treats a failure here as "do not share this one", never as a failed request.
    """
    out = {}
    for ch, entry in (by_channel or {}).items():
        if not isinstance(entry, dict):
            out[ch] = entry
            continue
        nC = int(np.asarray(entry.get("centers_hz") or [], dtype=float).size)
        packed_entry = {k: v for k, v in entry.items() if k not in ("td", "psd")}
        for fam_name in ("td", "psd"):
            fam = entry.get(fam_name)
            if not isinstance(fam, dict):
                packed_entry[fam_name] = fam
                continue
            fam_out = {}
            for k, v in fam.items():
                if k == availability._LSB_MAT_MEMO_KEY:
                    # The matcher parks its own converted matrix in the family dict. Storing it
                    # would put the same numbers in the file twice: measured on RCS08, the entry
                    # goes from 245 MB to 511 MB if this is left in.
                    continue
                if k in _RAW_LSB_MATRICES:
                    fam_out[k] = availability._lsb_rows_to_mat(v or [], nC)
                elif k in _RAW_LSB_BOOL_MATRICES:
                    fam_out[k] = (np.asarray(v, dtype=bool) if v is not None and len(v)
                                  else np.empty((0, nC), dtype=bool))
                elif k in _RAW_LSB_FLOAT_VECTORS:
                    fam_out[k] = np.asarray(v if v is not None else [], dtype=float)
                elif k in _RAW_LSB_BOOL_VECTORS:
                    fam_out[k] = np.asarray(v if v is not None else [], dtype=bool)
                elif k == "source":
                    src = [str(s) for s in (v or [])]
                    labels = sorted(set(src))
                    code = {s: i for i, s in enumerate(labels)}
                    fam_out[k] = {"labels": labels,
                                  "codes": np.asarray([code[s] for s in src], dtype=np.int32)}
                else:
                    fam_out[k] = v
            packed_entry[fam_name] = fam_out
        out[ch] = packed_entry
    return out


def _raw_lsb_unpack(stored):
    """The stored shape turned back into what `raw_lsb_spectrum_cache` returns.

    Every field goes back to the list it was built as, with ONE deliberate exception: the
    per-window spectra stay as the float array they were stored as. Turning 29 million numbers
    back into Python floats would cost most of what the file saves, and the only reader of that
    field is `availability._lsb_family_mat`, which wants a float array and now accepts one
    directly (see its own note). The values are the same either way: the array is exactly what
    that function builds from the list, checked value by value in
    tests/test_shared_raw_lsb_cache.py.

    THE RETURNED PRODUCT IS READ-ONLY TO CALLERS, or must be copied before being changed. Every
    worker that loads this file, and every panel served by that worker, is handed the same object,
    exactly as with the in-process memo. The spectra array is additionally marked non-writeable by
    `_lsb_family_mat`, so an attempt to change it fails loudly instead of quietly corrupting what
    another panel is about to read.
    """
    out = {}
    for ch, entry in (stored or {}).items():
        if not isinstance(entry, dict):
            out[ch] = entry
            continue
        rebuilt = {k: v for k, v in entry.items() if k not in ("td", "psd")}
        for fam_name in ("td", "psd"):
            fam = entry.get(fam_name)
            if not isinstance(fam, dict):
                rebuilt[fam_name] = fam
                continue
            fam_out = {}
            for k, v in fam.items():
                if k in _RAW_LSB_MATRICES and isinstance(v, np.ndarray):
                    fam_out[k] = v
                elif k == "source" and isinstance(v, dict) and "codes" in v:
                    labels = list(v.get("labels") or [])
                    fam_out[k] = [labels[int(i)] for i in np.asarray(v["codes"]).tolist()]
                elif isinstance(v, np.ndarray):
                    fam_out[k] = v.tolist()
                else:
                    fam_out[k] = v
            rebuilt[fam_name] = fam_out
        out[ch] = rebuilt
    return out


def _raw_lsb_cache_cached(participant_uid, channels, td_recordings, event_psd_blocks,
                          *, montage_psd_blocks=None, centers=_LSB_SPECTRUM_CENTERS,
                          use_shared_cache=True, shared_sig=None):
    """Memoized per-channel match-AGNOSTIC raw LSB cache. The signature deliberately OMITS any PRO set
    (the cache does not depend on ratings) — only participant + recording identities + centers. Returns
    { raw_channel: availability.raw_lsb_spectrum_cache(...) }. montage_psd_blocks (the montage/survey
    device-PSD snapshots) are folded into the cache's PSD family alongside the patient-event PSDs.

    THREE PLACES THE ANSWER CAN COME FROM, cheapest first: this process's own memo, the file the
    other worker processes share (see the long note above this function), and a build. Anything
    that goes wrong with the file is a rebuild, never a failed request.

    `use_shared_cache=False` bypasses the file in both directions, neither reading nor writing it.
    It exists so that a build with the cache out of the picture can be compared against a build
    that used it, which is how the stored product is checked against a fresh one.
    """
    if not channels:
        return {}
    # reuse the recording-identity signature with an EMPTY pro set so the key is PRO-independent.
    sig = _lsb_spectrum_signature(participant_uid, np.asarray([], dtype=float),
                                  td_recordings, event_psd_blocks, centers,
                                  montage_psd_blocks=montage_psd_blocks) + "|raw"
    with _RAW_LSB_CACHE_MEMO_LOCK:
        cached = _RAW_LSB_CACHE_MEMO.get(sig)
    if cached is not None:
        return cached

    # `shared_sig` lets a caller that has already built the tile key (the sweep does, for its
    # own key) hand it in rather than have the recording rows enumerated and hashed a second time.
    if not (use_shared_cache and shared_cache_dir() is not None):
        shared_sig = None
    elif shared_sig is None:
        try:
            shared_sig = _raw_lsb_shared_signature(participant_uid, centers)
        except Exception as exc:
            _log.info("Biomarkers: could not build the shared tile-cache key (%r); this request "
                      "builds the tiles itself", exc)
            shared_sig = None
    if shared_sig is not None:
        stored = _shared_load(_RAW_LSB_SHARED_KIND, participant_uid, shared_sig)
        if stored is not None:
            loaded = None
            try:
                loaded = _raw_lsb_unpack(stored)
            except Exception as exc:
                _log.warning("Biomarkers: could not read back the shared tile cache (%r); "
                             "rebuilding", exc)
            if loaded is not None and all(ch in loaded for ch in channels):
                _remember_raw_lsb_cache(sig, loaded)
                return loaded
            if loaded is not None:
                with _SHARED_CACHE_LOCK:
                    _SHARED_CACHE_EVENTS["wrong_channels"] += 1

    # ONE BUILD ACROSS THE FOUR WORKERS (Track F step 2). The first worker to miss the shared file
    # takes a short-lived Redis lock keyed on the file's own key and builds; the others wait for the
    # file to appear and read it. A waiter that runs out of patience builds anyway, and Redis being
    # unreachable means building as before, so the page never fails on the lock. With no shared
    # file to share there is nothing to lock.
    if shared_sig is None:
        return _build_raw_lsb_cache(participant_uid, channels, td_recordings, event_psd_blocks,
                                    montage_psd_blocks, centers, sig, shared_sig)
    lock_name = "cachestore:build:%s:%s:%s" % (_RAW_LSB_SHARED_KIND, participant_uid,
                                                _cache_store.signature_key(shared_sig))

    def _ready():
        return _cache_store.read_stamp(_RAW_LSB_SHARED_KIND, participant_uid, shared_sig) is not None

    with _locks.build_lock(lock_name, ttl_s=RAW_LSB_BUILD_LOCK_TTL_S,
                           wait_s=RAW_LSB_BUILD_LOCK_WAIT_S, ready=_ready) as lk:
        if lk.role == "served":
            stored = _shared_load(_RAW_LSB_SHARED_KIND, participant_uid, shared_sig)
            loaded = None
            if stored is not None:
                try:
                    loaded = _raw_lsb_unpack(stored)
                except Exception as exc:
                    _log.warning("Biomarkers: could not read back the tiles another worker built "
                                 "(%r); building", exc)
            if loaded is not None and all(ch in loaded for ch in channels):
                _log.info("Biomarkers: tiles for %s built by another worker; read after %.1f s",
                          participant_uid, lk.waited_s)
                return _remember_raw_lsb_cache(sig, loaded)
        return _build_raw_lsb_cache(participant_uid, channels, td_recordings, event_psd_blocks,
                                    montage_psd_blocks, centers, sig, shared_sig)


#: The build lock's lifetime and a waiter's patience, in seconds. The build measured 36 to 39 s
#: on RCS08 (Track B step 4), so both are set well above it; the lock expiring early would let a
#: second build start, the wait expiring early would do the same, and neither is an error.
RAW_LSB_BUILD_LOCK_TTL_S = 300.0
RAW_LSB_BUILD_LOCK_WAIT_S = 150.0


def _build_raw_lsb_cache(participant_uid, channels, td_recordings, event_psd_blocks,
                         montage_psd_blocks, centers, sig, shared_sig):
    """Build the tiles for every channel, remember them, and share them when there is a file."""
    cen = np.asarray(centers, dtype=float)
    out = {}
    # ONE preparation of every voltage trace for all channels (Track B step 4), instead of
    # resolving the column and converting every recording to float once per channel.
    index = (availability.channel_index(td_recordings, None)
             if availability.USE_CHANNEL_INDEX else None)
    for raw_ch in channels:
        key = availability._canon_channel(raw_ch)
        try:
            out[raw_ch] = availability.raw_lsb_spectrum_cache(
                key, cen, td_recordings=td_recordings, event_psd_recordings=event_psd_blocks,
                montage_psd_recordings=montage_psd_blocks, index=index)
        except Exception as e:
            _log.warning("Biomarkers: raw LSB cache failed for %s (%s)", raw_ch, e)
    remembered = _remember_raw_lsb_cache(sig, out)
    if remembered is not out:
        return remembered                      # another thread won the race; reuse its result
    if shared_sig is not None:
        try:
            _shared_store(_RAW_LSB_SHARED_KIND, participant_uid, shared_sig, _raw_lsb_pack(out))
        except Exception as exc:
            with _SHARED_CACHE_LOCK:
                _SHARED_CACHE_EVENTS["unpackable"] += 1
            _log.info("Biomarkers: the tiles could not be put in shareable shape (%r); they stay "
                      "in this process's memory only", exc)
    return out


def _remember_raw_lsb_cache(sig, out):
    """Put the tiles in this process's memo, bounded. Returns whatever is in the memo afterwards,
    which is another thread's result when that thread got there first."""
    with _RAW_LSB_CACHE_MEMO_LOCK:
        existing = _RAW_LSB_CACHE_MEMO.get(sig)
        if existing is not None:
            return existing
        if len(_RAW_LSB_CACHE_MEMO) >= _RAW_LSB_CACHE_MEMO_MAX:
            _RAW_LSB_CACHE_MEMO.pop(next(iter(_RAW_LSB_CACHE_MEMO)), None)
        _RAW_LSB_CACHE_MEMO[sig] = out
        return out


def cache_status_for_page(participant_uid, *, centers=_LSB_SPECTRUM_CENTERS):
    """The tile entry's last build date for the page, or the plain fact that there is none yet.

    The key is built from database rows alone (decision 24), so this costs no decoding; a
    failure to build it is reported in the block rather than raised, because a page must never
    fail over its own status line.
    """
    meaning = ("the date the three-second band-power tiles for this participant's recordings were "
               "last built; every biomarker number on this page derives from them, and a newer "
               "upload rebuilds them under a new key")
    try:
        sig = _raw_lsb_shared_signature(participant_uid, centers)
    except Exception as exc:                          # noqa: BLE001
        return {"kind": _RAW_LSB_SHARED_KIND, "exists": False, "last_built_utc": None,
                "what_it_means": meaning, "note": f"the tile key could not be built: {exc!r}"}
    return _cache_store.status_for_page(_RAW_LSB_SHARED_KIND, participant_uid, sig,
                                        what_it_means=meaning)


def warm_shared_raw_cache(participant_uid, *, centers=_LSB_SPECTRUM_CENTERS):
    """Build the shared tile-cache file for this participant if it is not already there.

    SAFE TO CALL AFTER AN INGEST, WHICH IS WHAT IT IS FOR. The shared file makes any one worker's
    build help all four workers; this makes even the FIRST page view after an upload fast, because
    the build has already happened. The two are complementary, not alternatives.

    CHEAP WHEN THERE IS NOTHING TO DO. The only work an already-warm participant costs is the key,
    which is built from database rows alone — 0.46 s on RCS08's 4,078 rows — and one test for the
    existence of a file. No stored Percept file is opened and no tile is computed.

    IT NEVER RAISES. An ingest must not fail because a cache could not be warmed, so every failure
    is logged and reported in the returned dictionary instead. The returned `status` is one of
    "already_warm", "built", "no_directory", "no_recordings", "nothing_to_build" or "failed".
    """
    t0 = _time.perf_counter()

    def done(status, **extra):
        out = {"status": status, "participant": str(participant_uid),
               "seconds": round(_time.perf_counter() - t0, 3)}
        out.update(extra)
        return out

    try:
        if shared_cache_dir() is None:
            return done("no_directory")
        identity = _raw_lsb_recording_identity(participant_uid)
        if identity is None:
            return done("no_recordings")
        sig = _raw_lsb_shared_signature(participant_uid, centers, identity=identity)
        path = _shared_path(_RAW_LSB_SHARED_KIND, participant_uid, sig)
        if path is not None and os.path.exists(path):
            return done("already_warm", path=path)

        td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES)
        psd_list = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
        channels = list(dict.fromkeys(availability._canon_channel(c)
                                      for c in (_derive_chan_order(td) or [])))
        if not channels:
            return done("nothing_to_build")
        sensing_idx = _build_sensing_config_index(list(td or []))
        event_blocks = _event_psd_lsb_blocks(participant_uid, sensing_index=sensing_idx)
        montage_blocks = _montage_psd_lsb_blocks(participant_uid, montage_recordings=psd_list)
        _stamp_td_product(list(td or []))
        _raw_lsb_cache_cached(participant_uid, channels,
                              list(td or []) + list(psd_list or []), event_blocks,
                              montage_psd_blocks=montage_blocks, centers=centers)
        landed = bool(path is not None and os.path.exists(path))
        return done("built", path=path, file_written=landed, channels=channels)
    except Exception as exc:
        _log.warning("Biomarkers: warming the shared tile cache for %s did not finish (%r); "
                     "nothing else is affected", participant_uid, exc, exc_info=True)
        return done("failed", error=repr(exc))


def _live_pro_lsb_spectrum(participant_uid, pro_times, channels, td_recordings, event_psd_blocks,
                           *, montage_psd_blocks=None, centers=_LSB_SPECTRUM_CENTERS,
                           tol_s=None, td_quantity_s=None, allow_window_reuse=False,
                           return_spectra=True):
    """LIVE per-(channel, PRO) LSB spectrum: build the match-agnostic raw cache once, then match PROs
    against it per channel with availability.live_lsb_spectrum_match. Drop-in for the spectral scan:
    returns { raw_channel: [ per-PRO spectrum dict, ... ] } in the SAME contract it consumes.

    TWO-WINDOW MATCHING (PI 2026-06-28): `tol_s` (the main MatchToleranceMin slider, in SECONDS) is
    the eligibility radius for BOTH TD and PSD; `td_quantity_s` (the MatchExtentSec slider) caps how
    many of the nearest 3 s TD tiles to median per PRO (PSD has no quantity cap). Matching runs on the
    pre-computed raw 3 s-tile cache, so there is no real-time TD recompute. Returns (spectra, stats).

    `return_spectra=False` (the caller that only needs `stats`, e.g. run_for_participant's live
    matching-controls caption) skips building the per-PRO record list in
    availability.live_lsb_spectrum_match entirely; `spectra` comes back `{}` and every `stats` value
    is unchanged, since stats never depended on the records in the first place."""
    pt = np.asarray([] if pro_times is None else pro_times, dtype=float)
    if pt.size == 0 or not channels:
        return {}, {}
    _stamp_td_product(td_recordings)
    raw_by_ch = _raw_lsb_cache_cached(participant_uid, channels, td_recordings, event_psd_blocks,
                                      montage_psd_blocks=montage_psd_blocks, centers=centers)
    spectra, stats = {}, {}
    for raw_ch in channels:
        raw_cache = raw_by_ch.get(raw_ch)
        if raw_cache is None:
            continue
        try:
            recs, st = availability.live_lsb_spectrum_match(
                pt, raw_cache, tol_s=tol_s, td_quantity_s=td_quantity_s,
                allow_window_reuse=allow_window_reuse, want_records=return_spectra)
            if return_spectra:
                spectra[raw_ch] = recs
            stats[raw_ch] = st
        except Exception as e:
            _log.warning("Biomarkers: live LSB match failed for %s (%s)", raw_ch, e)
    return spectra, stats


def _load_montage_psd_events(participant_uid, dedup_times=None, tol_s=5.0):
    """Load NeuralActivitySnapshot montage sweeps as montage-PSD marker events, de-duplicated
    against the montage/survey PSD recordings that ALREADY render on the timeline.

    A NeuralActivitySnapshot is an automatic ~20 s montage survey: full-band Welch PSDs over
    reference-montage channels (`PSD[i] = {Frequency, Power, ...}`). ~80% of them coincide (within
    a few seconds) with a MedtronicBrainSenseSurvey/Montages recording already shown as PSD ticks,
    so to avoid double-counting we DROP any snapshot whose StartTime is within `tol_s` of a time in
    `dedup_times` (the montage/survey PSD record StartTimes). The remainder — montage sweeps with no
    matching survey/montage recording — are surfaced as their own markers.

    These are a DISTINCT source from the patient-triggered events: NeuralActivitySnapshot carries its
    own 250 Hz TD (it is a montage product, LSB route = direct TD→LSB transform), whereas patient
    events are PSD-only. They are tagged `category=DISPLAY_MONTAGE_SNAPSHOT` so the timeline keeps them
    separate from the Streaming/labeled patient-event rows (which previously shared the bare
    "Montage PSD" label and caused the mislabel: Streaming-event ticks reading as montage PSDs).

    Returns events normalized for `availability.event_markers`:
        [{"name": DISPLAY_MONTAGE_SNAPSHOT, "category": DISPLAY_MONTAGE_SNAPSHOT,
          "t": epoch_s, "psds": [(freq, power), ...]}, ...]
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
        out.append({"name": DISPLAY_MONTAGE_SNAPSHOT, "category": DISPLAY_MONTAGE_SNAPSHOT,
                    "t": float(t0), "psds": psds})
    return out


# The main bipolar sensing pairs (per hemisphere). The exploratory spectral scan is restricted to
# these — ring/segment montages and reference-electrode channels are dropped (they aren't the
# closed-loop sensing channels and don't map to a single bipolar pair). DESIGN: channel is the gate.
#
# R12 / audit F5: this set is now DERIVED from a pair list × hemispheres rather than hand-listed, and
# is OVERRIDABLE per participant/site via the BRAVO_MAIN_BIPOLAR env var (comma-separated canonical
# channel names) — so onboarding a participant with a different sensing montage (e.g. ZERO_ONE,
# TWO_THREE, or a custom pair) no longer requires a code edit. The default reproduces the original
# six pairs exactly. Pairs are the contiguous + skip-one bipoles available on a 4-contact Percept
# lead; extend `_DEFAULT_BIPOLAR_PAIRS` (or set the env var) for non-standard configurations.
_DEFAULT_BIPOLAR_PAIRS = ("ZERO_THREE", "ONE_THREE", "ZERO_TWO")
_HEMISPHERES = ("LEFT", "RIGHT")


def _build_main_bipolar():
    """Canonical bipolar channel set: env override if present, else pairs × hemispheres default."""
    import os as _os
    override = _os.environ.get("BRAVO_MAIN_BIPOLAR", "").strip()
    if override:
        names = {n.strip().upper() for n in override.split(",") if n.strip()}
        if names:
            return names
    return {f"{p}_{h}" for p in _DEFAULT_BIPOLAR_PAIRS for h in _HEMISPHERES}


_MAIN_BIPOLAR = _build_main_bipolar()

# Bump when the channel-canonicalization rule below changes — folded into the PSD-matrix cache
# signature so a rule change forces a re-Welch instead of serving the stale pre-fix matrix.
_CHANNEL_CANON_VERSION = "v2_ring_aware"

# Version of the rating-centered TD emission LOGIC. Folded into the TD per-recording cache key and
# the rating-centered matrix signature (NOT the montage/survey keys), so changing how centered rows
# are produced invalidates exactly the TD-dependent caches without forcing a full montage re-decode.
# Bump when the centering/fall-back rule changes.
#   v2_fallback: a TD session with NO rating inside its real coverage falls back to a single
#     session-start PSD (tolerance-matchable) instead of emitting nothing. v1 dropped such sessions,
#     which greyed out every short-session TD lane and undercounted the matched pool.
_TD_CENTERED_VERSION = "v2_fallback"

# Version of the TD Missing-aware Welch rejection. Folded into the TD per-recording cache key (same
# places as _TD_CENTERED_VERSION) so enabling/retuning the missing-fraction rejection re-Welch's the
# TD-dependent caches without a full montage re-decode.
#   v1_missing_aware: reject Welch windows whose Missing fraction exceeds WELCH_MAX_MISSING_FRAC, so
#     FixBreaking concatenation zero-fill no longer biases the TD PSD (parity with the PowerDomain
#     adapter, which already drops missing>0 samples).
_TD_MISSING_VERSION = "v1_missing_aware"


def _missing_time_vector(missing, nsamp):
    """Collapse a recording's `Missing` field to a per-sample (n_samples,) 0/1 flag, or None.

    The decoder stores Missing aligned to the Data array, which is (n_samples,) for a single channel
    or (n_samples, n_ch) after hemisphere pairing. A sample is considered missing if ANY channel is
    flagged there (the zero-fill from FixBreaking / dropped-packet insertion spans all channels, so
    this is exact for those; an any-channel rule is the conservative choice regardless). Returns None
    when no usable mask is present, so the Welch helpers keep their legacy (mask-free) behavior.
    """
    if missing is None:
        return None
    m = np.asarray(missing)
    if m.size == 0:
        return None
    if m.ndim == 2:
        # (n_samples, n_ch) or (n_ch, n_samples) -> reduce over the channel axis to (n_samples,)
        axis = 1 if m.shape[0] == nsamp else (0 if m.shape[1] == nsamp else 1)
        m = (np.asarray(m) > 0).any(axis=axis)
    return np.asarray(m).ravel()


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
    # Patient-event PSDs (ORM metadata, no decode) — assigned to their real bipolar channel via
    # the active-sensing resolver. Index built from td_list only (single-channel BrainSense
    # streaming records); psd_list is montage/survey sweeps that sense ALL pairs simultaneously
    # and would be excluded by _build_sensing_config_index's single-channel guard anyway.
    try:
        _ev_idx = _build_sensing_config_index(list(td_list or []))
        rows.extend(_event_psd_rows(participant_uid, sensing_index=_ev_idx))
    except Exception:
        pass
    return rows


def _welch_rows_into(rows, recs, source_label, _sp, pro_times=None):
    """Welch every main-bipolar channel of each loaded recording dict, appending
    {"channel", "source", "t", "freq", "power", "dur"} rows to `rows`.

    Single source of truth for the row schema: BOTH the legacy whole-participant assembly
    (`_assemble_psd_rows`) and the per-recording cache (`_recording_psd_rows`) build rows through
    here, so a matrix assembled from the cache is byte-identical to one assembled the old way.

    `pro_times` : array-like of PRO timestamps (UTC epoch s) or None.
        When None (default — preserves the legacy behavior and every existing test): each recording
        emits ONE row per channel, Welch'd over its FIRST `WELCH_MAX_SECONDS` and stamped at the
        recording START.
        When provided AND `source_label == "TD streaming"`: each TD session emits one
        RATING-CENTERED row per (overlapping PRO, channel) instead — a `WELCH_MAX_SECONDS` window
        centered on each PRO that falls inside [t0, t0+dur], clipped to the session boundary, with
        windows below `WELCH_CENTERED_MIN_SECONDS` of coverage dropped. The row's `t` is the PRO's
        own timestamp, so timestamp matching finds it at offset ~0 (this is the fix for the
        "TD coverage present but no neural match" artifact). Montage/survey/event sources ignore
        `pro_times` and keep the first-window behavior (they are already short ~30 s snapshots whose
        start time IS the rating-relevant time).
    """
    centered = (pro_times is not None and source_label == "TD streaming")
    pt = np.asarray(pro_times, dtype=float) if centered else None
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
        nsamp = int(sig.shape[-1])

        if centered:
            # Ratings that fall inside this session's [t0, t0+dur] coverage. dur is the ACTUAL
            # recorded span (nsamp/fs == the decoder's Duration), so a PRO only "overlaps" if real
            # samples exist around it. When >=1 rating overlaps, emit a rating-CENTERED PSD per kept
            # rating (the fix for a mid-stream rating being un-matchable). When NONE overlaps -- the
            # common case for short ~30 s sessions, which almost never contain a rating -- FALL BACK
            # to the legacy first-window emission below (one PSD at t0) so the session can still match
            # a nearby rating via the tolerance window, exactly as it did before rating-centering.
            # Dropping it here is what greyed out every short-session TD lane.
            dur_s = nsamp / fs if fs > 0 else 0.0
            in_win = pt[(pt >= t0) & (pt <= t0 + dur_s)]
            emitted = False
            if in_win.size:
                centers_s = in_win - t0   # offsets from session start (s)
                try:
                    # Missing mask aligned to the TIME axis of `sig` (n_ch, n_samples). The decoder
                    # stores Missing as (n_samples,) or (n_samples, n_ch); collapse to a per-sample
                    # flag (any channel missing -> sample missing) so the centered Welch can reject
                    # windows dominated by FixBreaking zero-fill.
                    miss_vec = _missing_time_vector(r.get("Missing"), nsamp)
                    psd_k, used_k, kept = _sp.welch_rating_centered(
                        sig, keep_names, fs, keep_names, centers_s,
                        missing=miss_vec)  # (K,k,F),(K,),(len,)
                    kept_times = in_win[kept]   # PRO timestamps that produced a PSD
                    psd_k = np.asarray(psd_k)
                    for kk in range(psd_k.shape[0]):
                        tk = float(kept_times[kk]); dk = float(used_k[kk])
                        for j, n in enumerate(keep_names):
                            rows.append({"channel": _canon_channel(n), "source": source_label,
                                         "t": tk, "freq": _sp.F_SET, "power": psd_k[kk, j, :],
                                         "dur": dk})
                    emitted = psd_k.shape[0] > 0
                except Exception:
                    emitted = False
            if emitted:
                continue
            # else: no overlapping rating (or all dropped by the floor) -> fall through to first-window

        try:
            miss_vec = _missing_time_vector(r.get("Missing"), nsamp)
            psd = _sp.welch_psd_for_instance(sig, names, fs, keep_names,
                                             missing=miss_vec)  # (1, k, F)
        except Exception:
            continue
        psd = np.asarray(psd)
        # Missing-aware rejection: welch_psd_for_instance returns an all-NaN PSD when the first
        # `WELCH_MAX_SECONDS` window is more than WELCH_MAX_MISSING_FRAC zero-fill (e.g. a short
        # recording that a FixBreaking merge padded with a gap). Skip emitting a row for it rather
        # than storing a deflated spectrum; the rating then matches a cleaner montage/event PSD if
        # one is in window, exactly as an un-decodable recording would behave.
        if not np.isfinite(psd).any():
            continue
        # Duration (s) actually used by Welch for this recording = min(window, available). Reported
        # downstream as mean +/- SD so the clinician knows the TD epoch length feeding each PSD.
        used_dur = float(min(_sp.WELCH_MAX_SECONDS, nsamp / fs)) if fs > 0 else float("nan")
        for j, n in enumerate(keep_names):
            # Store the CANONICAL channel so ring-named survey rows pool with the short-named TD/Stim
            # rows for the same physical bipolar pair (e.g. ZERO_AND_THREE_LEFT_RING -> ZERO_THREE_LEFT).
            rows.append({"channel": _canon_channel(n), "source": source_label,
                         "t": float(t0), "freq": _sp.F_SET, "power": psd[0, j, :],
                         "dur": used_dur})


def _psd_sample_index(td_list, psd_list, pro_times=None):
    """Lightweight index of the scan's pooled-PSD samples: one entry per (recording, channel) the
    full-spectrum scan would include, WITHOUT the expensive Welch transform.

    Uses the IDENTICAL channel filter as `_assemble_psd_rows` (membership in `_MAIN_BIPOLAR`, same
    source labels), so the set of (t, channel, source) entries here equals the rows that feed the
    pooled PSD matrix — modulo the rare degenerate spectrum Welch drops (<4 finite bins), which
    effectively never occurs on real recordings. This lets the frontend replicate the backend's
    nearest-PRO match + binarization LIVE as the match-window slider moves, so the binarization
    histogram and the timeline coloring stay faithful to `matched_sample_counts` without a recompute.

    `pro_times` mirrors `_welch_rows_into`: when provided, TD-streaming entries become
    RATING-CENTERED — one entry per (overlapping PRO, channel), stamped at the PRO's own timestamp
    and gated by the same [t0, t0+dur] coverage + `WELCH_CENTERED_MIN_SECONDS` floor the Welch path
    uses. This keeps the live preview's match count IDENTICAL to the backend pool (a TD PRO inside
    coverage matches at offset 0; one near a session edge with < floor coverage is dropped, exactly
    as the spectra are). Montage/survey entries keep their start-time stamp regardless.

    Returns a list of {"t": epoch_s, "channel": "<CANON>_<HEMI>", "source": str}.
    """
    from .routines import streaming_psd as _sp
    out = []
    pt = np.asarray(pro_times, dtype=float) if pro_times is not None else None
    min_s = _sp.WELCH_CENTERED_MIN_SECONDS
    half_s = _sp.WELCH_MAX_SECONDS / 2.0

    def _index(recs, source_label, centered=False):
        # source_label may be a string (same for all recordings) OR a callable r -> str so a mixed
        # list (e.g. td_list = BrainSense streaming + Indefinite) is labeled per recording. This finer
        # provenance feeds the binarization-histogram hover's TD source breakdown.
        for r in recs or []:
            if not isinstance(r, dict):
                continue
            lbl = source_label(r) if callable(source_label) else source_label
            names = list(r.get("ChannelNames") or [])
            keep = [n for n in names if _canon_channel(n) in _MAIN_BIPOLAR]
            if not keep:
                continue
            t0 = availability._to_epoch(r.get("StartTime"))
            if t0 is None:
                continue
            emitted = False
            if centered and pt is not None:
                # Replicate welch_rating_centered's keep rule WITHOUT Welch'ing: a PRO inside
                # [t0, t0+dur] yields a window clipped to the session, kept iff its clipped length
                # >= min_s. Clipped length = min(t0+dur, pro+half) - max(t0, pro-half).
                data = np.asarray(r.get("Data"))
                if data.ndim == 2:
                    nsamp = data.shape[0] if data.shape[1] == len(names) else data.shape[1]
                    fs = float(r.get("SamplingRate") or 250.0)
                    dur_s = (nsamp / fs) if fs > 0 else 0.0
                    cand = pt[(pt >= t0) & (pt <= t0 + dur_s)]
                    if cand.size:
                        lo = np.maximum(t0, cand - half_s)
                        hi = np.minimum(t0 + dur_s, cand + half_s)
                        kept = cand[(hi - lo) >= min_s]
                        for tk in kept:
                            for n in keep:
                                out.append({"t": float(tk), "channel": _canon_channel(n),
                                            "source": lbl})
                        emitted = kept.size > 0
            if not emitted:
                # No rating overlaps this session's real coverage (or all dropped by the floor) ->
                # one entry at the session START, matched via the tolerance window downstream. This
                # MIRRORS the Welch fall-back in `_welch_rows_into`, so the live count == backend pool
                # for short sessions too (without it, every short-session TD lane greys out).
                for n in keep:
                    out.append({"t": float(t0), "channel": _canon_channel(n),
                                "source": lbl})

    # TD-streaming provenance: split BrainSense streaming vs Indefinite stream per recording so the
    # binarization hover can break the time-domain count down by source. The discriminator mirrors
    # _stamp_td_product (decoded payload carries Source=='indefinite' or an IndefiniteStream flag).
    def _td_label(r):
        if r.get("RecordingType") == "MedtronicIndefiniteStream" or r.get("Source") == "indefinite" or r.get("IndefiniteStream"):
            return "Indefinite stream"
        return "BrainSense streaming"
    _index(td_list, _td_label, centered=(pt is not None))
    _index(psd_list, "Montage")
    return out


def _biomarker_cache_base_dir():
    """The 'cache' directory itself -- parent of every ad hoc Biomarkers cache subdirectory that
    is not the one store (the per-recording spectrum cache and its small index files, decision
    51). The assembled matrix moved into the one store, decision 52, and no longer needs this."""
    try:
        from django.conf import settings
        base = getattr(settings, "DATASERVER_PATH", None) or os.environ.get("DATASERVER_PATH") or "/tmp/"
    except Exception:
        base = os.environ.get("DATASERVER_PATH") or "/tmp/"
    return os.path.join(base, "cache")


def _psd_rows_cache_dir():
    """Directory for the PER-RECORDING PSD-row cache (one .npz per recording instance).

    Distinct from the assembled matrix, which lives in the one store (`PSD_MATRIX_KIND`, decision
    52). The per-recording cache is keyed by the recording's DB identity (uid + hashed), BOTH of
    which are columns on the
    Recording row — so we can tell whether a recording's spectra are already cached WITHOUT opening
    its .bdat file. That is what lets the compute path skip the ~190 s cold decode of recordings it
    has already Welch'd: only the genuinely-new files are loaded.
    """
    base_dir = _biomarker_cache_base_dir()
    d = os.path.join(base_dir, "biomarker_psd_rows")
    os.makedirs(d, exist_ok=True)
    return d


def _psd_rows_index_dir():
    """Directory for the two small files that let `_assemble_psd_rows_cached` skip most of its own
    per-recording work: the manifest (which recordings this participant already has a valid
    per-recording file for) and the rows cache (the fully assembled row list for one exact
    recording set, so a request whose set has not moved skips the per-recording loop entirely).

    Distinct from `_psd_rows_cache_dir` (the per-recording files themselves) and the assembled
    matrix (which lives in the one store, `PSD_MATRIX_KIND`, decision 52). Neither of these two
    files replaces the per-recording cache; they only avoid re-deriving what it already tells us
    on every call.
    """
    base_dir = _biomarker_cache_base_dir()
    d = os.path.join(base_dir, "biomarker_psd_rows_index")
    os.makedirs(d, exist_ok=True)
    return d


def _rows_set_signature(entries, key_fn):
    """One short stamp for an entire recording set, from the per-recording cache key each entry
    resolves to -- so it already carries the recording's identity and content hash, the Welch
    window, the channel-canon and Missing-aware rule versions, and (for TD streaming) the PRO-set
    signature, with no extra work: these are exactly the same inputs `key_fn` already folds in.
    Order-independent, so the set is unchanged whether the ORM returns it in a different order.
    """
    import hashlib
    parts = sorted(os.path.basename(key_fn(e)) for e in entries)
    return hashlib.sha1("|".join(parts).encode("utf8")).hexdigest()[:16]


def _rows_manifest_path(participant_uid):
    return os.path.join(_psd_rows_index_dir(), f"manifest_{participant_uid}.json")


def _load_rows_manifest(participant_uid):
    """The per-recording cache keys already known to have a valid file on disk, or empty on a
    cold start, a corrupt file, or any read error -- the safe default is to fall back to checking
    every recording individually, exactly as before this manifest existed."""
    try:
        with open(_rows_manifest_path(participant_uid), "r", encoding="utf8") as fh:
            return set(json.load(fh).get("known_good", []))
    except Exception:
        return set()


def _save_rows_manifest(participant_uid, known_good):
    """Best-effort, like every other cache write in this module: two requests updating this
    participant's manifest at once can lose one's addition, but the per-recording file that
    addition refers to is already safely on disk (its own write is atomic), so the only cost of
    losing it is that one recording is checked again next time -- never a wrong answer."""
    path = _rows_manifest_path(participant_uid)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf8") as fh:
            json.dump({"known_good": sorted(known_good)}, fh)
        os.replace(tmp, path)
    except Exception as e:
        _log.warning("Biomarkers: PSD rows manifest write failed (%s)", e)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _rows_cache_path(participant_uid, rows_sig):
    return os.path.join(_psd_rows_index_dir(), f"rows_{participant_uid}_{rows_sig}.pkl")


def _load_rows_cache(participant_uid, rows_sig):
    """The fully assembled per-recording rows for this exact recording set, or None on a miss or
    any read error. Holds the rows BEFORE patient-event rows are appended: those are read fresh
    from the ORM on every call regardless, exactly as they always have been, because a new patient
    event is not a new recording and does not change `rows_sig`."""
    path = _rows_cache_path(participant_uid, rows_sig)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return pickle.load(fh)
    except Exception as e:
        _log.warning("Biomarkers: PSD rows-set cache read failed (%s); recomputing", e)
        return None


def _save_rows_cache(participant_uid, rows_sig, rows):
    path = _rows_cache_path(participant_uid, rows_sig)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as fh:
            pickle.dump(rows, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
        _sweep_old_rows_cache(participant_uid, rows_sig)
    except Exception as e:
        _log.warning("Biomarkers: PSD rows-set cache write failed (%s)", e)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _sweep_old_rows_cache(participant_uid, keep_sig):
    """Remove this participant's other rows-set entries once the new one has landed. Every new
    upload changes `rows_sig`, so without this the old entries would sit there forever -- the same
    reason `CacheStore._sweep_superseded` exists, at the same modest per-write cost (one directory
    listing, only on a write, never on a read)."""
    d = _psd_rows_index_dir()
    prefix = f"rows_{participant_uid}_"
    keep = os.path.basename(_rows_cache_path(participant_uid, keep_sig))
    try:
        names = os.listdir(d)
    except OSError:
        return
    for name in names:
        if name.startswith(prefix) and name != keep and not name.endswith(".tmp"):
            try:
                os.remove(os.path.join(d, name))
            except OSError:
                pass


def _pro_set_signature(pro_times):
    """Short, order-independent signature of the PRO timestamp SET feeding rating-centered TD PSDs.

    Rating-centered TD spectra depend on WHICH PROs exist (each PRO inside coverage emits a centered
    window), so the PRO set is part of the TD matrix CONTENT — exactly like WELCH_MAX_SECONDS or the
    channel-canon rule. Folding this into the TD cache keys means: add/remove/shift a PRO and the TD
    spectra are recomputed; leave the PROs unchanged and the cache serves the same centered rows.
    PROs are rounded to whole seconds (sub-second jitter never moves a 30 s window meaningfully) and
    sorted, so the signature is independent of row order. Returns "" for an empty/None set (the
    caller then uses the legacy first-window path, whose key carries no PRO component).
    """
    import hashlib
    if pro_times is None:
        return ""
    pt = np.asarray(pro_times, dtype=float)
    pt = pt[np.isfinite(pt)]
    if pt.size == 0:
        return ""
    pt = np.unique(np.round(pt).astype(np.int64))   # sorted + de-duped whole-second stamps
    return hashlib.sha1(pt.tobytes()).hexdigest()[:12]


def _recording_psd_cache_path(rec_uid, rec_hash, pro_sig=""):
    """Cache path for one recording's PSD rows. Keyed by uid + a short slice of the stored hash, so
    re-uploading the same data (new uid) or a content change (new hash) both miss and recompute.
    The Welch epoch length is also in the key: changing it produces different spectra, so the file
    name carries it (w<sec>) and a window change misses the old cache instead of serving stale PSDs."""
    from .routines import streaming_psd as _sp
    h = (str(rec_hash or "") or "nohash")[:16]
    w = str(_sp.WELCH_MAX_SECONDS).replace(".", "p")
    # Channel-canon rule is in the key too: a Survey recording previously cached with ZERO kept rows
    # (ring names dropped) must miss and re-Welch under the ring-aware rule instead of serving empty.
    # `pro_sig` (non-empty ONLY for rating-centered TD recordings) makes the PRO set part of the key,
    # so a TD recording's centered spectra are recomputed when the PROs change but a montage/survey
    # recording (pro_sig="") keeps a stable, PRO-independent cache entry.
    # `_TD_CENTERED_VERSION` rides along only for the rating-centered TD recordings (pro_sig set), so
    # a change to the centering/fall-back rule invalidates exactly those entries, not montage/survey.
    p = f"_p{pro_sig}_{_TD_CENTERED_VERSION}" if pro_sig else ""
    # `_TD_MISSING_VERSION` rides in the BASE key (unconditional): the Missing-aware rejection runs in
    # the first-window path too, which serves montage/survey/event recordings (pro_sig=""), so every
    # entry must invalidate when the rejection rule changes.
    return os.path.join(_psd_rows_cache_dir(),
                        f"{rec_uid}_{h}_w{w}_{_CHANNEL_CANON_VERSION}_{_TD_MISSING_VERSION}{p}.npz")


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


def _assemble_psd_rows_cached(participant_uid, pro_times=None, force_recompute=False):
    """Assemble the full PSD-row list for a participant using the per-recording cache, decoding +
    Welch'ing ONLY the recordings whose spectra are not already on disk.

    This is the load-skipping fast path behind `_cached_psd_matrix`: a participant whose recordings
    are all cached pays zero .bdat decodes (the ~190 s cold load disappears); a partially-warm
    participant pays only for the new files. The resulting rows are identical to
    `_assemble_psd_rows(td_list, psd_list)` because both go through `_welch_rows_into`.

    `pro_times`: when provided, TD-streaming recordings emit RATING-CENTERED rows (one per
    overlapping PRO, see `_welch_rows_into`); their cache entries are keyed by the PRO-set signature
    so a PRO change recomputes only the TD spectra. Montage/survey/event rows are PRO-independent and
    keep their stable cache entries.

    TWO SHORTCUTS SIT IN FRONT OF THE PER-RECORDING LOOP, NEITHER OF WHICH CAN SERVE A WRONG ANSWER.

    First, `_rows_set_signature` reduces this participant's whole recording set to one short stamp,
    and `_load_rows_cache` looks for the fully assembled rows already stored under that exact stamp.
    A hit means nothing about the recording set has moved since the last assembly, so the entire
    per-recording loop below is skipped. A participant asked about repeatedly with no new upload in
    between -- which is the common case for `band_psd_lsb_conversion`, a call site with no matrix-
    level cache in front of it at all -- pays for the per-recording loop once and then not again.

    Second, on a stamp miss, `_load_rows_manifest` reads one small saved list, once, naming which
    recordings are already known to have a good file -- for those, the file is opened straight
    away with no existence check first. A recording NOT on that list is not assumed missing: it is
    checked the way every recording always was, and being found there repairs the list for next
    time. So an empty or stale manifest, including the very first run after this manifest existed
    at all, costs at most the existence check this function has always made -- never a redecode of
    a recording whose file was already on disk, and never a wrong or missing recording.

    Returns (rows, n_cached, n_computed) — the row counts let callers log/verify the cache hit rate.
    """
    from .routines import streaming_psd as _sp
    entries = _recording_rows_for_psd(participant_uid)
    if not entries:
        return [], 0, 0

    pro_sig = _pro_set_signature(pro_times) if pro_times is not None else ""

    def _key_for(e):
        # Only TD-streaming recordings carry the PRO signature in their key (their spectra are
        # rating-centered); montage/survey stay PRO-independent so their cache is never invalidated
        # by a PRO edit.
        sig = pro_sig if (pro_sig and e["source"] == "TD streaming") else ""
        return _recording_psd_cache_path(e["uid"], e["hash"], sig)

    rows_sig = _rows_set_signature(entries, _key_for)
    rows = None if force_recompute else _load_rows_cache(participant_uid, rows_sig)
    if rows is not None:
        n_cached, n_computed = len(entries), 0
    else:
        known_good = set() if force_recompute else _load_rows_manifest(participant_uid)
        manifest_changed = False
        rows = []
        n_cached = 0
        missing = []   # entries needing a decode+Welch
        for e in entries:
            path = _key_for(e)
            name = os.path.basename(path)
            cached = None
            # force_recompute ignores the on-disk spectra so every recording is decoded and Welch'd
            # again. The rebuilt rows are still written back, so this is a one-off cost.
            if not force_recompute:
                if name in known_good:
                    # The manifest says this file is good: skip the existence check and open it
                    # directly. If the manifest was wrong, the load itself catches that below.
                    cached = _load_recording_psd_rows(path)
                    if cached is None:
                        known_good.discard(name)
                        manifest_changed = True
                elif os.path.exists(path):
                    # NOT IN THE MANIFEST IS NOT THE SAME AS MISSING. A file already on disk from
                    # before this manifest existed, or from a manifest write that was lost to a
                    # concurrent request, is still found here exactly as it always was; finding it
                    # also repairs the manifest, so this fallback is paid at most once per file.
                    cached = _load_recording_psd_rows(path)
                    if cached is not None:
                        known_good.add(name)
                        manifest_changed = True
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
                dicts = [d for d in (data if isinstance(data, list) else [data])
                         if isinstance(d, dict)]
                return e, dicts

            workers = max(1, min(len(missing), _loader_threads()))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for e, dicts in pool.map(_decode, missing):
                    rec_rows = []
                    if dicts:
                        # TD streaming gets rating-centered rows when pro_times is provided; other
                        # sources ignore it (pass None so they keep the first-window behavior).
                        _pt = (pro_times if (pro_times is not None and e["source"] == "TD streaming")
                               else None)
                        _welch_rows_into(rec_rows, dicts, e["source"], _sp, pro_times=_pt)
                    rows.extend(rec_rows)
                    n_computed += 1
                    # Persist this recording's rows (even if empty) so it is never re-decoded.
                    try:
                        _save_recording_psd_rows(_key_for(e), rec_rows)
                        known_good.add(os.path.basename(_key_for(e)))
                        manifest_changed = True
                    except Exception as ex:
                        _log.warning("Biomarkers: per-recording PSD cache write failed (%s)", ex)

        if manifest_changed:
            _save_rows_manifest(participant_uid, known_good)
        _save_rows_cache(participant_uid, rows_sig, rows)

    # Patient-event PSDs (incl. Streaming markers): read off ORM metadata, no decode/Welch, so they
    # need no per-recording cache and are never part of the rows-set stamp above. Appended on every
    # assembly, cache hit or miss alike — a new patient event is not a new recording, so it must be
    # picked up even when the recording set (and therefore `rows_sig`) has not moved at all.
    # Build the sensing index from the already-computed TD rows so event blocks with no SenseID
    # get their contact pair from the actual per-timestamp sensing config.
    try:
        _ev_idx = _build_sensing_config_index_from_rows(rows)
        ev_rows = _event_psd_rows(participant_uid, sensing_index=_ev_idx)
        rows = rows + ev_rows
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


def _psd_matrix_signature_orm(participant_uid, pro_times=None):
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
    # Missing-aware TD Welch rejection is part of the matrix CONTENT (it decides which windows yield a
    # spectrum), and it runs in the first-window path too, so fold it in unconditionally.
    parts.append(f"td_missing:{_TD_MISSING_VERSION}")
    # Rating-centered TD spectra depend on the PRO set, so it is part of the matrix CONTENT: fold the
    # PRO-set signature in (empty when pro_times is None -> the legacy first-window matrix key, fully
    # back-compatible). A PRO add/remove/shift changes this and re-Welch's the TD rows; montage/event
    # rows are PRO-independent and reused from their own per-recording cache regardless.
    _pro_sig = _pro_set_signature(pro_times) if pro_times is not None else ""
    if _pro_sig:
        parts.append(f"pro_centered:{_pro_sig}:{_TD_CENTERED_VERSION}")
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


def _normalize_force_refresh(value):
    """Normalize a request's ForceRefresh into None | "matrix" | "all".

    Accepts what a JSON client plausibly sends: absent/None/False/""/"0"/"false"/"none" -> None;
    True/"1"/"true"/"yes"/"matrix" -> "matrix" (rebuild the assembled matrix, seconds);
    "all"/"full"/"recompute"/"hard" -> "all" (also re-decode and re-Welch every recording, minutes).

    Anything unrecognised maps to None rather than raising, and deliberately so: an unrecognised
    value must never silently trigger the expensive path, and a typo in a query parameter should not
    500 a panel that is otherwise fine.
    """
    if value is None or value is False:
        return None
    if value is True:
        return "matrix"
    v = str(value).strip().lower()
    if v in ("", "0", "false", "no", "none", "off"):
        return None
    if v in ("all", "full", "recompute", "hard", "2"):
        return "all"
    if v in ("1", "true", "yes", "on", "matrix", "matrix_only"):
        return "matrix"
    return None


#: The assembled matrix's kind name in the one store (decision 52, Track E revised). Raw: it is a
#: deterministic decode-and-Welch of the device's own recordings, with no other module's choices
#: baked in, the same reasoning that makes the tile cache raw.
PSD_MATRIX_KIND = "biomarker_psd_matrix"


def _psd_matrix_payload(mat):
    """`psd_rows_to_matrix`'s dict, as the plain array bundle the store writes -- same fields, same
    dtypes, as the on-disk npz this replaces, so an entry already on disk in the old ad hoc
    directory and one written through the store are byte-for-byte the same shape."""
    out = dict(logX=mat["logX"], t=mat["t"],
              channel=np.asarray(mat["channel"], dtype=str),
              source=np.asarray(mat["source"], dtype=str), f_set=mat["f_set"])
    if mat.get("dur") is not None:
        out["dur"] = np.asarray(mat["dur"], dtype=float)
    return out


def _cached_psd_matrix(participant_uid, td_list=None, psd_list=None, pro_times=None,
                       force_refresh=None):
    """Load the per-channel PSD matrix for this participant from disk, or build it and persist it.

    Two-level cache:
      1. Assembled-matrix npz, keyed by participant + an ORM-derived content signature
         (`_psd_matrix_signature_orm`). A hit returns the matrix with ZERO file decodes.
      2. On a matrix miss, assemble via `_assemble_psd_rows_cached`, which decodes + Welch's ONLY
         the recordings whose per-recording spectra are not already cached. So ingesting one new
         file re-Welch's just that file (not all ~330), and the cold ~190 s load disappears once the
         per-recording cache is warm.

    `pro_times`: when provided (UTC epoch s), TD-streaming PSDs are RATING-CENTERED on the PROs and
    the cache keys fold in the PRO-set signature, so the matrix is recomputed iff the PROs change.
    When None (default), the legacy first-window behavior and keys apply — fully back-compatible, so
    callers that don't pass PROs (e.g. `warm_psd_cache` at ingestion) build the same matrix as before.

    `td_list`/`psd_list` are accepted for call-site back-compat but no longer needed (the assembly
    is keyed off the DB). Returns the `psd_rows_to_matrix` dict (or None if no PSDs).

    `force_refresh`: None/False = normal cached behaviour. "matrix" ignores the assembled-matrix npz
    and reassembles from the per-recording spectra (seconds). "all" additionally ignores the
    per-recording spectra, forcing a decode + Welch of every recording (minutes). A refresh still
    WRITES the rebuilt caches, so the next request is fast again. See `_normalize_force_refresh`.
    """
    from .routines import streaming_psd as _sp
    # FORCE REFRESH (2026-08-30). Until now there was no bypass at all: if this cache ever DID go
    # stale there was no way to rebuild from the UI, which is why the original "plot not updating"
    # complaint had no diagnostic path — even though the real cause turned out to be that the new
    # device files had never been ingested. Closing the hole so the next such report is answerable.
    _fr = _normalize_force_refresh(force_refresh)
    if _fr:
        _log.info("Biomarkers: force_refresh=%r — bypassing %s cache for %s", _fr,
                  "matrix + per-recording" if _fr == "all" else "matrix", participant_uid)
    sig, _entries = _psd_matrix_signature_orm(participant_uid, pro_times=pro_times)
    if not _fr:
        cached = _cache_store.load(PSD_MATRIX_KIND, participant_uid, sig)
        if cached is not None:
            return cached

    rows, n_cached, n_computed = _assemble_psd_rows_cached(
        participant_uid, pro_times=pro_times, force_recompute=(_fr == "all"))
    if n_computed or n_cached:
        _log.info("Biomarkers: PSD rows assembled for %s — %d from per-recording cache, %d Welch'd",
                  participant_uid, n_cached, n_computed)
    mat = _sp.psd_rows_to_matrix(rows)
    if mat is None:
        return None
    payload = _psd_matrix_payload(mat)
    if not _cache_store.store(PSD_MATRIX_KIND, participant_uid, sig, payload,
                              writer="biomarkers", trigger="biomarker_page",
                              n_recordings=len(_entries)):
        _log.warning("Biomarkers: PSD matrix cache write did not land for %s", participant_uid)
    return payload


def warm_psd_cache(participant_uid, pro_times=None, decoded_td=None, decoded_psd=None):
    """Build/refresh the per-recording PSD cache (and the assembled matrix) for a participant.

    Safe to call off the request thread or from ingestion: decodes + Welch's only the recordings not
    already cached, persists each, and writes the assembled-matrix npz. Idempotent and non-fatal.

    `pro_times`: when provided (the metric-agnostic `_all_pro_times` set), the warmed matrix is
    RATING-CENTERED and keyed by that PRO set — so the eager warm and the later scan/validation
    requests (which pass the SAME set) hit the identical cache entry. This is what keeps the
    expensive decode+Welch off the request thread: the centered matrix is already on disk by the time
    the user clicks "Start exploratory analysis". When None, the legacy first-window matrix is warmed.

    `decoded_td`/`decoded_psd`: the recordings ALREADY decoded by the timeline request (lists of
    dicts with "Data"). When supplied AND the matrix is not already cached, the centered matrix is
    built straight from these in-memory signals — NO second decode pass. This is the fix for the
    "90% CPU across all cores" stall: without it the warm re-decodes every .bdat from the DB through
    its own 16-worker pool, duplicating the decode the timeline render just paid and starving the
    foreground render. With it, the eager warm Welch's the already-decoded data and only writes caches.

    THE 3 s-TILE CACHE IS WARMED HERE TOO, which is what wires it into ingestion. This function is
    called from exactly two places, both of them off the request thread: the end of
    `DataCurator.MedtronicPerceptJSONDecoder`, in a daemon thread, once the newly uploaded
    recordings have been committed; and `_PSD_WARM_POOL`, the single background thread the timeline
    fires. So the tiles for a participant who has just had a file uploaded are built before anyone
    asks for them, and the FIRST page view after an upload is fast rather than the second. It costs
    0.43 s on a participant whose tiles are already there (the key only — no stored file is opened
    and no tile is computed), and it cannot raise: see `warm_shared_raw_cache`.
    """
    out = None
    try:
        if (decoded_td is not None or decoded_psd is not None) and pro_times is not None:
            out = _warm_centered_matrix_from_decoded(
                participant_uid, decoded_td or [], decoded_psd or [], pro_times)
        else:
            out = _cached_psd_matrix(participant_uid, pro_times=pro_times)
    except Exception as e:
        _log.warning("Biomarkers: warm_psd_cache failed for %s (%s)", participant_uid, e)
    # The two products are independent, so the tiles are warmed even when the spectra above failed.
    tiles = warm_shared_raw_cache(participant_uid)
    if tiles.get("status") == "built":
        _log.info("Biomarkers: built the shared 3 s-tile cache for %s in %.1f s after an ingest "
                  "or a timeline render", participant_uid, tiles.get("seconds", float("nan")))
    return out


def _warm_centered_matrix_from_decoded(participant_uid, td_list, psd_list, pro_times):
    """Build + persist the rating-centered PSD matrix from ALREADY-DECODED recordings — no ORM decode.

    Mirrors `_cached_psd_matrix`'s matrix-cache contract (same signature key, same npz schema incl.
    `dur`), but assembles rows from the in-memory `td_list`/`psd_list` the timeline request already
    decoded, so the expensive .bdat decode is paid exactly once per page load instead of twice. If the
    matrix is already cached (warm), it is loaded and returned without re-Welch'ing. The per-recording
    row cache is intentionally NOT written here (that path serves incremental ingestion, keyed off the
    DB); the matrix cache is what the scan/validation requests read.
    """
    from .routines import streaming_psd as _sp
    sig, _entries = _psd_matrix_signature_orm(participant_uid, pro_times=pro_times)
    cached = _cache_store.load(PSD_MATRIX_KIND, participant_uid, sig)
    if cached is not None:
        return cached

    rows = []
    # TD streaming -> rating-centered rows; montage/survey -> first-window rows (PRO-agnostic).
    _welch_rows_into(rows, td_list, "TD streaming", _sp, pro_times=pro_times)
    _welch_rows_into(rows, psd_list, "Montage/survey", _sp)
    try:
        _ev_idx = _build_sensing_config_index(list(td_list or []))  # td only; psd_list = sweeps
        rows.extend(_event_psd_rows(participant_uid, sensing_index=_ev_idx))
    except Exception:
        pass
    mat = _sp.psd_rows_to_matrix(rows)
    if mat is None:
        return None
    payload = _psd_matrix_payload(mat)
    if not _cache_store.store(PSD_MATRIX_KIND, participant_uid, sig, payload,
                              writer="biomarkers", trigger="timeline_render",
                              n_recordings=len(_entries)):
        _log.warning("Biomarkers: PSD matrix cache write (from decoded) did not land for %s",
                     participant_uid)
    return payload


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


def _redcap_narrow_pull_enabled():
    """Whether to request only the columns the patient field map consumes (the default).

    Set BRAVO_REDCAP_NARROW_PULL=0 to send the full-project export request instead. This is a
    switch for a REDCap-side surprise, NOT a freshness switch: both settings go to the server on
    every request and neither can return a report that is out of date.
    """
    return str(os.environ.get("BRAVO_REDCAP_NARROW_PULL", "1")).strip().lower() not in (
        "0", "false", "no", "off")


# WITHIN ONE REQUEST ONLY. This holds the pain reports already fetched during the request being
# served, so a request whose panels ask for them twice fetches them once. It is a ContextVar set
# and cleared by `_pro_scoped` around each endpoint, so it cannot outlive the request that filled
# it and therefore cannot serve a report set that is missing a newly filed report. THERE IS NO
# CROSS-REQUEST CACHE HERE, DELIBERATELY -- see the note on `_pro_scoped`.
_PRO_REQUEST_CACHE = _contextvars.ContextVar("bravo_pro_request_cache", default=None)


@_contextlib.contextmanager
def pro_request_scope():
    """Open the within-request pain-report scope; reentrant, so nesting shares the outer scope.

    NO CROSS-REQUEST CACHE IS BUILT, ON PURPOSE. Patients and clinicians file pain reports
    continuously, so a cache that outlived a request would eventually hand a biomarker analysis a
    report set that is one report short, with no error to show for it. Measured on the live record,
    a cross-request cache could not pay for itself either. The cheapest check that could prove a
    remembered report set still complete is REDCap's own record-edit log,
    `export_logging(log_type="record", begin_time=...)`. On the live RCS08 record that check and
    an outright fresh fetch of the reports, narrowed to the columns the field map consumes, cost
    the same to within the run-to-run scatter of the network -- both a few tenths of a second. So a
    cross-request cache would buy nothing and could hand back a pain-report table one report short.
    That trade is not worth taking. `_agent_bridge/_sync_redcap/_rc_probe2.py` is the script that
    times both; re-run it for current numbers rather than trusting a figure quoted here, since they
    move with the network.
    """
    existing = _PRO_REQUEST_CACHE.get()
    if existing is not None:
        yield existing
        return
    token = _PRO_REQUEST_CACHE.set({})
    try:
        yield _PRO_REQUEST_CACHE.get()
    finally:
        _PRO_REQUEST_CACHE.reset(token)


def _pro_scoped(fn):
    """Run one endpoint inside `pro_request_scope`."""
    @_functools.wraps(fn)
    def inner(*args, **kwargs):
        with pro_request_scope():
            return fn(*args, **kwargs)
    return inner


def _pro_scope_key(request_data, participant):
    """Identity of a pain-report fetch inside one request: everything `_load_pros_raw` reads.

    Returns None when the fetch must not be shared (an inline `ProcessedPRO` is already in memory,
    so there is nothing to save by remembering it).
    """
    if request_data.get("ProcessedPRO"):
        return None
    field_map = _resolve_field_map(request_data, participant)
    try:
        fm = json.dumps(field_map, sort_keys=True, default=str) if field_map else None
    except Exception:
        return None
    return (str(request_data.get("RedcapRecordId")), str(request_data.get("PtConfig")),
            str(getattr(participant, "uid", None) or getattr(participant, "name", None)), fm)


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

    Inside `pro_request_scope` the answer is remembered FOR THAT REQUEST ONLY, so a request that
    asks twice fetches once. A hit hands back its own copy, so one panel adding a column cannot
    disturb another.
    """
    cache = _PRO_REQUEST_CACHE.get()
    key = _pro_scope_key(request_data, participant) if cache is not None else None
    if key is not None and key in cache:
        got = cache[key]
        return got.copy() if got is not None else None
    df = _normalize_pro_times(_load_pros_raw(request_data, participant))
    if df is not None and not request_data.get("ProcessedPRO"):
        _snapshot_pain_reports(df, request_data, participant)
    # A REAL fetch just happened, so it becomes the table the read-only drill-downs ride on until
    # the next real fetch replaces it. See `_PRO_BUILD_CACHE`'s own note: this is the whole of the
    # invalidation rule -- every endpoint that BUILDS something still fetches fresh right here, and
    # by doing so re-seeds what the drill-downs see.
    _remember_pain_reports(request_data, participant, df)
    if key is not None:
        cache[key] = df.copy() if df is not None else None
    return df


#: ==========================================================================================
#: THE PAIN-REPORT SNAPSHOT. Written after every fresh fetch from REDCap; READ BY NO PAGE.
#:
#: Decision 22 stands: the pain reports are fetched fresh on every request, because the cheapest
#: check that could prove a remembered report set still complete costs the same as the fetch. What
#: is written here is not a cache and nothing above ever reads it back to answer a request. It is
#: the exact tidy table a request used, kept so that a result computed on a given day can name the
#: report set it was computed from. The stored copy buys reproducibility, not speed.
#:
#: THE KEY IS THE CONTENT OF THE TABLE, so the same report set writes exactly once however many
#: requests fetch it, and a newly filed report writes a new entry. The store keeps this kind's
#: history rather than sweeping it (`KEEP_HISTORY_KINDS`), because a swept snapshot would leave
#: the ledger row and not the table. Every product derived from the reports cites the snapshot's
#: key in its provenance, which is how the refusal in the store can tell a product built from
#: device recordings and reports (raw inputs) from one built from another module's choices.
#: ==========================================================================================
_REDCAP_SNAPSHOT_KIND = "redcap_reports"

#: Bumped when the shape of the tidy table changes in a way the columns alone do not capture.
_REDCAP_SNAPSHOT_RULE_VERSION = "v1_tidy_utc"

#: The name under which a frame carries the key of the entry it was snapshotted as. `DataFrame`
#: attributes survive `copy()`, column selection and the within-request copy above, so a consumer
#: holding any descendant of the fetched table can still cite it.
PRO_STORE_KEY_ATTR = _cache_store.STORE_KEY_ATTR


def _pro_table_digest(df):
    """A content hash of the tidy table: every value, every column name, in order.

    `hash_pandas_object` is deterministic across processes (it uses a fixed hash key), so four
    workers fetching the same report set agree on the digest and only the first one writes.
    """
    import hashlib
    h = hashlib.blake2b(digest_size=16)
    h.update(repr(list(map(str, df.columns))).encode("utf8"))
    h.update(str(len(df)).encode("ascii"))
    try:
        rows = pd.util.hash_pandas_object(df, index=False).to_numpy()
        h.update(rows.tobytes())
    except Exception:
        # A frame that cannot be hashed value-wise (an unhashable object column) still gets a
        # stable digest from its printed form, so the snapshot is written rather than skipped.
        h.update(df.to_csv(index=False).encode("utf8"))
    return h.hexdigest()


def _pro_participant_uid(request_data, participant):
    uid = getattr(participant, "uid", None) if participant is not None else None
    return str(uid or request_data.get("ParticipantId") or "shared")


def _snapshot_pain_reports(df, request_data, participant):
    """Write the fetched report table to the store if this exact table is not there already.

    Returns the product key, and records it on the frame under `PRO_STORE_KEY_ATTR`. Every
    failure is logged and swallowed: a snapshot that cannot be written must never be the reason a
    clinician's page fails, and the fresh table is already in hand.
    """
    try:
        if df is None or len(df) == 0:
            return None
        uid = _pro_participant_uid(request_data, participant)
        # THE KEY IS THE TABLE, NOT HOW IT WAS ASKED FOR. The record identifier and the field map
        # are recorded in the stamp, not the key: the same 760-row table requested two ways is one
        # report set, and two entries for it would tell an audit nothing.
        signature = (_REDCAP_SNAPSHOT_KIND, _REDCAP_SNAPSHOT_RULE_VERSION, uid,
                     _pro_table_digest(df))
        key = _cache_store.product_key(_REDCAP_SNAPSHOT_KIND, uid, signature)
        df.attrs[PRO_STORE_KEY_ATTR] = key
        field_map = _resolve_field_map(request_data, participant)
        try:
            fm = json.loads(json.dumps(field_map, default=str)) if field_map else None
        except Exception:
            fm = None
        # `store_if_absent` reads first, and a read with no consumer applies no refusal. The read
        # is only the existence check that makes the key decide; NOTHING RETURNED HERE IS USED TO
        # ANSWER THE REQUEST -- `df` is the table just fetched, and it is what the caller gets.
        _cache_store.store_if_absent(
            _REDCAP_SNAPSHOT_KIND, uid, signature, lambda: df,
            writer="biomarkers", trigger="fresh_fetch", provenance=[],
            extra={"n_reports": int(len(df)), "columns": [str(c) for c in df.columns],
                   "redcap_record_id": (str(request_data.get("RedcapRecordId"))
                                        if request_data.get("RedcapRecordId") is not None
                                        else None),
                   "field_map": fm},
            root=_SHARED_CACHE_DIR_OVERRIDE)
        return key
    except Exception as exc:
        _log.info("Biomarkers: the pain-report snapshot was not written (%r)", exc)
        return None


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
        field_map = _resolve_field_map(request_data, participant)
        if field_map:
            # ASK REDCAP FOR LESS, DO NOT REMEMBER ANYTHING. Every request still goes to the
            # server, so a pain report filed a second ago is in the answer; the only change is
            # that we request the 24 columns of this participant's daily pain survey instead of
            # all 637 columns of every participant. Measured on the live RCS08 record: 1.386 s
            # for the full export against 0.292 s for the narrowed one, producing a pain-report
            # table with the same 760 rows, the same columns and zero differing cells.
            fields, records = redcap_client.redcap_fields_for_field_map(field_map)
            df = None
            if fields and _redcap_narrow_pull_enabled():
                try:
                    df = redcap_client.pull_redcap(fields=fields, records=records)
                    # A patient field map whose timestamp column is a survey-generated field
                    # cannot be requested by name. If the narrowed export came back without the
                    # column `process_redcap` needs, fall back to the full export rather than
                    # let the pain reports come out short or raise at the caller.
                    if field_map.get("timestamp_label") not in getattr(df, "columns", []):
                        _log.warning(
                            "Biomarkers: the narrowed REDCap request did not return the report "
                            "timestamp column %r, so the full export is being used instead.",
                            field_map.get("timestamp_label"))
                        df = None
                except Exception as e:
                    _log.warning("Biomarkers: the narrowed REDCap request failed (%s); falling "
                                 "back to the full export.", e, exc_info=True)
                    df = None
            if df is None:
                df = redcap_client.pull_redcap()  # token via env vars
            return redcap_client.process_redcap(df, field_map)
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
                       match_direction="prior",
                       outlier_n_mad=None, outlier_scale=None):
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
                # `spectral_feature_importance` (the exploratory 5 Hz sliding-band scan) is no longer
                # computed: its only frontend consumer, BiomarkerAnalytics.js's scatter+violin
                # drill-down, was removed as an unnecessary duplicated analysis -- the calibrated
                # band-by-length grid (band_time_sweep_for_participant) is the headline result and
                # already covers the same question with a stronger correction. `_live_pro_lsb_spectrum`
                # above is still called, but with `return_spectra=False` -- only `live_match_stats`,
                # which the matching-controls caption still reads, is built; the per-PRO spectrum
                # records nothing here ever consumed are no longer computed at all.
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
    # Resolution-independent ns epoch (Series.view is deprecated/removed in pandas 3.0; a bare
    # .astype("int64") would give microseconds under pandas 3.0's datetime64[us] default).
    t_ep = (ts[ok].to_numpy().astype("datetime64[ns]").astype("int64") / 1e9)
    return t_ep, val[ok].to_numpy(dtype=float)


def _all_pro_times(pro_df):
    """Every parseable PRO timestamp (UTC epoch s), INDEPENDENT of any metric — sorted, de-duped.

    This is the PRO set the rating-centered TD matrix is built on. It is deliberately metric-agnostic
    so the matrix cache key is STABLE when the user switches the displayed metric (vas <-> mpq <-> ...):
    a TD window centered on a PRO timestamp is the same regardless of which metric that PRO carries,
    and the per-metric matching (which drops PROs lacking a finite value for the chosen metric) stays
    downstream in `build_pooled_detail_from_matrix`. Using the metric-FILTERED set here instead would
    re-key — and thus re-Welch — the whole matrix on every metric switch. Returns None if unavailable.
    """
    if pro_df is None or len(pro_df) == 0 \
            or (_PRO_TIME_COL not in pro_df.columns and _PRO_TIME_UTC_COL not in pro_df.columns):
        return None
    ts = _pro_times_utc_series(pro_df)
    ts = ts[ts.notna()]
    if ts.empty:
        return None
    # Resolution-independent ns epoch (see _metric_pro_series above).
    t_ep = ts.to_numpy().astype("datetime64[ns]").astype("int64") / 1e9
    return np.unique(t_ep)   # sorted + de-duped


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


def _native_lsb_tolerance_param(request_data):
    """Resolve the timeline's per-PRO native-LSB match window (seconds) from the request.

    This is `availability.per_pro_lsb`'s own tolerance -- how far from a pain report's timestamp a
    device-sensed reading may sit and still set that rating's timeline circle. Was a Python default
    with no request path at all (hardcoded 120 s, decision 73/76's shared-matching-layer work);
    reading it here, with the same default, is what makes it reachable from a knob rather than
    fixed. `NativeLsbToleranceSec` absent or non-numeric keeps the historical default so nothing
    already computed changes unless a caller deliberately sets it.
    """
    return _float_param(request_data, "NativeLsbToleranceSec", default=120.0, lo=1.0, hi=3600.0)


def _window_params_body(request_data, sliding):

    train_days, window_months = _months_to_days(request_data.get("WindowMonths"))
    step_days, window_step_months = _months_to_days(request_data.get("WindowStep"))
    return train_days, step_days, sliding, window_months, window_step_months


def _build_availability(participant_uid, *, chronic_list, powerdomain_list, td_list,
                        pro_df, label_metric, region_map, warm=False, native_lsb_tolerance_s=120.0,
                        psd_list=None):
    """Assemble the data-availability-timeline payload for the new BiomarkerDataTimeline component.

    Reuses recordings already loaded for the decoder (td/chronic/powerdomain) and additionally loads
    the PSD-bearing montage/survey products (which the decoder doesn't use). Returns:
        {records, pain, stim, freq_bands, span}
    where `records` are per-channel availability records, `pain`/`stim` are the shared-axis series,
    `freq_bands` are the categorical legend bands actually present, and `span` is [min_t, max_t].
    Guarded so any failure yields an empty payload rather than breaking the main timeline response.

    `psd_list`, when the caller already loaded `AVAILABILITY_PSD_TYPES` for this exact
    participant this request (run_for_participant does, for its own live-matching scan), is used
    as-is instead of reloading -- one fewer disk-read/decompress/unpickle pass over the same files.
    Left `None` (the default), this loads it itself exactly as before. Only this one load is reused
    across the two call sites: the sensing-config index built a few lines below intentionally
    differs between callers (this function always includes `powerdomain_list`;
    run_for_participant's own scan index does not), so it is NOT threaded through here -- doing so
    would change this function's own output instead of merely reusing already-equal work.
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
            (ind if (r.get("RecordingType") == "MedtronicIndefiniteStream" or r.get("Source") == "indefinite" or r.get("IndefiniteStream")) else bs).append(r)
        if psd_list is None:
            psd_list = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
        recs_by_type = {
            "MedtronicBrainSenseTimeDomain": bs,
            "MedtronicIndefiniteStream": ind,
            "MedtronicChronicBrainSense": list(chronic_list or []),
            "MedtronicBrainSensePowerDomain": list(powerdomain_list or []),
            "MedtronicBaselineMontages": [r for r in (psd_list or []) if isinstance(r, dict)],
        }
        records = availability.extract_availability(recs_by_type, region_map=region_map)
        # Build the active-sensing config index from already-decoded single-channel records
        # (BrainSenseTimeDomain + PowerDomain). Used by the event-PSD channel resolver so that
        # the 84% of event blocks with no SenseID get their contact pair from the device's actual
        # sensing config at press time, rather than a static per-hemisphere guess. Built once here
        # and reused by _event_psd_index, _event_psd_lsb_blocks, and the scan pool below.
        _sensing_idx = _build_sensing_config_index(
            list(td_list or []) + list(powerdomain_list or []))
        # Patient-event PSDs (incl. 'Streaming') are imported into the per-channel scan pool, so they
        # must also render as PSD TICKS on their contact lanes (DESIGN: "a PSD mark at those
        # contacts"). Append one synthetic dtype="psd" record per (event, hemisphere block) on its
        # assigned bipolar channel — same record schema extract_availability emits, product tagged
        # "patient_event" so the lane draws them as ticks alongside montage/survey PSDs.
        try:
            for ev in _event_psd_index(participant_uid, sensing_index=_sensing_idx):
                ch = ev["channel"]
                fmt = availability.analytics.format_channel(ch, region=region_map.get(ch))
                records.append({
                    "channel": ch, "label": fmt.get("short", ch),
                    "hemisphere": availability._hemisphere(ch),
                    "dtype": "psd", "product": "patient_event",
                    "event_name": ev.get("name", "Event"),   # the marker's own name (e.g. "Streaming");
                                                             # the lane tick keys on product/event_name
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
        #
        # MODELED fallback (psd_modeled tier): the MONTAGE SURVEY is the device-blessed
        # modeled source — it sweeps ALL bipolar contacts STIM-OFF, carries raw 250 Hz TD (in
        # Recording["Data"]) AND the device's own per-contact peak frequency (Descriptor.MedtronicPSD),
        # but produces NO native device LSB scalar. So those contacts have no LSB point without this:
        # convert via the transform DSP -> td_to_lsb (k=352.62, CS-1 2026-06-27; was Welch-256 ->
        # psd_band_to_lsb k=269) at each contact's configured sensing center (falling back to the
        # device peak). `psd_list` is the montage/survey products
        # (MedtronicBrainSenseSurvey + Baseline/Stimulation montages), all carrying TD. Tagged
        # source="psd_modeled" so the frontend draws it with a distinct hollow marker; NEVER preferred
        # over a sensed value. Deployment threshold is unaffected (stays native/frozen) — exploratory
        # timeline display only. (Montage TD is already ingested under MedtronicBrainSenseSurvey; this
        # is what surfaces it on the timeline.)
        sensing_hz = availability.analytics.power_center_freqs(powerdomain_list)
        # CS-3 PSD->LSB bridge: PSD-only patient-triggered snapshot events (no TD) -> modeled LSB.
        # Montage/survey (psd_list) carry TD and go through montage_td_recordings above; this is the
        # exclusive consumer of the bridge.
        event_psd_blocks = _event_psd_lsb_blocks(participant_uid, sensing_hz_by_channel=sensing_hz,
                                                  sensing_index=_sensing_idx)
        lsb = availability.lsb_series(chronic_list, powerdomain_list, region_map=region_map,
                                      montage_td_recordings=psd_list,
                                      sensing_hz_by_channel=sensing_hz,
                                      event_psd_recordings=event_psd_blocks)
        # Compact the per-sample LSB into render-cheap geometry (chronic line + per-session blocks)
        # so the calendar-scale timeline stays responsive while zooming; the frontend draws this.
        lsb_overview = availability.lsb_overview(lsb)
        # CS-4 per-PRO LSB SELECTION: one LSB per pain rating per channel, chosen by the strict source
        # precedence (native sensed > direct TD->LSB transform > PSD-only-event bridge), each tagged
        # with its tier + saturation flag so the timeline can colour each rating's biomarker point by
        # trust. TD-bearing recordings for tier 2 = streaming TD (td_list) + montage/survey TD
        # (psd_list, all 250 Hz TD); the PSD-only event bridge is tier 3 (event_psd_blocks).
        _pro_t_lsb = np.asarray(pain.get("t") or [], dtype=float) if isinstance(pain, dict) else None
        pro_lsb = _pro_lsb_by_channel(
            _pro_t_lsb, lsb, list(td_list or []) + list(psd_list or []),
            event_psd_blocks, sensing_hz, native_tol_s=native_lsb_tolerance_s
        ) if (_pro_t_lsb is not None and _pro_t_lsb.size) else {}
        bands = availability.present_freq_bands(records)
        # Patient-triggered events. _load_patient_events returns BOTH the labeled button presses
        # (category=DISPLAY_PATIENT_EVENT) AND the auto 'Streaming' LFP snapshots
        # (category=DISPLAY_STREAMING_EVENT). The diamond EVENTS row only renders the LABELED presses;
        # the Streaming snapshots render as per-lane PSD ticks from a SEPARATE payload (av.records via
        # _event_psd_index). So we run the (PSD-averaging) event_markers on the labeled events ONLY and
        # surface the Streaming count separately — avoids the (many) wasted decimated-PSD/peak
        # computations for Streaming markers the diamond row never draws.
        event_list = _load_patient_events(participant_uid)
        labeled_events = [e for e in event_list
                          if e.get("category") != DISPLAY_STREAMING_EVENT]
        streaming_count = sum(1 for e in event_list
                              if e.get("category") == DISPLAY_STREAMING_EVENT)
        events = availability.event_markers(labeled_events)
        events["streaming_count"] = streaming_count
        # Montage-PSD events: NeuralActivitySnapshot montage sweeps (category=DISPLAY_MONTAGE_SNAPSHOT;
        # a montage product carrying its OWN TD, distinct from the PSD-only patient events) NOT already
        # represented by a montage/survey PSD recording (de-duplicated against those StartTimes so we
        # don't double-count). Surfaced as their own marker row.
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
        # PRO times (pain["t"], the finite-metric+time set, == the matrix's pm[0]) are passed so the
        # TD-streaming index entries are RATING-CENTERED — one per PRO inside a session's coverage,
        # stamped at the PRO's time — making the live count IDENTICAL to the rating-centered backend
        # pool (a TD PRO inside coverage matches at offset 0 instead of "no neural match").
        _pro_t_idx = np.asarray(pain.get("t") or [], dtype=float) if isinstance(pain, dict) else None
        psd_scan_index = _psd_sample_index(td_all, psd_all,
                                           pro_times=(_pro_t_idx if _pro_t_idx is not None
                                                      and _pro_t_idx.size else None))
        # Patient-event PSDs (incl. 'Streaming') are imported into the per-channel pool, so index
        # them here too — they render as ticks on their contact lanes and the live binarization
        # preview counts them, matching the backend pool (TD + montage + Patient event).
        try:
            psd_scan_index = psd_scan_index + _event_psd_index(participant_uid,
                                                                sensing_index=_sensing_idx)
        except Exception as e:
            _log.warning("Biomarkers: event PSD index failed (%s)", e)

        # Eagerly warm the rating-centered PSD matrix on the background pool, reusing the recordings
        # already decoded here (td_all/psd_all carry "Data") so NO second .bdat decode happens — the
        # fix for the "90% CPU across all cores / 45 s blank timeline" stall, where the warm used to
        # re-decode every recording from the DB through its own 16-worker pool, duplicating this
        # request's decode and starving the foreground render. Centered on the metric-agnostic PRO set
        # (stable across metric switches) so the later scan/validation requests hit this exact entry.
        # Only fired on the timeline (availability) path (warm=True); the full-run path skips it to
        # avoid racing the scan that writes the same npz.
        if warm:
            try:
                _warm_pro_t = _all_pro_times(pro_df)
                if _warm_pro_t is not None and _warm_pro_t.size:
                    _PSD_WARM_POOL.submit(warm_psd_cache, participant_uid, pro_times=_warm_pro_t,
                                          decoded_td=list(td_all), decoded_psd=list(psd_all))
            except Exception as e:
                _log.warning("Biomarkers: PSD cache warm dispatch failed (%s)", e)

        return {"records": records, "pain": pain, "stim": stim, "freq_bands": bands,
                "span": span, "samples": samples, "lsb_overview": lsb_overview,
                "pro_lsb": pro_lsb,
                "events": events, "montage_events": montage_events,
                "psd_scan_index": psd_scan_index}
    except Exception as e:
        _log.warning("Biomarkers: availability payload failed: %s", e, exc_info=True)
        return {"records": [], "pain": {"metric": label_metric, "t": [], "y": []},
                "stim": {"t": [], "y": []}, "freq_bands": [], "span": [], "lsb_overview": {},
                "pro_lsb": {},
                "events": {"events": [], "n": 0},
                "montage_events": {"events": [], "n": 0}, "psd_scan_index": []}


@_pro_scoped
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
    native_lsb_tolerance_s = _native_lsb_tolerance_param(request_data)

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
            label_metric=label_metric, region_map=region_map,
            native_lsb_tolerance_s=native_lsb_tolerance_s)
        return {"availability": av, "available_metrics": BIOMARKER_METRICS,
                "label_metric": label_metric,
                "message": "DEMO DATA — synthetic availability timeline."}

    # Real participant. The pain-report table is fetched fresh every time regardless (decision 22
    # -- never memoized), which is cheap on its own (well under a second) and is what makes the
    # cache key below trustworthy: its content digest is the ONE thing that can tell a genuinely
    # new pain rating apart from an unchanged one, so a stale entry can never be served.
    pro_df = _load_pros(request_data, Participant)
    pro_df, label_metric, _ = _resolve_biomarker_metric(request_data, pro_df)
    pro_digest = _pro_table_digest(pro_df) if pro_df is not None and len(pro_df) else "empty"
    cache_key = ("availability_v1", participant_uid, native_lsb_tolerance_s, label_metric, pro_digest)

    def _build():
        # Only reached on a genuine cache miss -- the recording loads and _build_availability
        # itself (measured live on RCS08 at ~2.9s and ~5.0s respectively) are skipped entirely on
        # a hit. Recordings are loaded through the participant-scoped memo above so that even a
        # miss (a newly-filed rating, say) does not re-pay the recording-decode cost if some other
        # request already warmed it for this participant.
        td, chronic_list, powerdomain_list = _availability_recordings_cached(participant_uid)
        chan_order = _derive_chan_order(td)
        recorded_powers = _recorded_powers(powerdomain_list)
        region_map = _region_map(Participant, list(chan_order) + [p["raw"] for p in recorded_powers])
        # warm=True: _build_availability dispatches the eager rating-centered matrix warm from the
        # recordings IT already decoded (td_all/psd_all carry "Data"), on the background pool, so
        # the expensive Welch is on disk by the time the user clicks "Start exploratory analysis"
        # and the request thread never re-decodes. Only the timeline path warms; the full-run path
        # does not (it would race the scan writing the same matrix npz).
        built = _build_availability(
            participant_uid, chronic_list=chronic_list, powerdomain_list=powerdomain_list,
            td_list=td, pro_df=pro_df, label_metric=label_metric, region_map=region_map, warm=True,
            native_lsb_tolerance_s=native_lsb_tolerance_s)
        # Normalized to JSON-safe values (numpy arrays -> lists, NaN/Inf -> None) BEFORE this
        # entry is stored, not left for the view layer's own json_compliant_handler(Analysis) call
        # to do later. That call mutates whatever it is given IN PLACE -- harmless the first time,
        # but this same object is now handed back verbatim on every later cache hit too, so without
        # this, a second concurrent request could be mutating the one shared cached dict while a
        # third was reading it. Normalizing once here, before the object is ever shared, avoids
        # that regardless of request timing; the view's later call becomes a cheap, idempotent
        # no-op pass over data that is already in its final form.
        return json_compliant_handler(built)

    av = _availability_result_cached(cache_key, _build)

    msg = None
    if not av.get("records"):
        msg = ("No Percept recordings decoded for this participant yet — upload sessions to populate "
               "the availability timeline.")
    return {"availability": av, "available_metrics": BIOMARKER_METRICS,
            "label_metric": label_metric, "message": msg}


@_pro_scoped
def run_for_participant(request_data):
    """Assemble inputs from the DB + REDCap and run the biomarker pipeline for one participant.

    Returns a dict: {source, channels, timeline (records), summary, message}. `message` is
    non-empty (and timeline empty) when required inputs are missing -- the card renders that
    as a friendly state instead of erroring.
    """
    participant_uid = request_data["ParticipantId"]
    # THE BAND-BY-LENGTH-OF-SIGNAL SWEEP RIDES THIS ENDPOINT AND RETURNS ALONE.
    # The section at the bottom of the exploration page asks a different question from the panels
    # above it and has its own pain-score choice, so it fetches on its own. It returns here before
    # any of the heavy per-channel work below, because that work would add tens of seconds and
    # roughly nineteen megabytes to a request whose answer does not use any of it. The route and its
    # view are owned outside this work, which is why this is a flag on the existing endpoint rather
    # than an endpoint of its own.
    if _wants_band_time_sweep(request_data):
        try:
            return band_time_sweep_for_participant(request_data)
        except Exception as e:
            _log.warning("Biomarkers: band/length-of-signal sweep request failed (%s)", e,
                         exc_info=True)
            return {"band_time_sweep": {}, "available_metrics": BIOMARKER_METRICS,
                    "message": f"The sweep could not be computed: {e}"}
    # TRACK A, TASK A2's DRILL-DOWN. The grid's own stored response never carried the per-report
    # (band power, pain score) pairs behind one cell -- only the aggregate row and matrix values --
    # so a reader who clicks a cell has nowhere to get a scatter or a violin from. This is the
    # smallest thing that can answer that: one contact pair, one band centre, one length of signal,
    # matched exactly the way that cell's own grid value was, and handed back as raw pairs. It does
    # no permutation test and no bootstrap -- the r, the AUC and every other statistic for the cell
    # are already sitting in the grid response the browser is holding, so nothing here recomputes
    # them; this only supplies what a picture of that one cell needs.
    if _wants_band_time_sweep_cell(request_data):
        try:
            return band_time_sweep_cell_for_participant(request_data)
        except Exception as e:
            _log.warning("Biomarkers: band/length-of-signal cell drill-down failed (%s)", e,
                         exc_info=True)
            return {"band_time_sweep_cell": None,
                    "message": f"The cell's underlying data could not be computed: {e}"}
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
        # Recordings are immutable once exported (decision 22), so this no-expiry, participant-keyed
        # memo is safe -- same shape as _recordings_setup_cached above. The "Source" self-tag (for
        # the merged-series two-source batch/scale confound diagnostic downstream) and the
        # chronic+powerdomain concatenation both happen once, inside the memo, not on every request.
        chronic_list, powerdomain_list, power_list = _power_list_cached(participant_uid)

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
    native_lsb_tolerance_s = _native_lsb_tolerance_param(request_data)
    # Per-rating CAP for the exploratory scan: how many PSDs one pain rating may absorb per channel,
    # and the refractory gap (min) enforced among the kept set, so a streaming BURST around one survey
    # can't double-count. `MaxPerRating` (>=1) and `RefractoryMin` (>=0) come from the frontend.
    # max_per_rating=1 reduces to the old "one per rating" behavior (the single nearest-prior PSD).
    # Match direction defaults to "prior" (forecasting: the PSD must precede the rating).
    max_per_rating = _int_param(request_data, "MaxPerRating", default=3, lo=1, hi=50)
    refractory_min = _float_param(request_data, "RefractoryMin", default=2.0, lo=0.0, hi=720.0)
    # Outlier exclusion (PI, 2026-08-30). Defaults come from the analytics module, so the rule is ON
    # unless a caller deliberately disables it. `OutlierNMad = 0` disables removal entirely, which is
    # the switch for reproducing a pre-2026-08-30 number rather than editing the module.
    outlier_n_mad = _float_param(request_data, "OutlierNMad",
                                 default=float(analytics.OUTLIER_N_MAD), lo=0.0, hi=50.0)
    outlier_scale = str(request_data.get("OutlierScale") or analytics.OUTLIER_SCALE).lower()
    if outlier_scale not in ("log", "raw"):
        outlier_scale = analytics.OUTLIER_SCALE
    # Three-way match direction (PSD<->PRO). See `_forecast_match_direction`'s own docstring for
    # the meaning of each value and why this reader defaults to "prior" where the sweep's own
    # `_sweep_match_direction` defaults to "pro_first".
    match_direction = _forecast_match_direction(request_data)
    # `aggregate` retained for back-compat with the detail builder, but the cap subsumes it: a cap of
    # 1 IS one-per-rating, so callers no longer send the old Aggregate toggle. Keep "all" here so the
    # cap (not a pre-aggregation collapse) governs sample independence, with rating-grouped AUC on top.
    aggregate = "all"
    # The spectral scan's per-PRO LSB spectrum is built by matching PROs against the match-agnostic
    # raw 3 s-window cache (median over a configurable rating-centered extent, TD preferred
    # in-window, NO LSB vector reused across >1 PRO) -- the ONLY path since 2026-06-28 (decision
    # log). `UseLiveMatching` used to gate this; removed (decision 76 UI-wiring sweep) after
    # confirming it had become a request field with no computational effect anywhere in this
    # function -- read once, only ever echoed back, never branched on.
    match_extent_s = _float_param(request_data, "MatchExtentSec", default=float(
        analytics.TRANSFORM_CENTERED_EXTENT_SECONDS), lo=3.0, hi=300.0)
    # When ON, a raw window may match EVERY PRO whose extent covers it (not just its nearest), trading
    # the no-reuse independence guarantee for sample size. Default OFF (strict one-window-one-PRO).
    allow_window_reuse = str(request_data.get("AllowWindowReuse", "")).lower() in ("1", "true", "yes", "on")
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
    # TD-streaming PSDs are rating-centered (one centered window per PRO inside a session's coverage)
    # instead of a single first-30 s spectrum stamped at the session start — this is what lets a
    # rating in the middle of a long stream match. Use the METRIC-AGNOSTIC PRO set (all timestamps),
    # which is the SAME set `warm_psd_cache` built the matrix on, so this request hits the warm cache
    # instead of re-decoding on the request thread. Per-metric PRO filtering stays downstream in the
    # match step (build_pooled_detail_from_matrix / pro_match).
    pro_match = _pro_match_arrays(pro_df, label_metric)
    _force_refresh = _normalize_force_refresh(request_data.get("ForceRefresh"))
    psd_matrix = _cached_psd_matrix(participant_uid, pro_times=_all_pro_times(pro_df),
               force_refresh=_force_refresh)

    # Per-pair LSB spectrum cache for the live matching-controls caption (live_match_stats, read via
    # _live_pro_lsb_spectrum below). Its per-PRO indexing is by position in `pro_match[0]` (the
    # metric-FILTERED PRO set — only ratings with a finite label_metric). So the cache MUST be built
    # from that exact array: _scan_pro_times = pro_match[0] — do not substitute pain["t"] (the
    # metric-AGNOSTIC set the timeline uses) here, or the index would point at the wrong PRO. The
    # timeline's modeled markers build their OWN cache entry
    # from pain["t"] in _build_availability under a DIFFERENT signature; the two entries agree on any
    # shared PRO because per_pro_lsb_spectrum is deterministic in (pro_time, channel, recordings) — the
    # numbers match by construction, NOT by sharing one memo slot. td_recordings = ALL TD-bearing
    # products (streaming + montage/survey, 250 Hz); event_psd_blocks = PatientControllerEvent FFT only.
    _scan_psd_list = _load_recordings(participant_uid, AVAILABILITY_PSD_TYPES)
    # Index from streaming TD only — psd_list is montage sweeps (all pairs, excluded by guard).
    _scan_sensing_idx = _build_sensing_config_index(list(td or []))
    _scan_event_blocks = _event_psd_lsb_blocks(participant_uid,
                                               sensing_index=_scan_sensing_idx)
    # Montage/survey device-PSD snapshots (Descriptor.MedtronicPSD) as their own bridge windows, so a
    # montage contributes a PSD-tier LSB even when its TD tile fails the cache quality gate. Same unit /
    # bridge constant as the patient-event PSD (validated paired vs the TD transform).
    _scan_montage_blocks = _montage_psd_lsb_blocks(participant_uid,
                                                   montage_recordings=_scan_psd_list)
    _scan_channels = list(dict.fromkeys(
        availability._canon_channel(ch) for ch in (chan_order or [])))
    _scan_pro_times = (pro_match[0] if pro_match is not None else None)
    _have_scan_inputs = (_scan_pro_times is not None and _scan_pro_times.size and _scan_channels)
    live_match_stats = None
    if _have_scan_inputs:
        # CACHE-BASED MATCHING (PI 2026-06-28, now the ONLY path — the legacy real-time
        # per_pro_lsb_spectrum recompute is retired): match PROs against the pre-computed match-agnostic
        # raw 3 s-tile cache. TWO WINDOWS: tol_s = the main MatchToleranceMin slider (minutes->seconds)
        # is the eligibility radius for BOTH TD and PSD; td_quantity_s = the MatchExtentSec slider caps
        # how many of the nearest 3 s TD tiles to median per PRO (PSD has no quantity cap). The main
        # tolerance can be None ("disable time-matching") — fall back to the extent so PSD still has a
        # finite eligibility window rather than matching the whole record. AllowWindowReuse governs
        # reuse of the same window+modality across PROs (per-modality, both passes).
        _tol_s = (float(match_tol_min) * 60.0 if match_tol_min else float(match_extent_s))
        _, live_match_stats = _live_pro_lsb_spectrum(
            participant_uid, _scan_pro_times, _scan_channels,
            list(td or []) + list(_scan_psd_list or []),
            _scan_event_blocks, montage_psd_blocks=_scan_montage_blocks,
            tol_s=_tol_s, td_quantity_s=match_extent_s, allow_window_reuse=allow_window_reuse,
            return_spectra=False)  # only live_match_stats (the matching-controls caption) is used

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
                                                 match_direction=match_direction,
                                                 outlier_n_mad=outlier_n_mad,
                                                 outlier_scale=outlier_scale),
                         label_metric=label_metric)
    # Echo the exclusion settings at the top level so the UI can state the rule without digging
    # into the analytics subtree, and so a saved response records what was applied.
    # Report the cache decision so a "the plot is not updating" report is answerable from the
    # payload alone instead of needing a container probe: the reader can see whether this response
    # came from cache and how to force a rebuild.
    out["cache"] = {
        "force_refresh": _force_refresh,
        "meaning": ({"matrix": "assembled-matrix cache bypassed and rebuilt from per-recording spectra",
                     "all": "assembled-matrix AND per-recording spectra bypassed; every recording "
                            "re-decoded and re-Welch'd"}.get(_force_refresh)
                    if _force_refresh else "normal cached read (no refresh requested)"),
        "how_to_refresh": ("POST ForceRefresh='matrix' to rebuild the assembled matrix (seconds), or "
                           "ForceRefresh='all' to also re-decode and re-Welch every recording "
                           "(minutes). NOTE: a stale cache has never yet been the cause of a frozen "
                           "plot here — on 2026-08-30 the cause was device files that had never been "
                           "ingested. Check the newest SourceFile date before reaching for this."),
    }
    out["outlier_n_mad"] = (float(outlier_n_mad) if outlier_n_mad is not None
                            else float(analytics.OUTLIER_N_MAD))
    out["outlier_scale"] = str(outlier_scale if outlier_scale is not None
                               else analytics.OUTLIER_SCALE)
    out["label_metric"] = label_metric
    out["aggregate"] = aggregate
    out["max_per_rating"] = max_per_rating
    out["refractory_min"] = refractory_min
    out["match_direction"] = match_direction
    out["match_extent_s"] = float(match_extent_s)
    out["native_lsb_tolerance_s"] = float(native_lsb_tolerance_s)
    out["allow_window_reuse"] = bool(allow_window_reuse)
    if live_match_stats is not None:
        # Pooled independence stats across channels: with live matching every PRO contributes ONE LSB
        # vector (no reuse), so pseudoreplication collapses. Surface the totals for the UI before/after.
        _pooled = {"n_pro": 0, "n_pro_td": 0, "n_pro_psd": 0, "n_pro_unmatched": 0,
                   "n_td_assigned": 0, "n_td_used": 0, "n_psd_assigned": 0, "n_psd_used": 0}
        for _st in live_match_stats.values():
            for _k in _pooled:
                _pooled[_k] += int(_st.get(_k, 0) or 0)
        _pooled["extent_s"] = float(match_extent_s)        # legacy alias (== td_quantity_s)
        _pooled["td_quantity_s"] = float(match_extent_s)   # TD nearest-N-seconds quantity slider
        _pooled["tol_s"] = (float(match_tol_min) * 60.0 if match_tol_min else float(match_extent_s))
        _pooled["match_tolerance_min"] = match_tol_min      # the main eligibility slider (minutes)
        _pooled["per_channel"] = live_match_stats
        out["live_match_stats"] = _pooled
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
        label_metric=label_metric, region_map=region_map,
        native_lsb_tolerance_s=native_lsb_tolerance_s,
        psd_list=_scan_psd_list)  # already loaded above for the live-matching scan; same
                                  # participant, same AVAILABILITY_PSD_TYPES -- reuse, don't reload
    # Honesty flag (rigor fix #5): the power-domain detector currently pools all recorded power
    # channels into ONE threshold. If they span >1 anatomical target/hemisphere (e.g. Left GPi +
    # Right medial thalamus) and/or the raw 10-min Chronic vs per-session Power-Domain scales,
    # a single pooled threshold mixes physiologically distinct signals — surface that to the user.
    distinct_regions = sorted({(p.get("region") or "").strip() for p in recorded_powers if p.get("region")})
    # TRACK C STEP 4: when the tiles every number on this page derives from were last built.
    out["cache_status"] = cache_status_for_page(participant_uid)
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
    # THE THREE-WAY VERDICT DECIDES THE PARENTHETICAL, not the legacy boolean.
    #
    # This used to fall straight through to "(stim-stable)" whenever `stim_stable` was not
    # explicitly False, which includes the case where the equivalence test ran and could not
    # decide: the interaction test failed to reject AND the interval on the largest between-era
    # slope difference was wider than the declared margin. A failure to reject is not evidence of
    # equivalence, so printing "stim-stable" there asserted exactly what the test had declined to
    # grant, and it did so in the badge — the shortest and most-read string on the page.
    #
    # The front end was rewriting this parenthetical client-side to compensate, which worked but
    # put the same rule in two places. Reading `stability_verdict` here removes that duplication.
    _v = h.get("stability_verdict") if h.get("available") else None
    if _v == "inconclusive":
        return "VALIDATED (stim stability not determinable)"
    if _v in (None, "", "not_tested") and h.get("stim_stable") is None:
        return "VALIDATED (stim stability not tested)"
    return "VALIDATED (stim-stable)"


def _deployment_summary_stim_stable_gate(st):
    """Pure gate-state logic for deployment_summary's "stim_stable" gate (decision 82 fix).

    Extracted so this can be pinned by a direct test without a live participant, the same reason
    `_band_decide_verdict` above is its own function. Reads `stability_verdict` (the three-way
    "stable"/"stim-dependent"/"inconclusive" answer from `analytics.stability_equivalence`), never
    the retired `stim_stable` boolean (`p_lrt >= 0.05`, a failure to reject rather than evidence of
    stability -- see this same file's `_band_decide_verdict` comment for why that flag alone is
    unsafe). Returns (state, detail) where state is one of "pass"/"fail"/"indeterminate".
    """
    _v = st.get("stability_verdict") if st.get("available") else None
    if _v == "stable":
        return "pass", f"band×era LRT p={st.get('lrt_p')} (equivalence verdict: stable)"
    if _v == "stim-dependent":
        return "fail", f"band×era LRT p={st.get('lrt_p')} (equivalence verdict: stim-dependent)"
    if st.get("available"):
        return "indeterminate", (
            f"band×era LRT p={st.get('lrt_p')} did not reject, but the interval on the largest "
            "between-era difference is wider than the declared margin -- these data cannot tell a "
            "stable band from a materially unstable one (absence of evidence, not evidence of "
            "stability).")
    return "indeterminate", ("band×era LRT did not converge on this match-direction — "
                             "stim-stability UNCONFIRMED (absence of evidence, not evidence of "
                             "stability).")


def _deployment_summary_adaptive_band_gate(center_hz, band_width_hz):
    """Pure gate-state logic for deployment_summary's "adaptive_band" gate (decision 82 fix).

    Checks the band EDGES against the Percept adaptive range, matching
    `ClosedLoopDeployment/constraints.py`'s D08 rule (`band_edges`/`permitted_band_hz`) rather than
    the band's bare centre -- a 5 Hz band centred at 10 Hz has its centre inside 8-30 Hz but its
    lower edge at 7.5 Hz, outside it, and D08 (the rule that actually decides whether the device
    will accept the band) correctly refuses it. Returns (state, detail, lo_edge, hi_edge).
    """
    half = float(band_width_hz) / 2.0
    lo_edge, hi_edge = center_hz - half, center_hz + half
    ok = bool(lo_edge >= ADAPTIVE_LO_HZ and hi_edge <= ADAPTIVE_HI_HZ)
    detail = (f"band {round(lo_edge,1)}–{round(hi_edge,1)} Hz (center {round(center_hz,1)} Hz) "
             f"must fit inside {ADAPTIVE_LO_HZ:.1f}–{ADAPTIVE_HI_HZ:.1f} Hz")
    return ("pass" if ok else "fail"), detail, lo_edge, hi_edge


@_pro_scoped
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
    # Pass the METRIC-AGNOSTIC PRO set so TD PSDs are rating-centered identically to the scan path AND
    # the warm cache (band validation must see the SAME pooled features the scan does, or a validated
    # band wouldn't match its scan r; using pm[0] here would re-key the matrix per metric and miss the
    # warm entry). Per-metric filtering stays in the match step below (pm feeds the matcher).
    _force_refresh = _normalize_force_refresh(request_data.get("ForceRefresh"))
    mat = _cached_psd_matrix(participant_uid, pro_times=_all_pro_times(pro_df),
        force_refresh=_force_refresh)
    if mat is None or np.asarray(mat.get("t")).size == 0 \
            or np.asarray(mat.get("logX")).size == 0:
        return {"available": False, "reason": "no PSD samples for this participant"}
    label_strategy, low_pct, high_pct = _label_strategy_params(request_data)
    match_tol_min = _match_tolerance_param(request_data)
    max_per_rating = _int_param(request_data, "MaxPerRating", default=3, lo=1, hi=50)
    refractory_min = _float_param(request_data, "RefractoryMin", default=2.0, lo=0.0, hi=720.0)
    # Three-way match direction (PSD<->PRO); see `_forecast_match_direction`'s own docstring.
    match_direction = _forecast_match_direction(request_data)
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


#: ==========================================================================================
#: TRACK D, TASK D2(b) — the cross-setting-stability column on the calibrated grid.
#:
#: "Does this band mean the same thing about pain at every stimulation setting" is already answered
#: for ONE chosen candidate, on the Closed-Loop Deployment page, by
#: `ClosedLoopDeployment.adapter.report_for_participant` (see
#: `ClosedLoopDeployment/WIRING_stability_into_the_report.md`, Route A): it calls
#: `_validate_band_core` here, reads the `"stim"` result back out, and hands THAT RAW RESULT to
#: `ClosedLoopDeployment.stability.finding_from_stability_result` for the honest four-answer
#: translation.
#:
#: THIS FUNCTION DOES ONLY THE FIRST HALF, ON PURPOSE. `stability.py`'s own module docstring states
#: the dependency direction as a hard rule: "it imports from Biomarkers, and Biomarkers must never
#: import it back, because that would be a loop neither module could load out of." An earlier draft
#: of this function violated that rule by importing `ClosedLoopDeployment.stability` from inside
#: Biomarkers -- caught immediately when the container (which loads `Biomarkers.bravo_service` but
#: never `ClosedLoopDeployment`) tried to import it and failed. So the honest-four-value TRANSLATION
#: stays on the Closed-Loop Deployment side, where the one-way arrow already points, and this
#: function returns only the untranslated `_validate_band_core(...)["stim"]` result -- exactly the
#: same dict `adapter.py`'s own inline call reads before it hands the same thing to
#: `stability.finding_from_stability_result`. `Biomarkers/tests` proves this raw result is identical
#: to what `_validate_band_core` itself returns; `ClosedLoopDeployment/tests` proves the translation
#: of a grid row is identical to `adapter.py`'s own inline translation of the same raw result.
#:
#: A READER OF THE TRANSLATED FIELD MUST STILL NEVER USE A BARE `stim_stable`/`stable` BOOLEAN.
#: The warning already in `adapter.py` applies without a word changed: on this participant's own
#: data, ONE_THREE_LEFT at 12.5 Hz has the old two-valued flag reading True (the interaction test
#: did not reject, p = 0.290) while the honest answer is "cannot tell" (the interval on the largest
#: between-era difference runs from -1.23 to +0.22, wider than the declared margin of 0.69).
#: ==========================================================================================
def raw_stability_result_for_point(participant_uid, channel, center_hz, band_width_hz=5.0):
    """The untranslated `stim` result `_validate_band_core` computes for one (channel, band centre)
    point -- the same call the single-candidate page already makes, run once per grid point instead
    of once per click. Never raises: any failure comes back as `{"available": False, "reason": ...}`,
    the same shape `_validate_band_core` itself already uses for a failure.

    Read `answer` on the TRANSLATED form (`ClosedLoopDeployment.stability.finding_from_stability_
    result` applied to this dict), never a bare boolean read off this raw form directly -- see the
    module note above.
    """
    width = float(band_width_hz)
    try:
        core = _validate_band_core({
            "ParticipantId": participant_uid, "Channel": channel,
            "CenterHz": float(center_hz), "BandWidthHz": width})
        return (core.get("stim") or {}) if core.get("available") else {
            "available": False,
            "reason": core.get("reason") or "the band validation path returned nothing usable"}
    except Exception as exc:                                     # noqa: BLE001
        return {"available": False, "reason": f"band validation raised {exc!r}"}


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


def _ramp_guidance(polarity, adaptive_valid, suggested_mode, *, stim_stable=None,
                   power_available=None):
    """Advisory Percept adaptive RAMP guidance for the sign-off (audit C10).

    The closed-loop tuning surface is band + threshold + RAMP — but the module previously stopped at
    band + threshold, leaving the programmer to pick a transition rate with no advice. Percept adaptive
    ramps stimulation between the lower and upper amplitude limits when the sensed LFP band-power
    crosses the detection threshold(s); the RAMP RATE (mA/s, set per direction as up/down) controls how
    abruptly that transition happens. This is ADVISORY ONLY — the safe rate is patient- and
    side-effect-bound and must be titrated in clinic — but a sensible starting posture follows from the
    biomarker's properties:

      * Not deployable as stock adaptive (out-of-range band, or negative polarity needing the inverse
        control law) -> no ramp guidance; fix the control mapping first.
      * A biomarker that is NOT stim-stable (band x era reversal / significant LRT) argues for a
        SLOWER, more conservative ramp: the feature-to-pain relationship shifts as stim changes, so a
        fast transition risks chasing a moving target. Flagged conservative.
      * Otherwise a MODERATE starting ramp, titrated to comfort, with asymmetric up/down as the usual
        starting posture (ramp DOWN — reducing stim — can be a touch faster than ramp UP for comfort).

    Returns {available, posture, ramp_up_hint, ramp_down_hint, transition_note, reason} — all advisory
    strings, never device-set values. Defensive: returns available False on any unknown control mapping.
    """
    if not adaptive_valid or suggested_mode is None or polarity != "positive":
        return {
            "available": False,
            "reason": ("ramp guidance applies only to an in-range, positive-direction biomarker "
                       "deployable as stock Percept adaptive; resolve the control mapping first "
                       "(custom/negated feature or in-range re-anchor) before setting a ramp rate"),
        }
    # Anything not CONFIRMED stable (False = stim-dependent, None = LRT did not converge) takes the
    # conservative posture — the same abstain philosophy as the C8 stim-stability gate: absence of a
    # stability result is not evidence of stability, so do not start with a fast ramp.
    conservative = (stim_stable is not True)
    posture = "conservative" if conservative else "moderate"
    if conservative:
        why = ("Biomarker is stim-dependent (the band->pain relationship shifts across stim eras)"
               if stim_stable is False else
               "stim-stability is UNCONFIRMED (the band×era LRT did not converge)")
        transition_note = (f"{why} — start SLOW so a fast transition does not chase a moving target; "
                           "re-evaluate stability before speeding the ramp up.")
        ramp_up_hint = "start at the slow end of the clinic range, titrate up only if symptom control lags"
        ramp_down_hint = "match or slightly faster than ramp-up, prioritizing comfort on stim reduction"
    else:
        transition_note = ("Biomarker is stim-stable — a moderate transition is a reasonable starting "
                           "posture; titrate to the patient's comfort and side-effect threshold in clinic.")
        ramp_up_hint = "moderate starting rate, titrate up to comfort"
        ramp_down_hint = "moderate, may be set slightly faster than ramp-up for comfort on stim reduction"
    return {
        "available": True,
        "posture": posture,
        "ramp_up_hint": ramp_up_hint,
        "ramp_down_hint": ramp_down_hint,
        "transition_note": transition_note,
        "reason": ("Advisory only — the deployable ramp rate is patient- and side-effect-bound and "
                   "must be titrated in clinic. This is a starting posture from the biomarker's "
                   "polarity, adaptive-range validity, and stim-stability."),
    }


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


def _threshold_mode_block(request_data, center_hz, threshold_lsb):
    """Resolve the requested Percept threshold mode and report, for THIS band, whether the
    Timeline-anchored LSB threshold is valid/usable in that mode.

    Reads request ThresholdMode in {Dual, Single, SingleInverse} (default Dual — the mode forced for
    non-PD pain patients). Returns a JSON-able dict carrying, for the chosen mode and all three:
      * fft_size / averaging_ms / update_hz / adaptive (from analytics.THRESHOLD_MODES);
      * adaptive_band_ok: is center_hz inside the mode's adaptive sensing range (8–30 Hz for the two
        adaptive modes)?;
      * fft_convertible: does the mode share the 256-pt FFT this calibration/anchor is built on? (Single
        Threshold's 64-pt FFT does NOT — its LFP Power is a different band integral);
      * threshold_usable + a plain-language note steering the programmer.
    The Timeline anchor is a 10-min average; the controller adapts at the mode's averaging window, so
    the number is a STARTING POINT to be confirmed live in the operating mode.
    """
    raw = (request_data.get("ThresholdMode") or "Dual")
    alias = {"dual": "Dual", "single": "Single", "singleinverse": "SingleInverse",
             "single_inverse": "SingleInverse", "single-inverse": "SingleInverse",
             "singlethreshold": "Single", "singlethresholdinverse": "SingleInverse"}
    mode = alias.get(str(raw).strip().lower().replace(" ", ""), "Dual")
    modes = analytics.THRESHOLD_MODES

    def _one(m):
        v = modes[m]
        lo, hi = v["adaptive_band_hz"]
        band_ok = (center_hz is not None and lo <= float(center_hz) <= hi)
        convertible = (v["fft_size"] == analytics.CONVERSION_FFT_SIZE)
        return {
            "label": v["label"],
            "fft_size": v["fft_size"],
            "averaging_ms_adaptive": v["averaging_ms"][0],
            "averaging_ms_sensing": v["averaging_ms"][1],
            "fft_update_hz_adaptive": v["fft_update_hz"][0],
            "adaptive": v["adaptive"],
            "adaptive_band_hz": [lo, hi],
            "adaptive_band_ok": bool(band_ok),
            "fft_convertible": bool(convertible),
        }

    has_thr = bool(threshold_lsb and threshold_lsb.get("available")
                   and threshold_lsb.get("upper_lsb") is not None)

    def _verdict(d):
        """Usability + plain-language note for ONE mode's metadata dict `d`. Computed for EVERY mode
        so the frontend can switch modes client-side (no refetch) — the threshold value is mode-
        independent; only its validity/interpretation changes."""
        if not d["fft_convertible"]:
            return (False,
                    "%s uses a %d-pt FFT, but the device Timeline LSB (and this calibration) is "
                    "256-pt. LFP Power is not comparable across FFT sizes, so the Timeline-anchored "
                    "threshold does NOT translate to this mode — recapture the threshold while "
                    "sensing in %s before deploying." % (d["label"], d["fft_size"], d["label"]))
        if not d["adaptive_band_ok"] and d["adaptive"]:
            return (False,
                    "%.1f Hz is outside this mode's %g–%g Hz adaptive sensing range, so it cannot run "
                    "adaptive here regardless of the threshold." % (
                        float(center_hz or 0), d["adaptive_band_hz"][0], d["adaptive_band_hz"][1]))
        if not has_thr:
            return (False,
                    "Mode is compatible (256-pt FFT, band in range), but no Timeline-anchored LSB "
                    "threshold is available for this band yet.")
        avg = d["averaging_ms_adaptive"]
        if not d["adaptive"]:
            return (True,
                    "Sensing-only mode (no adaptive actuation): the Timeline-anchored upper threshold "
                    "%.1f LSB is reviewed against, not acted on. 256-pt FFT, %g ms averaging." % (
                        float(threshold_lsb["upper_lsb"]), avg))
        return (True,
                "Timeline-anchored upper threshold %.1f LSB is a STARTING POINT: it is read off the "
                "10-min Timeline average, while %s adapts on a %g ms window. Shorter averaging widens "
                "the tails, so confirm/raise the threshold live while sensing in %s before enabling "
                "adaptive." % (float(threshold_lsb["upper_lsb"]), d["label"], avg, d["label"]))

    all_modes = {}
    for m in modes:
        d = _one(m)
        u, note_m = _verdict(d)
        d["threshold_usable"] = u
        d["note"] = note_m
        all_modes[m] = d
    chosen = all_modes[mode]

    return {
        "requested_mode": mode,
        "chosen": chosen,
        "threshold_usable": chosen["threshold_usable"],
        "note": chosen["note"],
        "controller_averaging_ms": chosen["averaging_ms_adaptive"],
        "timeline_averaging_ms": 600000.0,
        "all_modes": all_modes,
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
    # Forward / out-of-sample validation alongside the in-sample ROC (audit C2): held-out AUC + CI
    # from train-past → test-future weekly folds, so the panel shows in-sample vs forward side by side.
    forward = analytics.deployment_forward_chaining(
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
        "forward": forward,
    }


def band_psd_lsb_conversion(request_data):
    """Derive a PSD→device-LSB conversion for ONE channel from time-matched chronic streams.

    The device reports band power in "LSB" units; an offline Welch PSD reports physical µV²/Hz. This
    pairs every offline PSD epoch on the channel with the device's own LSB Timeline samples recorded
    within a time window (±MatchWindowH hours, default 1) and fits the proportional law LSB = k·µV²
    (analytics.psd_lsb_conversion), integrating each PSD over the band the DEVICE was actually sensing
    at that moment (each LSB sample carries its sensing center_hz). No mains notch is applied — the
    Percept is implanted and battery-powered, so there is no 60 Hz line component to remove.

    The user's design choice: pairs within 1–2 h are "good enough" because chronic band power is
    slowly varying. The conversion is a cross-scale CALIBRATION (show a physical µV² target in the LSB
    units the device programs), not a control law.

    Request: ParticipantId, Channel; optional CenterHz (fixed band centre, else use each LSB sample's
    own sensing center_hz), BandWidthHz (default 5.0), MatchWindowH (default 1.0), NBoot (default 2000).
    Returns analytics.psd_lsb_conversion(...) enriched with channel, match_window_h, band_width_hz,
    center_hz_mode, and a small scatter sample (≤400 points) for the panel, or {available: False,...}.
    """
    participant_uid = request_data.get("ParticipantId")
    channel = request_data.get("Channel")
    if not (participant_uid and channel):
        return {"available": False, "reason": "ParticipantId and Channel required"}
    try:
        win_h = float(request_data.get("MatchWindowH", 1.0))
    except (TypeError, ValueError):
        win_h = 1.0
    win_h = min(max(win_h, 0.25), 6.0)
    half = float(request_data.get("BandWidthHz", 5.0)) / 2.0
    fixed_center = request_data.get("CenterHz")
    try:
        fixed_center = float(fixed_center) if fixed_center is not None else None
    except (TypeError, ValueError):
        fixed_center = None
    n_boot = _int_param(request_data, "NBoot", default=2000, lo=200, hi=5000)

    Participant = models.Participant.find(uid=participant_uid)
    if Participant is None:
        return {"available": False, "reason": f"participant {participant_uid} not found"}

    short = analytics.format_channel(channel)["short"]

    # --- raw PSD rows for this channel (cached per-recording; {channel, source, t, freq, power}) ---
    try:
        rows, _nc, _ncomp = _assemble_psd_rows_cached(participant_uid)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"PSD assembly failed: {e}"}
    psds = []
    for r in rows:
        rc = r.get("channel")
        if rc == channel or analytics.format_channel(rc)["short"] == short:
            psds.append((float(r["t"]), r["freq"], r["power"]))
    if len(psds) < 20:
        return {"available": False, "reason": f"only {len(psds)} offline PSD epochs on {channel}",
                "n_pairs": 0}
    psds.sort(key=lambda x: x[0])

    # --- device LSB Timeline for this channel (chronic + powerdomain streaming) ---
    chronic = _load_recordings(participant_uid, CHRONIC_TYPES)
    pdl = _load_recordings(participant_uid, POWERDOMAIN_TYPES)
    from modules.Biomarkers.routines import availability as _av
    lsb = _av.lsb_series(chronic, pdl)
    L = lsb.get(channel) or lsb.get(short)
    if not L:
        return {"available": False, "reason": f"no device LSB Timeline for {channel}", "n_pairs": 0}
    ly = np.asarray(L.get("y"), dtype=float)
    lt = np.asarray(L.get("t"), dtype=float)
    lc = np.asarray(L.get("center_hz"), dtype=float)
    lsrc = np.asarray(L.get("source") or ["?"] * ly.size, dtype=object)
    keep = np.isfinite(ly) & (ly > 0) & np.isfinite(lt)
    ly, lt, lc, lsrc = ly[keep], lt[keep], lc[keep], lsrc[keep]
    if lt.size < 20:
        return {"available": False, "reason": f"only {lt.size} usable device LSB samples on {channel}",
                "n_pairs": 0}
    order = np.argsort(lt); ly, lt, lc, lsrc = ly[order], lt[order], lc[order], lsrc[order]

    # --- MODALITY + CONFIGURATION GUARD (audit: the 8.8 Hz "drift" was a pooling artifact) ----------
    # The device computes "LFP Power" through DIFFERENT signal chains depending on how it was recorded
    # (per the Percept aDBS white paper, FY25): the chronic BrainSense Timeline is a **10-minute**
    # average; in-clinic streaming (Sensing Only) is a **3000 ms** average; and the adaptive (aDBS)
    # controller itself acts on a **1200 ms** average (Dual Threshold) — all 256-pt FFT but wildly
    # different averaging windows. Pooling them gives a SINGLE LSB/µV² gain that is really a blend of
    # two measurements with ~200-600x different smoothing, and a sensing-band reconfiguration (the
    # device parked at a different center frequency) breaks the series outright. We therefore:
    #   (1) NEVER pool across `source`; match + fit each modality SEPARATELY;
    #   (2) within a match window only use LSB samples whose own sensing center is consistent with the
    #       band being calibrated (per-sample center, not a window median that can straddle a reconfig);
    #   (3) tag which modality is closest to what the CONTROLLER acts on (streaming/3000 ms is the
    #       nearest available proxy for the 1200 ms aDBS detector; chronic/10-min is a trend, far from
    #       the control timescale and must NOT seed a deployment threshold).
    # The white-paper averaging windows (ms) per source; aDBS adaptive Dual-Threshold detector = 1200.
    _SRC_AVG_MS = {"streaming": 3000.0, "chronic": 600000.0}
    _CONTROLLER_AVG_MS = 1200.0  # Dual Threshold, Adaptive (the unit a deployed threshold must be in)
    win_s = win_h * 3600.0

    def _match_one_source(src_mask, src_name):
        """Pair PSD epochs to LSB samples of ONE source only; band center from per-sample sensing."""
        st, sy, sc = lt[src_mask], ly[src_mask], lc[src_mask]
        if st.size < 20:
            return None
        P, Lp, T = [], [], []
        for (tp, fr, pw) in psds:
            a = int(np.searchsorted(st, tp - win_s, side="left"))
            b = int(np.searchsorted(st, tp + win_s, side="right"))
            if b - a < 1:
                continue
            cc = sc[a:b]
            if fixed_center is not None:
                center = fixed_center
                # only keep samples whose own center is within ±half of the requested band
                near = np.isfinite(cc) & (np.abs(cc - fixed_center) <= half)
                if near.sum() == 0:
                    continue
                lsb_val = float(np.median(sy[a:b][near]))
            else:
                ccf = cc[np.isfinite(cc)]
                if ccf.size == 0:
                    continue
                center = float(np.median(ccf))
                # CONFIGURATION GUARD: require the window to sense ONE band (no reconfig straddle)
                near = np.isfinite(cc) & (np.abs(cc - center) <= half)
                if near.sum() == 0 or (near.sum() / cc.size) < 0.8:
                    continue
                lsb_val = float(np.median(sy[a:b][near]))
            bp = analytics._band_power_notched(fr, pw, center, half)
            if not (np.isfinite(bp) and bp > 0):
                continue
            P.append(bp); Lp.append(lsb_val); T.append(tp)
        if len(P) < 20:
            return None
        f = analytics.psd_lsb_conversion(np.asarray(P), np.asarray(Lp), n_boot=n_boot)
        f["source"] = src_name
        f["n_pairs"] = len(P)
        f["averaging_ms"] = _SRC_AVG_MS.get(src_name)
        f["controller_relevant"] = (src_name == "streaming")
        f["t_span"] = [float(min(T)), float(max(T))] if T else None
        if f.get("available"):
            Pa = np.asarray(P); La = np.asarray(Lp)
            idx = np.arange(Pa.size)
            if Pa.size > 400:
                idx = np.linspace(0, Pa.size - 1, 400).astype(int)
            f["scatter"] = {"psd_uv2": [float(x) for x in Pa[idx]],
                            "lsb": [float(x) for x in La[idx]]}
        return f

    sources = [s for s in ("streaming", "chronic") if np.any(lsrc == s)]
    by_modality = {}
    for s in sources:
        r = _match_one_source(lsrc == s, s)
        if r is not None:
            by_modality[s] = r

    if not by_modality:
        return {"available": False, "reason": "no modality yielded >=20 single-configuration pairs",
                "n_pairs": 0, "channel": channel}

    # Headline fit = the controller-relevant modality if present, else the largest-n modality.
    if "streaming" in by_modality:
        primary = by_modality["streaming"]
    else:
        primary = max(by_modality.values(), key=lambda f: f.get("n_pairs", 0))

    fit = dict(primary)  # copy the primary modality's fit to the top level (back-compat)
    fit["channel"] = channel
    fit["channel_label"] = analytics.format_channel(channel)["label"]
    fit["match_window_h"] = win_h
    fit["band_width_hz"] = half * 2.0
    fit["center_hz_mode"] = ("fixed %.1f Hz" % fixed_center) if fixed_center is not None \
        else "device sensing center (per-sample)"
    fit["primary_source"] = primary["source"]
    fit["controller_averaging_ms"] = _CONTROLLER_AVG_MS
    # Per-modality breakdown (k / R² / n / averaging) so the panel can show them side-by-side and
    # never silently pool. A large k gap between modalities is the pooling artifact made explicit.
    fit["by_modality"] = {
        s: {k: r.get(k) for k in ("available", "k_lsb_per_uv2", "k_ci", "r2", "loglog_slope",
                                  "n_pairs", "averaging_ms", "controller_relevant", "t_span")}
        for s, r in by_modality.items()
    }
    if len(by_modality) > 1:
        ks = {s: r.get("k_lsb_per_uv2") for s, r in by_modality.items() if r.get("k_lsb_per_uv2")}
        if len(ks) > 1:
            kmax, kmin = max(ks.values()), min(ks.values())
            fit["modality_gain_ratio"] = float(kmax / kmin) if kmin else None
            fit["modality_caveat"] = (
                "Chronic (10-min average) and streaming (3000 ms) LFP power use different averaging "
                "windows and are NOT pooled; their LSB/µV² gains differ by %.1fx. A deployment "
                "threshold must use the streaming-class gain (closest to the 1200 ms aDBS detector), "
                "NOT the chronic trend." % (kmax / kmin if kmin else float("nan")))

    # --- THRESHOLD-MODE COMPATIBILITY (audit: 64-pt Single Threshold is a different band integral) ---
    # This conversion is built from 256-pt-equivalent band power (chronic Timeline + 3000 ms streaming
    # both 256-pt FFT). Per white paper Table 1, Single Threshold uses a 64-pt FFT — a different set of
    # frequency bins — so this k is NOT valid for it. Expose the per-mode verdict so the deployment
    # module can compute a threshold for Dual / Single-Inverse but DECLINE Single Threshold rather than
    # silently mis-scale it.
    fit["conversion_fft_size"] = analytics.CONVERSION_FFT_SIZE
    fit["threshold_mode_compat"] = {
        m: {
            "fft_size": v["fft_size"],
            "averaging_ms_adaptive": v["averaging_ms"][0],
            "fft_update_hz_adaptive": v["fft_update_hz"][0],
            "adaptive": v["adaptive"],
            "adaptive_band_hz": list(v["adaptive_band_hz"]),
            "convertible": (v["fft_size"] == analytics.CONVERSION_FFT_SIZE),
            "reason": ("256-pt FFT matches this calibration" if v["fft_size"] == analytics.CONVERSION_FFT_SIZE
                       else "%d-pt FFT integrates a different band than the 256-pt calibration; "
                            "LFP Power is not comparable across FFT sizes — recapture calibration in "
                            "this mode before deploying a threshold." % v["fft_size"]),
        }
        for m, v in analytics.THRESHOLD_MODES.items()
    }
    fit["compatible_threshold_modes"] = list(analytics.COMPATIBLE_THRESHOLD_MODES)
    return fit


def psd_lsb_conversion_model(request_data):
    """Return the FROZEN per-participant PSD->LSB conversion model + plot payload for the deployment
    panel. Unlike band_psd_lsb_conversion (which refits one band live from time-matched streams),
    this serves the reviewed, frozen model: per-channel common slope, per-frequency gain anchor
    (intercept = LSB at 1 uV^2), pooled fallback gain, and the cluster scatter for each fittable
    channel so the panel can draw (a) gain-anchor-vs-frequency per channel and (b) LSB-vs-PSD per
    channel colored by frequency.

    Request: ParticipantId OR Participant (the participant CODE, e.g. RCS08).
    Output: {available, participant, schema, pipeline, channels:[{channel, fittable, common_slope_b,
             r2, channel_pooled_k, bands:[{center_hz, lsb_at_1uv2, intercept_a, intercept_ci, n}]}]}.
    """
    from modules.Biomarkers.routines import psd_lsb_model as _plm
    participant = request_data.get("Participant") or request_data.get("ParticipantId")
    if not participant:
        return {"available": False, "reason": "Participant (code) required"}
    # ParticipantId may be a uid; resolve to the participant code if so.
    code = participant
    P = models.Participant.find(uid=participant)
    if P is not None:
        code = getattr(P, "code", None) or getattr(P, "name", None) or participant
    return _plm.model_plot_payload(code)


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


def _modeled_lsb_threshold_estimate(thr_lsb, modeled_thr, n_modeled, center_hz, percentile):
    """Shared modeled-LSB fallback (audit: deployment_fallback).

    When the device never sensed THIS (channel, band) long enough to read a deployable threshold
    straight off its own native LSB Timeline (`thr_lsb is None`), return the modeled LSB estimate and
    flag it ESTIMATED, so a clinician never mistakes a modeled threshold for a measured one. Returns the
    `thr_estimate` dict (or None).

    Both deployment endpoints call THIS one function so the measured→modeled fallback can never drift
    between the per-panel LSB readout (band_lsb_and_power) and the one-shot sign-off (deployment_summary).

    SINGLE modeled tier (`modeled_timeline`): the caller models the LSB line off the RAW µV TD the ROC
    was built from, AT the ROC's own band center (availability.modeled_lsb_at_center — transform ×352.62
    / bridge ≈73.63), and passes the percentile-anchored value in as `modeled_thr`. This is units-
    consistent (no µV²↔LSB conversion of the z-scored cut-point) and covers any band the ROC can score.
      (The old TIER-2 frozen-model-on-µV²-cut-point and TIER-3 population-constant k=269 tiers were both
       retired 2026-06-28: when there is no TD/PSD for the channel `modeled_thr` is None and the modeled
       threshold is INDETERMINATE, fail-closed, rather than a units-mismatched or population-average guess.)

    `thr_lsb` (measured native threshold) ALWAYS wins; this is only consulted when it is None.
    """
    thr_estimate = None
    # TIER 1 of the fallback ladder: the MODELED-LSB Timeline (psd_modeled). When the device never
    # sensed this band natively but the montage-survey sweeps DID give us calibrated modeled LSB
    # points in-band (transform×352.62 — the hollow diamonds on the timeline), read the threshold off
    # those at the same percentile, the SAME way the native path reads it. This is the closest thing
    # to a measured threshold for an unsensed band — a real per-contact LSB time series — so it
    # outranks the µV²-cut-point model below. Flagged modeled so the sign-off card never mistakes it
    # for a sensed value.
    if thr_lsb is None and modeled_thr is not None:
        # Shared definition of "outside the validated calibration range" — the SAME predicate the
        # frozen per-band model uses (analytics._freq_extrapolated mirrors psd_lsb_model._freq_extrapolated,
        # asserted equal by test), so the sign-off card's extrapolation warning is consistent across tiers.
        fextrap = analytics._freq_extrapolated(center_hz)
        note = ("Device never sensed this band; threshold read from the MODELED LSB timeline — the "
                "montage/survey sweeps converted via the transform DSP × %.2f LSB/µV² (the same "
                "calibrated series shown as hollow diamonds on the timeline), at the %g-th percentile "
                "of %d in-band modeled points. Confirm live on the device Timeline before deploying."
                % (analytics.LSB_PER_UV2_TRANSFORM, percentile, n_modeled))
        if fextrap:
            note += (" EXTRAPOLATED: outside the validated %.1f–%.1f Hz range." % (
                analytics.LSB_VALIDATED_HZ_LO, analytics.LSB_VALIDATED_HZ_HI))
        sigma = analytics.MODELED_LSB_SIGMA_FOLD
        thr_estimate = {
            "estimated_upper_lsb": modeled_thr,
            "estimated_upper_lsb_lo": round(modeled_thr / sigma, 1),
            "estimated_upper_lsb_hi": round(modeled_thr * sigma, 1),
            "sigma_fold": round(float(sigma), 3),
            "tier": "modeled_timeline", "k_effective": analytics.LSB_PER_UV2_TRANSFORM,
            "slope_b": None, "model_center_hz": center_hz,
            "r2": None, "n_modeled_points": n_modeled,
            "freq_extrapolated": fextrap,
            "validated_hz_range": [analytics.LSB_VALIDATED_HZ_LO, analytics.LSB_VALIDATED_HZ_HI],
            "note": note,
            "method": "modeled from montage/survey LSB timeline (transform DSP × k=352.62)",
        }
    # The old TIER-2 (per-participant frozen model applied to the µV² cut-point) and TIER-3
    # (population constant k=269) were both REMOVED 2026-06-28. TIER-2 fed the deployment ROC cut-point
    # — a within-(channel,source) z-scored log-power feature (dimensionless, frequently negative) —
    # into psd_lsb_model.estimate_lsb, which expects a LINEAR µV² band power: a negative z clipped to
    # 1e-12 (LSB≈0) and a positive z was silently misread as µV². The units-correct replacement is the
    # single modeled tier above: model the LSB line off the RAW TD the ROC was built from, at the ROC's
    # OWN band center (transform ×352.62 over streaming + montage TD; bridge ≈73.63 for PSD-only
    # events), then anchor by RANK (percentile) exactly like the native path — no µV²↔LSB conversion of
    # the cut-point. When there is genuinely no TD/PSD for the channel the modeled tier yields < 8
    # in-band points and `modeled_thr` stays None -> thr_estimate stays None (fail-closed), rather than
    # a units-mismatched or population-average guess.
    return thr_estimate


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
    # Include the montage-survey TD so the MODELED LSB tier (psd_modeled, transform×352.62 — the same
    # hollow-diamond series the timeline draws) is available as a fallback when the device never
    # sensed THIS band natively. Mirrors deployment_summary and the timeline caller so this panel
    # sees exactly the modeled points the clinician sees on the timeline.
    psd_list = _load_recordings(core["participant_uid"], AVAILABILITY_PSD_TYPES)
    # ALL raw-uV TD for the modeled tier: BrainSense streaming TD + IndefiniteStream (TIMEDOMAIN_TYPES)
    # AND the montage/survey sweeps (psd_list). The exploration timeline already pools every TD product
    # into the modeled LSB; the deployment fallback must see the same superset so no modeled point is
    # dropped just because the band was only ever streamed, never montage-swept. Power-domain records
    # (chronic/powerdomain) are NOT raw TD and are excluded by the helper's fs/name guards.
    streaming_td = _load_recordings(core["participant_uid"], TIMEDOMAIN_TYPES)
    td_for_modeled = list(streaming_td or []) + list(psd_list or [])
    sensing_hz = analytics.power_center_freqs(pd_list)
    lsb = _av.lsb_series(chronic_list, pd_list,
                         montage_td_recordings=psd_list, sensing_hz_by_channel=sensing_hz)
    half = band_width_hz / 2.0
    threshold_lsb = {"available": False, "reason": "not computed"}
    band_lsb_vals = None                  # NATIVE (device-sensed) in-band LSB
    thr_lsb = None; n_native = 0
    modeled_thr = None; n_modeled = 0     # MODELED in-band LSB (psd_modeled tier)
    series = lsb.get(channel) or lsb.get(analytics.format_channel(channel)["short"])
    if series is not None:
        y = np.asarray(series.get("y"), dtype=float)
        hz = np.asarray(series.get("center_hz"), dtype=float)
        modeled_flag = np.asarray(series.get("modeled"), dtype=object)
        bmask = np.isfinite(y) & np.isfinite(hz) & (hz >= center_hz - half) & (hz < center_hz + half)
        # NATIVE (sensed) points only: exclude modeled psd_modeled samples so a measured threshold is
        # never contaminated by a modeled one (native is always preferred for the deployable number).
        is_modeled = (np.array([bool(m) for m in modeled_flag]) if modeled_flag.size == y.size
                      else np.zeros(y.size, bool))
        band_lsb_vals = y[bmask & ~is_modeled]
        n_native = int(band_lsb_vals.size)
    # MODELED in-band points: model the LSB line off the RAW µV TD the ROC was built from, AT THE ROC's
    # own band center (transform ×352.62 over the montage/survey TD; bridge ≈73.63 for PSD-only events),
    # then anchor by percentile like native. Universal — covers any band the ROC can score, not only the
    # montage's configured sensing bands — and units-consistent (replaces the retired µV²-cut-point
    # estimate_lsb fallback, removed 2026-06-28). `td_for_modeled` is ALL raw-µV TD (streaming +
    # montage/survey); chronic/powerdomain are power-domain, not TD, and excluded by the helper guards.
    # Used only if there's no native threshold.
    mvals = _av.modeled_lsb_at_center(channel, center_hz,
                                      td_recordings=td_for_modeled,
                                      psd_recordings=None, half_hz=half)
    n_modeled = int(mvals.size)
    if mvals.size >= 8 and percentile is not None:
        modeled_thr = round(float(np.percentile(mvals, percentile)), 1)
    if band_lsb_vals is not None and band_lsb_vals.size >= 20 and percentile is not None:
        # MEASURED, native device-sensed threshold — the deployable number, always preferred.
        thr_lsb = float(np.percentile(band_lsb_vals, percentile))
        threshold_lsb = {
            "available": True, "estimated": False,
            "method": "percentile-anchored on device Timeline LSB",
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
        # No native threshold: default to the MODELED LSB estimate via the shared fallback ladder
        # (single modeled tier: LSB line modeled off the raw TD at the ROC band — transform ×352.62 /
        # bridge ≈73.63 — then percentile-anchored; population-constant k=269 tier retired 2026-06-28,
        # so an uncovered band is fail-closed). The IDENTICAL helper deployment_summary uses, so the
        # per-panel number can never drift from the sign-off card.
        # Flagged estimated=True so the frontend renders it with its ESTIMATED tier + ±1σ band and
        # never as a measured value (audit C8 fail-closed: a modeled value is for PLANNING, not a
        # measured prerequisite).
        thr_estimate = _modeled_lsb_threshold_estimate(
            thr_lsb, modeled_thr, n_modeled, center_hz, percentile)
        n_band = int(band_lsb_vals.size) if band_lsb_vals is not None else 0
        if thr_estimate is not None:
            threshold_lsb = {
                "available": True, "estimated": True,
                "method": thr_estimate["method"],
                "tier": thr_estimate["tier"],
                "upper_lsb": thr_estimate["estimated_upper_lsb"], "lower_lsb": None,
                "upper_lsb_lo": thr_estimate["estimated_upper_lsb_lo"],
                "upper_lsb_hi": thr_estimate["estimated_upper_lsb_hi"],
                "sigma_fold": thr_estimate["sigma_fold"],
                "percentile": (round(percentile, 1) if percentile is not None else None),
                "n_timeline_samples": n_band,
                "n_modeled_points": thr_estimate.get("n_modeled_points", n_modeled),
                "freq_extrapolated": thr_estimate.get("freq_extrapolated", False),
                "validated_hz_range": thr_estimate.get("validated_hz_range"),
                "k_effective": thr_estimate.get("k_effective"),
                "r2": thr_estimate.get("r2"),
                "note": thr_estimate["note"],
            }
        else:
            threshold_lsb = {
                "available": False, "estimated": False,
                "reason": (f"device sensed this band only {n_band} times, and no modeled LSB or "
                           "Phase-B cut-point was available to estimate from"
                           if percentile is not None
                           else "no Phase-B cut-point supplied (Cutpoint param)"),
                "n_timeline_samples": n_band,
                "n_modeled_points": n_modeled,
                "hint": ("This band is off the device's programmed sensing range (the Percept "
                         "adaptive band is 8–30 Hz) and no montage/survey sweep covered it, so "
                         "there is neither a native nor a modeled LSB anchor here. Record a montage "
                         "sweep or stream this band to obtain a deployable threshold."),
            }

    # ---- 1b) recommended-vs-currently-programmed delta (audit C10) ----
    # The task here is tuning an EXISTING device setting, so a recommended LSB number alone forces the
    # programmer to context-switch to the device to know whether it is a small nudge or a large change.
    # Surface the currently-programmed adaptive UPPER threshold for THIS channel's hemisphere (same LFP
    # units as the recommendation, present only when closed loop is active on that hemisphere) and the
    # signed delta. Defensive: any failure leaves recommended_vs_programmed unavailable, never raises.
    recommended_vs_programmed = {"available": False,
                                 "reason": "no active closed-loop program on this hemisphere"}
    try:
        Participant = models.Participant.find(uid=core["participant_uid"])
        prog = _programmed_adaptive_thresholds(Participant) if Participant else {}
        hemi = analytics.format_channel(channel).get("hemisphere")
        ph = prog.get(hemi) if hemi else None
        if ph and threshold_lsb.get("available") and threshold_lsb.get("upper_lsb") is not None:
            rec = float(threshold_lsb["upper_lsb"])
            prog_upper = ph.get("upper")
            delta = (rec - float(prog_upper)) if prog_upper is not None else None
            pct = ((delta / float(prog_upper) * 100.0) if (delta is not None and prog_upper) else None)
            recommended_vs_programmed = {
                "available": True,
                "hemisphere": hemi,
                "recommended_upper_lsb": round(rec, 1),
                "programmed_upper_lsb": (round(float(prog_upper), 1) if prog_upper is not None else None),
                "programmed_lower_lsb": (round(float(ph.get("lower")), 1) if ph.get("lower") is not None else None),
                "delta_lsb": (round(delta, 1) if delta is not None else None),
                "delta_pct": (round(pct, 1) if pct is not None else None),
                "direction": (None if delta is None else
                              ("raise" if delta > 0 else "lower" if delta < 0 else "unchanged")),
                "programmed_status": ph.get("status"),
                "programmed_date": ph.get("date"),
                "note": ("Recommended threshold vs the value currently programmed on the device for this "
                         "hemisphere (same device LFP-power units). Positive delta = raise the upper "
                         "threshold (stim engages later); negative = lower it (stim engages sooner)."),
            }
        elif ph:
            recommended_vs_programmed = {
                "available": False, "hemisphere": hemi,
                "programmed_upper_lsb": (round(float(ph.get("upper")), 1) if ph.get("upper") is not None else None),
                "reason": "a closed-loop program is active but no deployable recommended LSB threshold to compare",
            }
    except Exception as _e:  # noqa: BLE001 — therapy metadata must never break the LSB report
        recommended_vs_programmed = {"available": False, "reason": f"programmed-threshold lookup failed: {_e}"}

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
            # audit C4: pass the de-folded CI lower bound so power is reported as a band and the
            # gate reads the conservative end (never powered on the optimistic point AUC alone).
            # audit C1 guard: the "powered/beats-chance" gate reads the DE-FOLDED percentile lower
            # bound (auc_lo_defold), NOT the BCa headline bound — BCa's bias term re-floors a null band
            # at ~0.5, which must never let absence-of-signal read as significance. Falls back to the
            # BCa bound only if the guard is absent (CI suppressed below the valid-replicate floor).
            _gate_auc_lo = roc.get("auc_lo_defold", roc.get("auc_lo"))
            power = analytics.auc_power(roc["auc"], n_pos_eff, n_neg_eff, auc_lo=_gate_auc_lo,
                                        design_effect=roc.get("deff", 1.0))

    # ---- 4) THRESHOLD-MODE awareness (audit: mode determines FFT size + adaptive averaging) --------
    # The percentile-anchored threshold above is read off the device Timeline LSB, which is a 10-MINUTE
    # average. The controller, once adapting, recomputes LFP Power at the chosen mode's averaging window
    # (Dual 1200 ms / Single 100 ms / Single-Inverse is sensing-only). A given upper percentile of the
    # 10-min distribution is NOT the same LSB as that percentile of the shorter-averaged distribution
    # (shorter averaging => fatter tails => higher upper-percentile LSB), so the Timeline-anchored
    # number is a STARTING POINT that must be read in the mode it will run in. And Single Threshold uses
    # a 64-pt FFT — a different band integral — so the Timeline (256-pt) anchor does not even apply.
    threshold_mode = _threshold_mode_block(rd, center_hz, threshold_lsb)

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
        "threshold_mode": threshold_mode,
        "recommended_vs_programmed": recommended_vs_programmed,
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
    # Surface the formal band×era LRT (band_stim_stability) alongside the per-era refit so the panel
    # verdict can key on the test the module already runs, not raw point-AUC spread (audit C3).
    st = core.get("stim") or {}
    if isinstance(by_era, dict) and by_era.get("available"):
        by_era["stim_lrt"] = {
            "available": bool(st.get("available")),
            "lrt_p": _ff(st.get("lrt_p")) if st.get("available") else None,
            "stim_stable": (st.get("stim_stable") if st.get("available") else None),
        }
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
    # Forward-chaining / out-of-sample validation (audit C2): train on past weeks, test forward, so
    # the deploy card carries a held-out AUC beside the in-sample number and a 'forward-validated'
    # gate. Orientation + Youden threshold are fit on the train fold ONLY (no look-ahead).
    forward = analytics.deployment_forward_chaining(
        pooled, channel, center_hz, band_width_hz=band_width_hz,
        strategy=core["label_strategy"], low_pct=core["low_pct"], high_pct=core["high_pct"],
        n_boot=n_boot)
    # Audit [18]: per-week threshold-drift diagnostic. Does the optimal Youden cut-point move
    # systematically over calendar time? A single fixed device threshold fit on all data would be
    # miscalibrated in later weeks if so. Fail-closed to 'not_assessed' when too few weeks qualify.
    drift = analytics.threshold_drift_by_week(
        pooled, channel, center_hz, band_width_hz=band_width_hz,
        strategy=core["label_strategy"], low_pct=core["low_pct"], high_pct=core["high_pct"])

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
    # Include the montage-survey TD so the MODELED LSB tier (psd_modeled, transform×352.62 — the same
    # hollow-diamond series the timeline draws) is available as a fallback when the device never
    # sensed THIS band natively. Mirrors the timeline caller so the deployment fallback sees exactly
    # the modeled points the clinician sees on the timeline.
    psd_list = _load_recordings(core["participant_uid"], AVAILABILITY_PSD_TYPES)
    # ALL raw-uV TD for the modeled tier (see band_lsb_and_power): BrainSense streaming TD +
    # IndefiniteStream (TIMEDOMAIN_TYPES) AND the montage/survey sweeps. Mirror the exploration
    # timeline's TD superset so no modeled point is dropped for a streamed-only band.
    streaming_td = _load_recordings(core["participant_uid"], TIMEDOMAIN_TYPES)
    td_for_modeled = list(streaming_td or []) + list(psd_list or [])
    sensing_hz = analytics.power_center_freqs(pd_list)
    lsb = _av.lsb_series(chronic_list, pd_list,
                         montage_td_recordings=psd_list, sensing_hz_by_channel=sensing_hz)
    half = band_width_hz / 2.0
    series = lsb.get(channel) or lsb.get(analytics.format_channel(channel)["short"])
    thr_lsb = None; n_tl = 0
    modeled_thr = None; n_modeled = 0      # MODELED-LSB fallback (psd_modeled tier)
    if series is not None:
        y = np.asarray(series.get("y"), dtype=float); hz = np.asarray(series.get("center_hz"), dtype=float)
        src = np.asarray(series.get("source"), dtype=object)
        modeled_flag = np.asarray(series.get("modeled"), dtype=object)
        bandm = np.isfinite(y) & np.isfinite(hz) & (hz >= center_hz - half) & (hz < center_hz + half)
        # NATIVE (sensed) points only: exclude the modeled psd_modeled samples so a measured threshold
        # is never contaminated by a modeled one (native is always preferred for the deployable number).
        is_modeled = np.array([bool(m) for m in modeled_flag]) if modeled_flag.size == y.size \
            else np.zeros(y.size, bool)
        native_m = bandm & ~is_modeled
        vals = y[native_m]; n_tl = int(vals.size)
        if vals.size >= 20 and percentile is not None:
            thr_lsb = round(float(np.percentile(vals, percentile)), 1)
    # MODELED points in-band: model the LSB line off the RAW µV TD the ROC was built from, AT THE ROC's
    # own band center (transform ×352.62 over the montage/survey TD; bridge ≈73.63 for PSD-only events),
    # then anchor by percentile like native. Universal across any band the ROC can score and units-
    # consistent (replaces the retired µV²-cut-point estimate_lsb fallback, removed 2026-06-28).
    # `td_for_modeled` is ALL raw-µV TD (streaming + montage/survey); chronic/powerdomain are
    # power-domain, not TD. Gathered regardless; used only if there's no native threshold (below).
    mvals = _av.modeled_lsb_at_center(channel, center_hz,
                                      td_recordings=td_for_modeled,
                                      psd_recordings=None, half_hz=half)
    n_modeled = int(mvals.size)
    if mvals.size >= 8 and percentile is not None:
        modeled_thr = round(float(np.percentile(mvals, percentile)), 1)

    # Fallback (audit: deployment_fallback): the device never sensed THIS (channel, band) long
    # enough to read a threshold straight off its own LSB Timeline (thr_lsb is None) -- but we still
    # have modeled LSB sources. Delegate to the SHARED ladder so this path can never drift from the
    # per-panel LSB readout (band_lsb_and_power) which calls the identical helper.
    thr_estimate = _modeled_lsb_threshold_estimate(
        thr_lsb, modeled_thr, n_modeled, center_hz, percentile)

    # Native-vs-modeled cross-check: REMOVED 2026-06-28 with the k=269 population constant. It compared
    # the measured Timeline LSB against lsb_from_uv2(cutpoint, k=269); with k=269 retired there is no
    # population-constant model of a sensed band's cut-point to compare against (the frozen per-participant
    # model is per-band, not a single scalar). Kept as None so the payload contract is unchanged.
    native_modeled_check = None

    # Power on the clustered effective n.
    power = {"available": False, "reason": "ROC unavailable"}
    if roc.get("available"):
        n_clu = int(roc.get("n_clusters") or 0); prev = roc.get("prevalence")
        if n_clu >= 4 and prev is not None and 0 < prev < 1:
            # audit C4: power band on the de-folded CI lower bound; gate reads the conservative end.
            n_pos = int(round(n_clu * prev))
            # audit C1 guard: gate reads the de-folded percentile lower bound, not the BCa bound.
            _gate_auc_lo = roc.get("auc_lo_defold", roc.get("auc_lo"))
            power = analytics.auc_power(roc["auc"], n_pos, n_clu - n_pos, auc_lo=_gate_auc_lo,
                                        design_effect=roc.get("deff", 1.0))

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
    # Each gate carries a tri-state `state` ("pass" | "fail" | "indeterminate") AND a `necessary`
    # flag (audit C8). `pass` (bool) is retained for back-compat but is True only for state=="pass",
    # so absence-of-evidence (indeterminate) never counts as a pass. NECESSARY gates are the hard
    # prerequisites to program at all (a validated band, an in-range adaptive band, a deployable
    # threshold); SUPPORTIVE gates strengthen the case but do not by themselves block. "Ready to
    # program" requires every NECESSARY gate to pass — not merely a high passed-count.
    def _gate(key, label, state, detail, necessary=False):
        return {"key": key, "label": label, "state": state,
                "pass": state == "pass", "necessary": bool(necessary), "detail": detail}

    gates = []
    gates.append(_gate("validated", "Band validated (mixed-effects)",
                       "pass" if (verdict and "VALIDATED" in str(verdict)) else "fail",
                       verdict, necessary=True))
    # The gate checks the band EDGES against the device's adaptive range, not merely the centre --
    # matching ClosedLoopDeployment/constraints.py's D08 rule (band_edges/permitted_band_hz). A 5 Hz
    # band centred at 10 Hz has its centre inside 8-30 Hz but its lower edge at 7.5 Hz, outside it;
    # this used to read `adaptive_valid` (centre-only), which would have shown "pass" for that band
    # even though D08 -- the rule that actually decides whether the device will accept it -- refuses
    # it. `adaptive_valid` (centre-only) is left untouched for `_suggested_percept_mode` above, which
    # answers a different question (which Percept mode to recommend, matching
    # `_threshold_mode_block`'s own centre-based per-mode check) -- only this gate's pass/fail is
    # changed to the edge rule. See `_deployment_summary_adaptive_band_gate` for the pure logic,
    # pinned by its own test.
    _ab_state, _ab_detail, *_ = _deployment_summary_adaptive_band_gate(center_hz, band_width_hz)
    gates.append(_gate("adaptive_band", "In Percept adaptive range (8–30 Hz)",
                       _ab_state, _ab_detail, necessary=True))
    # A MEASURED threshold passes. A MODELED estimate (device never sensed this band) is
    # "indeterminate" -- usable for planning but NOT a measured prerequisite, so it can never count
    # toward "ready to program" on its own (audit C8 fail-closed discipline). Neither -> fail.
    if thr_lsb is not None:
        _thr_state, _thr_detail = "pass", f"power ≥ {thr_lsb} LSB (measured on device Timeline)"
    elif thr_estimate is not None:
        _thr_state = "indeterminate"
        _thr_detail = (f"power ≥ {thr_estimate['estimated_upper_lsb']} LSB ESTIMATED "
                       f"({thr_estimate['tier']} tier) — device never sensed this band; "
                       "modeled from µV² cut-point, confirm by sensing before programming")
        if thr_estimate.get("freq_extrapolated"):
            # Out-of-range high-gamma (e.g. 55.5 Hz): the PSD->LSB conversion itself is extrapolated
            # beyond its calibrated 7.8-28.3 Hz range, so the LSB value is even less trustworthy than
            # an in-range estimate. Surface it on the sign-off detail, not just in the nested note.
            _vr = thr_estimate.get("validated_hz_range") or [analytics.LSB_VALIDATED_HZ_LO,
                                                             analytics.LSB_VALIDATED_HZ_HI]
            _thr_detail += (f" ⚠ band is OUTSIDE the validated {_vr[0]:.1f}–{_vr[1]:.1f} Hz "
                            "conversion range — LSB is EXTRAPOLATED (gain not band-flat); needs "
                            "streaming calibration at this center frequency")
    else:
        _thr_state, _thr_detail = "fail", f"device sensed this band {n_tl} times"
    gates.append(_gate("deployable_threshold", "Deployable LSB threshold available",
                       _thr_state, _thr_detail, necessary=True))
    gates.append(_gate("credible_ci", "Credible effect-size CI",
                       "pass" if credible else "fail",
                       f"OR CI [{g.get('or_lo')}, {g.get('or_hi')}]"))
    # Stim-stability gate (audit C8, corrected per decision 82): FAIL-CLOSED / ABSTAIN, never
    # fail-open. This USED TO read the retired `stim_stable` boolean (`p_lrt >= 0.05`), which is a
    # failure to reject rather than evidence of stability -- with three eras and modest counts it
    # reads "stable" precisely when the test has no power, which is the situation in which a false
    # reassurance is most costly on a page that gates programming a device. `stability_verdict`
    # (from `analytics.stability_equivalence`, computed on the SAME `st` dict, no extra call) is the
    # three-way answer that exists specifically to fix this: "stable" only when the largest
    # between-era difference is demonstrably smaller than the declared equivalence margin,
    # "stim-dependent" when the interaction LRT rejects, "inconclusive" when the LRT does not reject
    # but the interval is too wide to tell a stable band from a materially unstable one -- and
    # "inconclusive" must render as indeterminate, not pass, or this gate reintroduces the exact
    # failure mode it exists to prevent. `ClosedLoopDeployment/stability.py`'s own
    # `finding_from_stability_result` already encodes this identical three-way mapping for the
    # ClosedLoopDeployment side of this same page; it is not imported here because
    # ClosedLoopDeployment may import Biomarkers but not the reverse (see `edges.py`'s own note on
    # this one-way rule) -- so the mapping is inlined against the same source field instead. See
    # `_deployment_summary_stim_stable_gate` for the pure logic, pinned by its own test.
    stim_state, stim_detail = _deployment_summary_stim_stable_gate(st)
    gates.append(_gate("stim_stable", "Stim-stable (band×era equivalence test)", stim_state, stim_detail))
    # audit C4: the gate passes only when the CONSERVATIVE (CI-lower-bound) power clears target, so a
    # band that looks powered on its optimistic point AUC cannot pass. Detail shows the power band.
    if power.get("available"):
        # Same present-but-null hazard as n_ratings_needed below: `.get(key, 0)` does not protect
        # against a key that exists with value None, and line ~4865 already treats the sibling
        # n_ratings_needed_hi as nullable. Coerce explicitly rather than relying on the default.
        _pc_raw = power.get("power_current")
        _pc = round(_pc_raw * 100) if _pc_raw is not None else None
        _pc_txt = f"{_pc}%" if _pc is not None else "not estimable"
        _plo = power.get("power_current_lo")
        if _plo is not None:
            _need_hi = power.get("n_ratings_needed_hi")
            # Same guard as the else-branch below: when the requirement is not achievable by
            # collecting more data, do not print a number that reads as a collection target. This
            # branch had been left unguarded, so a near-chance band WITH a CI lower bound still
            # printed its six-figure requirement.
            if power.get("status") in ("at_or_below_chance", "requirement_infeasible"):
                _powered_detail = (f"power {round(_plo*100)}%–{_pc_txt} (conservative–point AUC); "
                                   f"target power NOT achievable by collecting more data "
                                   f"(AUC indistinguishable from chance)")
            else:
                _powered_detail = (f"power {round(_plo*100)}%–{_pc_txt} (conservative–point AUC); "
                                   f"need {_need_hi if _need_hi is not None else '∞'} ratings at the CI "
                                   f"lower bound (audit C4: gate reads the conservative end)")
        else:
            # Do not print a six-figure requirement as if it were a target: at a near-chance AUC the
            # required n is finite only arithmetically (1/(AUC-0.5)^2), so it reads as a plan when it
            # is really a restatement that the band does not discriminate.
            _need_txt = power.get("n_ratings_needed")
            if power.get("status") in ("at_or_below_chance", "requirement_infeasible"):
                _powered_detail = (f"power {_pc_txt}; target power NOT achievable by collecting more "
                                   f"data (AUC indistinguishable from chance)")
            else:
                _powered_detail = (f"power {_pc_txt}, need "
                                   f"{_need_txt if _need_txt is not None else '∞'} ratings")
    else:
        _powered_detail = "n/a"
    gates.append(_gate("powered", "Adequately powered (≥80%)",
                       "pass" if (power.get("available") and not power.get("more_data_needed")) else "fail",
                       _powered_detail))
    # Forward-validated gate (audit C2): PASS only when the held-out (train-past → test-future) AUC's
    # bootstrap CI lower bound clears chance; INDETERMINATE when the record can't be split forward
    # (no held-out estimate is absence of evidence, never a pass); FAIL when the held-out CI includes
    # 0.5 (the band did not generalize forward, even if its in-sample AUC looks good).
    if not forward.get("available"):
        fwd_state = "indeterminate"
        fwd_detail = (f"no forward split available ({forward.get('reason', 'insufficient temporal span')}) "
                      "— out-of-sample generalization UNCONFIRMED")
    elif forward.get("held_out_auc_lo") is None:
        fwd_state = "indeterminate"
        fwd_detail = (f"{forward.get('n_folds')} forward fold(s) but the held-out CI is unstable "
                      "(too few independent held-out ratings) — generalization UNCONFIRMED")
    elif forward.get("beats_chance_forward"):
        fwd_state = "pass"
        fwd_detail = (f"held-out AUC {round(forward.get('held_out_auc') or 0, 2)} "
                      f"(95% CI {round(forward.get('held_out_auc_lo'), 2)}–"
                      f"{round(forward.get('held_out_auc_hi'), 2)}) over {forward.get('n_folds')} "
                      f"weekly folds clears chance vs in-sample {round(forward.get('in_sample_auc') or 0, 2)}")
    else:
        fwd_state = "fail"
        _ho = forward.get("held_out_auc") or 0.0
        _is = forward.get("in_sample_auc") or 0.0
        _ci = (f"(95% CI {round(forward.get('held_out_auc_lo'), 2)}–"
               f"{round(forward.get('held_out_auc_hi'), 2)})")
        if _ho <= 0.55:
            # The held-out point estimate itself collapsed to (or below) chance: the in-sample
            # direction does not predict the future — the closed-loop failure C2 exists to catch.
            fwd_detail = (f"held-out AUC {round(_ho, 2)} {_ci} collapses to chance while in-sample is "
                          f"{round(_is, 2)} (optimism {round(forward.get('optimism') or 0, 2)}); band "
                          "did NOT generalize forward — do not program on the in-sample number.")
        else:
            # The held-out POINT estimate holds (≈ in-sample) but its CI lower bound dips below 0.5:
            # underpowered to PROVE it clears chance, not a demonstrated failure to generalize.
            fwd_detail = (f"held-out AUC {round(_ho, 2)} {_ci} holds near in-sample {round(_is, 2)} "
                          "(point estimate generalizes) but its CI does not yet exclude chance — "
                          "UNDERPOWERED forward; more weeks of ratings needed to confirm.")
    gates.append(_gate("forward_validated", "Forward-validated (held-out AUC clears chance)",
                       fwd_state, fwd_detail))

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
    # Audit [18]: calendar-time threshold drift. A significant weekly trend in the optimal cut-point
    # means a single fixed device threshold will be miscalibrated in later weeks.
    if drift.get("available") and drift.get("drift_flag"):
        caveats.append(f"Threshold drift over time: the optimal cut-point trends "
                       f"{round(drift.get('slope_per_week') or 0, 3):+} /week "
                       f"(p={round(drift.get('slope_p') or 1, 3)}) across "
                       f"{drift.get('n_weeks_qualifying')} weeks — a fixed device threshold will be "
                       "miscalibrated in later weeks; plan periodic recalibration.")
    if power.get("available") and power.get("more_data_needed"):
        # `n_ratings_needed` is legitimately None when the power calculation flags underpowering but
        # cannot SOLVE for the required N — an observed effect at or near chance has no finite
        # sample size that reaches 80%. `.get(key, 0)` does NOT protect against this: the default
        # only fires when the key is ABSENT, and here it is present and null, so the subtraction
        # raised TypeError and took down the whole deployment summary (both deployment_summary
        # tests, 2026-08-30). Report the honest state instead of inventing a number.
        _need = power.get("n_ratings_needed")
        _have = power.get("n_ratings_current")
        _status = power.get("status")
        _have_txt = f" Currently {int(_have)} ratings." if _have is not None else ""
        if _status == "at_or_below_chance" or _need is None or _have is None:
            caveats.append(
                "Underpowered, and the requirement is UNDEFINED rather than large: at the observed "
                "discrimination (AUC at or below chance) no finite number of additional ratings "
                "reaches 80% power. This band does not separate the pain classes; collecting more "
                "data will not change that." + _have_txt)
        elif _status == "requirement_infeasible":
            # The number is finite but only arithmetically. Required n scales as 1/(AUC-0.5)^2, so a
            # near-chance AUC yields a requirement no study can meet; quoting it as a shortfall
            # implies more data would rescue the biomarker.
            # Quote the requirement the STATUS was decided on. Feasibility reads the conservative
            # CI-lower-bound requirement when one exists (fail-closed, matching the gate), so
            # quoting the point requirement here would cite a different, smaller number than the
            # one that triggered the verdict.
            _need_hi_c = power.get("n_ratings_needed_hi")
            _deciding = _need_hi_c if (power.get("auc_lo") is not None and _need_hi_c is not None) else _need
            _which = ("at the CI lower bound" if _deciding is not _need else "at the point AUC")
            caveats.append(
                f"Underpowered and NOT rescuable by more data: 80% power would require "
                f"{int(_deciding):,} independent ratings {_which}, beyond the "
                f"{int(power.get('feasible_n_max') or 0):,} ceiling for a realistic "
                f"single-participant study. Because required n scales as 1/(AUC-0.5)^2, this is a "
                f"restatement of 'indistinguishable from chance', not a collection target." + _have_txt)
        else:
            caveats.append(f"Underpowered: ~{int(_need) - int(_have)} "
                           "more independent pain ratings needed for 80% power.")
    caveats.append("Selection bias: this band was chosen from a sweep on the same data; the OR/AUC are "
                   "optimistic. Out-of-sample / prospective confirmation is the honest test.")
    # Audit C2: surface the forward-chaining result as a caveat so the in-sample optimism is
    # quantified, not just asserted.
    if forward.get("available") and forward.get("held_out_auc") is not None:
        if forward.get("beats_chance_forward"):
            caveats.append(
                f"Forward-validated: training on past weeks and testing forward, the held-out AUC is "
                f"{round(forward.get('held_out_auc'), 2)} (95% CI {round(forward.get('held_out_auc_lo'), 2)}–"
                f"{round(forward.get('held_out_auc_hi'), 2)}) over {forward.get('n_folds')} weekly folds vs "
                f"in-sample {round(forward.get('in_sample_auc'), 2)} (forward optimism "
                f"{round(forward.get('optimism') or 0, 2)}). This is the out-of-sample number to weight.")
        elif (forward.get("held_out_auc") or 0.0) <= 0.55:
            caveats.append(
                f"FORWARD VALIDATION FAILED: held-out AUC {round(forward.get('held_out_auc'), 2)} "
                f"(95% CI {round(forward.get('held_out_auc_lo'), 2)}–{round(forward.get('held_out_auc_hi'), 2)}) "
                f"collapses to chance, although the in-sample AUC is {round(forward.get('in_sample_auc'), 2)} "
                f"(forward optimism {round(forward.get('optimism') or 0, 2)}). Training on the past does not "
                "predict the future for this band — do NOT program it as an adaptive threshold on the "
                "in-sample number alone.")
        else:
            caveats.append(
                f"Forward UNDERPOWERED: the held-out AUC {round(forward.get('held_out_auc'), 2)} holds near "
                f"in-sample {round(forward.get('in_sample_auc'), 2)} (the point estimate generalizes forward), "
                f"but its 95% CI {round(forward.get('held_out_auc_lo'), 2)}–{round(forward.get('held_out_auc_hi'), 2)} "
                "does not yet exclude chance. More weeks of pain ratings are needed to confirm forward "
                "validity before programming.")
    elif not forward.get("available"):
        caveats.append(
            f"Forward validation not possible ({forward.get('reason', 'insufficient temporal span')}): "
            "every reported AUC is in-sample. Out-of-sample generalization is UNCONFIRMED.")
    if thr_lsb is None and thr_estimate is not None:
        _src_phrase = ("read from the MODELED LSB timeline (montage/survey sweeps, transform×352.62)"
                       if thr_estimate.get("tier") == "modeled_timeline"
                       else "MODELED from the physical µV² cut-point via the frozen PSD→LSB conversion")
        caveats.append(
            f"ESTIMATED threshold ({thr_estimate['tier']} tier): the device never sensed this "
            f"(channel, band) long enough to read a threshold off its own sensed LSB Timeline. The "
            f"≥ {thr_estimate['estimated_upper_lsb']} LSB value is {_src_phrase} "
            f"({thr_estimate['note']}). Sense this band "
            "on the device to confirm before committing it as an adaptive threshold.")

    def _ff(x):
        try:
            return float(x) if x is not None and np.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    return {
        "available": True,
        "match_direction": core["match_direction"], "verdict": verdict,
        "identity": {
            # participant_uid (a string), NOT core["Participant"] (a Django model object) — the latter
            # is not JSON-serializable and made /queryDeploymentSummary 500 on every real fetch.
            "participant": core.get("participant_uid"), "hemisphere": analytics.format_channel(channel)["hemisphere"],
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
            # Advisory ramp-parameter guidance (audit C10): the closed-loop tuning surface is band +
            # threshold + RAMP. stim_stable is the tri-state value (True/False/None) the C8 gate keys
            # on — None (LRT did not converge) is treated as "not confirmed stable", i.e. conservative.
            "ramp": _ramp_guidance(
                polarity, adaptive_valid, suggested_mode,
                stim_stable=(bool(st.get("stim_stable")) if st.get("available") else None),
                power_available=bool(power.get("available"))),
        },
        "threshold": {
            "available": thr_lsb is not None, "upper_lsb": thr_lsb,
            "percentile": round(percentile, 1) if percentile is not None else None,
            "cutpoint_feature": _ff(cutpoint), "n_timeline_samples": n_tl,
            "method": "percentile-anchored on device Timeline LSB",
            # When the device never sensed this band, an ESTIMATED threshold from the frozen
            # PSD->LSB conversion model (flagged, with its fallback tier). Never overwrites a
            # measured upper_lsb; present only when `available` is False.
            "estimated": (thr_estimate is not None and thr_lsb is None),
            "estimate": thr_estimate,
            # FYI agreement check: retired 2026-06-28 with the k=269 constant; always None now (the
            # payload key is retained for API-contract stability; no frontend consumer).
            "native_modeled_check": native_modeled_check,
            # Threshold-mode awareness (audit): which Percept mode this number is valid for, the
            # FFT-size compatibility, and the 10-min-Timeline vs adaptive-averaging caveat.
            "mode": _threshold_mode_block(
                rd, center_hz,
                {"available": thr_lsb is not None, "upper_lsb": thr_lsb}),
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
        # Forward / out-of-sample validation (audit C2): the held-out AUC + CI shown beside the
        # in-sample AUC, the per-fold trace, and the optimism gap. The card reads in_sample_auc vs
        # held_out_auc to see how much the in-sample number is inflated by fitting on its own data.
        "forward": ({"available": True,
                     "in_sample_auc": _ff(forward.get("in_sample_auc")),
                     "held_out_auc": _ff(forward.get("held_out_auc")),
                     "held_out_auc_lo": _ff(forward.get("held_out_auc_lo")),
                     "held_out_auc_hi": _ff(forward.get("held_out_auc_hi")),
                     "held_out_sens": _ff(forward.get("held_out_sens")),
                     "held_out_spec": _ff(forward.get("held_out_spec")),
                     "optimism": _ff(forward.get("optimism")),
                     "beats_chance_forward": bool(forward.get("beats_chance_forward")),
                     "reliable": bool(forward.get("reliable")),
                     "n_folds": forward.get("n_folds"),
                     "n_test_clusters": forward.get("n_test_clusters"),
                     "folds": forward.get("folds"),
                     "ci_method": forward.get("ci_method"), "note": forward.get("note")}
                    if forward.get("available")
                    else {"available": False, "reason": forward.get("reason")}),
        "portability": ({"available": True, "auc_spread": _ff(by_era.get("auc_spread")),
                         "cutpoint_spread": _ff(by_era.get("cutpoint_spread")),
                         "n_eras_estimable": by_era.get("n_eras_estimable"),
                         "era_counts": by_era.get("era_counts"),
                         "eras": {k: {"auc": _ff(v.get("auc")) if v.get("available") else None,
                                      "available": v.get("available", False)}
                                  for k, v in (by_era.get("eras") or {}).items()}}
                        if by_era.get("available") else {"available": False, "reason": by_era.get("reason")}),
        # Audit [23] — explicit, single-place temporal-validity status for the exported DEVICE RECORD,
        # so a reader of the JSON never has to infer it from the nested forward/portability dicts.
        # Every field defaults to "not_assessed" when the corresponding analysis didn't run, so the
        # record is unambiguous either way. Derived from already-computed results — no new computation.
        "temporal_validity": {
            "forward_validation": (
                ("validated" if forward.get("beats_chance_forward") else "failed")
                if forward.get("available") else "not_assessed"),
            "forward_held_out_auc": _ff(forward.get("held_out_auc")) if forward.get("available") else None,
            "forward_reliable": (bool(forward.get("reliable")) if forward.get("available") else None),
            # Audit [18]: per-week cut-point drift over CALENDAR time (distinct from stim-state
            # portability below). 'stable' / 'drift_detected' / 'not_assessed'.
            "threshold_drift": (drift.get("status", "not_assessed")
                                if drift.get("available") else "not_assessed"),
            "threshold_drift_slope_per_week": (_ff(drift.get("slope_per_week"))
                                               if drift.get("available") else None),
            "threshold_drift_p": (_ff(drift.get("slope_p")) if drift.get("available") else None),
            "threshold_drift_total": (_ff(drift.get("total_drift")) if drift.get("available") else None),
            "threshold_drift_n_weeks": (drift.get("n_weeks_qualifying")
                                        if drift.get("available") else None),
            "stim_state_portability": (
                ("portable" if by_era.get("portable_by_ci") else "fragile")
                if (by_era.get("available") and by_era.get("portable_by_ci") is not None)
                else "not_assessed"),
            "note": ("forward_validation = expanding-window weekly forward-chaining held-out AUC vs "
                     "chance (audit C2). stim_state_portability = per-era CI-overlap + LRT (audit C3); "
                     "this is robustness to stim STATE. threshold_drift = OLS trend test of the weekly "
                     "Youden cut-point vs week index (audit [18]); 'drift_detected' means the cut-point "
                     "moves systematically over calendar time and a fixed device threshold needs "
                     "periodic recalibration."),
        },
        "gates": gates, "caveats": caveats,
        "n_gates_passed": int(sum(1 for x in gates if x["pass"])), "n_gates": len(gates),
        "n_gates_indeterminate": int(sum(1 for x in gates if x.get("state") == "indeterminate")),
        # "Ready to program" is gated on the NECESSARY checks alone, not the passed count: a hard
        # prerequisite failing blocks deployment even if 5 of 6 gates pass (audit C8).
        "ready_to_program": bool(all(x["pass"] for x in gates if x.get("necessary"))),
        "n_necessary": int(sum(1 for x in gates if x.get("necessary"))),
        "n_necessary_passed": int(sum(1 for x in gates if x.get("necessary") and x["pass"])),
    }


@_pro_scoped
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
        # Emit BOTH a display string `t` and an unambiguous numeric `t_epoch` (UTC seconds). `t` is
        # tz-naive UTC; a browser doing `Date.parse(t)` / `new Date(t)` on a naive string re-reads it
        # in the BROWSER's local zone, shifting the corrected instant 7-8 h and knocking PROs off the
        # PSDs in the live match preview (the "61/682 instead of 290/682" symptom). `t_epoch` is
        # zone-independent: `tt.value/1e9` treats the tz-naive UTC Timestamp as UTC (NOT .timestamp(),
        # which would re-apply a local tz). Clients should match/plot on t_epoch. (FIXHANDOUT tz.)
        pts = [{"t": str(tt), "t_epoch": _f(tt.value / 1e9), "v": _f(v)}
               for tt, v in zip(t, vals) if pd.notna(tt) and pd.notna(v)]
        if pts:
            pts.sort(key=lambda p: p["t_epoch"])
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


# =================================================================================================
# HOW WELL EACH BAND TRACKS PAIN, AT EVERY LENGTH OF SIGNAL AVERAGED INTO ONE MEASUREMENT
# =================================================================================================
#
# This serves the last section of the biomarker exploration page, above the device-scale calibration
# panels. It rides the SAME endpoint as the rest of the page (`POST /api/queryBiomarkerAnalysis`)
# with `BandTimeSweep` set, because the endpoint and its route are owned elsewhere and adding a
# second one would have meant editing a file this work does not own. When that flag is set the
# request returns the sweep ALONE and skips the whole per-channel decode the page's main panels
# need, which is what makes the section usable interactively: the expensive part, slicing the
# recording history into 3 s pieces and computing a spectrum for each, is the same memoized cache
# the page's other panels already built.
#
# THE TOP-OF-PAGE SETTINGS GOVERN THIS SECTION. Every control that changes which recording is
# matched to which pain report is read from the same request keys the main analysis reads, through
# the same helper functions, so the sweep cannot be computed against a different match policy from
# the panels above it: `MatchToleranceMin` (the eligibility radius), `AllowWindowReuse`,
# `LabelStrategy` with `PercentileLow` / `PercentileHigh` (how high pain is separated from low),
# `OutlierNMad` / `OutlierScale`, and `RedcapRecordId` / `ProcessedPRO` (which pain reports exist).
# The ONE control the section overrides is which pain score to use, because the PI asked for that
# to be chosen inside the section; it is sent as `SweepMetric` and falls back to the page's own
# `LabelMetric` when absent.
#
# THE LENGTH OF SIGNAL IS THE ONE THING SWEPT. On the page above, how much of the nearest recording
# goes into one band-power measurement is a single slider (`MatchExtentSec`). Here that quantity is
# swept over `analytics.BAND_TIME_SWEEP_SECONDS` instead of taken from the slider, which is the
# whole point of the section, so `MatchExtentSec` is deliberately NOT read.

#: The request key that asks for the sweep alone.
BAND_TIME_SWEEP_KEY = "BandTimeSweep"


def _wants_band_time_sweep(request_data):
    """Whether this request is asking for the band-by-length-of-signal sweep alone."""
    return str(request_data.get(BAND_TIME_SWEEP_KEY, "")).lower() in ("1", "true", "yes", "on")


def _band_time_sweep_power_by_seconds(pro_times, raw_cache, center_hz, *, tol_s,
                                      allow_window_reuse, seconds=None,
                                      match_direction="pro_first", channel=None):
    """One band-power matrix per length of signal, each with one row per pain report and one column
    per band centre.

    THE MATCHING IS THE MODULE'S OWN, CALLED ONCE PER LENGTH OF SIGNAL, NOT REIMPLEMENTED.
    `availability.live_lsb_spectrum_match` is the function the page's full-spectrum scan already
    uses to decide which pieces of recording serve which pain report; it takes the length of signal
    as `td_quantity_s`, so sweeping that argument is exactly what this section needs and no new
    matching rule is introduced. Calling it once per length is cheap because the expensive work --
    slicing the recording history into 3 s pieces and computing a spectrum for each -- happened when
    the cache was built and is not repeated.

    THERE IS NO LOOP OVER BANDS ANYWHERE. Each call returns every band centre in the cache for every
    pain report, so the band axis arrives as columns of a matrix and every statistic downstream is a
    matrix operation across all bands at once.

    A `channel` that `analytics.BAND_SWEEP_LSB_CEILINGS` covers takes a different route entirely:
    `availability.live_lsb_band_medians_by_length` drops each contaminated 3 s piece BEFORE any of
    them are averaged and backfills with the next closest clean one, so no outlier rule is left to
    apply to the finished cell (PI, 2026-09-09). Every other channel keeps the original path
    unchanged, which is what gates this to the sweep's own real contacts and leaves every other
    panel that calls `live_lsb_spectrum_match` reading exactly what it read before.

    Returns `(power_by_seconds, stats_by_seconds, centers_used_hz, column_index, chunk_exclusion)`.
    `chunk_exclusion` is `None` on the original path.
    """
    secs = list(analytics.BAND_TIME_SWEEP_SECONDS if seconds is None else seconds)
    cache_centers = np.asarray(raw_cache.get("centers_hz") or [], dtype=float)
    centers = (analytics.sweep_center_freqs(cache_centers) if center_hz is None
               else np.atleast_1d(np.asarray(center_hz, dtype=float)))
    if centers.size == 0 or cache_centers.size == 0:
        return {}, {}, centers, np.asarray([], dtype=int), None
    # Column positions of the swept centres inside the cache's own centre list, so the matrix
    # columns and the reported centres cannot drift apart.
    col = np.asarray([int(np.argmin(np.abs(cache_centers - c))) for c in centers], dtype=int)
    pt = np.asarray(pro_times, dtype=float)

    ceiling_table = analytics.BAND_SWEEP_LSB_CEILINGS.get(channel) if channel else None
    if ceiling_table:
        ceilings = [ceiling_table.get(round(float(c), 1), np.inf) for c in centers]
        power, excl, stats = availability.live_lsb_band_medians_by_length(
            pt, raw_cache, tol_s=tol_s, lengths_s=secs, centers_hz=centers,
            band_ceilings=ceilings, allow_window_reuse=allow_window_reuse,
            match_direction=match_direction)
        return power, stats, centers, col, excl

    power, stats = {}, {}
    for s in secs:
        recs, st = availability.live_lsb_spectrum_match(
            pt, raw_cache, tol_s=tol_s, td_quantity_s=float(s),
            allow_window_reuse=allow_window_reuse, match_direction=match_direction)
        mat = np.full((pt.size, centers.size), np.nan, dtype=float)
        for i, rec in enumerate(recs or []):
            if i >= pt.size:
                break
            vec = rec.get("lsb")
            if not vec:
                continue
            v = np.asarray([np.nan if x is None else float(x) for x in vec], dtype=float)
            take = col[col < v.size]
            mat[i, : take.size] = v[take]
        power[float(s)] = mat
        stats[float(s)] = st
    return power, stats, centers, col, None


def _band_time_sweep_channels(raw_by_channel, pro_times, *, tol_s, allow_window_reuse,
                              pain_values, label_strategy, low_pct, high_pct,
                              outlier_n_mad, outlier_scale, metric_key, metric_label,
                              n_perm=None, n_boot=None, seed=0, match_direction="pro_first",
                              region_map=None):
    """Run the sweep for every sensing contact pair that has a cache, one entry per pair.

    ONE CONTACT PAIR IS ONE ANSWER, never pooled. A contact pair fixes which side of the brain and
    which pair of electrode contacts the signal came from, and two pairs are two different
    measurements of two different places; averaging their grids would invite a reader to read a
    number that belongs to neither. Each pair therefore gets its own grid, its own two summary
    tables and its own pair of figures, and the pair is named on every one of them.

    `region_map` (raw channel name -> region string, e.g. from `_region_map`) is used to attach a
    display label to each entry (`label`/`short`/`region`/`hemisphere`/`contacts`, via
    `analytics.format_channel` -- the SAME formatter `_recorded_powers` already uses for the
    "Recorded power channels" card, reused here rather than re-derived) so the frontend never has
    to turn a raw key like "ZERO_TWO_LEFT" into a display string itself. The raw key stays the
    dict key and the value every request field still sends -- only a label is added.
    """
    out = {}
    for raw_ch, raw_cache in (raw_by_channel or {}).items():
        if not raw_cache:
            continue
        t0 = _time.perf_counter()
        try:
            power, stats, centers, _, chunk_excl = _band_time_sweep_power_by_seconds(
                pro_times, raw_cache, None, tol_s=tol_s,
                allow_window_reuse=allow_window_reuse, match_direction=match_direction,
                channel=raw_ch)
            match_s = _time.perf_counter() - t0
            sweep = analytics.band_time_sweep_from_power(
                power, pain_values, center_freqs_hz=centers,
                strategy=label_strategy, low_pct=low_pct, high_pct=high_pct,
                outlier_n_mad=outlier_n_mad, outlier_scale=outlier_scale,
                n_perm=(analytics.BAND_TIME_SWEEP_N_PERM if n_perm is None else n_perm),
                n_boot=(analytics.BAND_TIME_SWEEP_N_BOOT if n_boot is None else n_boot),
                seed=seed, channel=raw_ch, metric_key=metric_key, metric_label=metric_label,
                chunk_exclusion=chunk_excl,
                power_feature=("band power in the device's own least-significant-bit units, "
                               "reached from the 250 samples-per-second voltage trace by the "
                               "validated transform, or from the device's own spectrum where no "
                               "voltage trace was in range"))
            _fmt = analytics.format_channel(raw_ch, region=(region_map or {}).get(raw_ch))
            sweep["display_short"] = _fmt["short"]        # e.g. "L 0⁻2⁺"
            sweep["display_region"] = _fmt["region"]       # e.g. "Left GPi", "" if unknown
            sweep["display_hemisphere"] = _fmt["hemisphere"]
            sweep["display_contacts"] = _fmt["contacts"]
            # Reported once per contact pair since one setting governs the whole request: "prior"
            # means every matched recording preceded the rating it was matched to (the
            # forecasting-safe direction); "prospective" means matching looked either direction in
            # time. Read back from the matcher's own stats rather than re-deriving the label here,
            # so the two can never disagree.
            _first_stats = next(iter((stats or {}).values()), {})
            sweep["match_direction"] = _first_stats.get(
                "match_direction", "prior" if str(match_direction).lower() == "prior"
                else "prospective")
            sweep["matched_seconds"] = float(match_s)
            sweep["total_seconds"] = float(_time.perf_counter() - t0)
            sweep["match_stats_by_seconds"] = {
                str(k): {kk: v[kk] for kk in ("n_pro", "n_pro_td", "n_pro_psd",
                                              "n_pro_unmatched", "td_n_epochs_cap",
                                              "n_td_assigned", "n_td_used")
                         if kk in (v or {})}
                for k, v in (stats or {}).items()}
            sweep["figures"] = analytics.band_time_sweep_figures(sweep)
            out[raw_ch] = sweep
        except Exception as e:
            _log.warning("Biomarkers: band/length-of-signal sweep failed for %s (%s)",
                         raw_ch, e, exc_info=True)
            out[raw_ch] = analytics._sweep_blank(
                f"the sweep could not be completed for contact pair {raw_ch}: {e}")
    return out


#: TRACK D, TASK D2(a) -- checked directly against `ClosedLoopDeployment.constraints.RULES`
#: (D01-D51) before writing any code, per that task's own instruction to confirm the 51-rule
#: eligibility screen can be meaningfully evaluated on a (contact, band centre) pair alone before
#: adding a column for it. IT CANNOT, for two independent reasons, both read out of that file
#: rather than assumed:
#:   1. Of the 51 rules, only D08/D10/D12/D13 read solely the fields a grid point carries (centre
#:      frequency, band width); every other rule needs `amp_mA`, `impedance_ohms`, `rate_hz`,
#:      `pulse_width_us`, `artifact_flags` or similar -- fields that exist only for a SPECIFIC
#:      programmed candidate, never for a (contact, band centre) point on its own. Calling
#:      `constraints.check_eligibility` with only a band's fields set would report all ~47 of those
#:      as `unknowns`, and `constraints.py`'s own docstring is explicit that an unknown BLOCKS
#:      ("treating absence of evidence as permission is the specific error this module exists to
#:      prevent") -- so the full screen would mark essentially every grid point "blocked", which
#:      is not a finding about the band, only about what a grid point is missing.
#:   2. Restricting to the genuinely band-only rules does not rescue this: D08's adaptive range is
#:      8.0-30.0 Hz, and the sweep's own 22 centres are already restricted to 8.5-29.5 Hz (decision
#:      32) -- a strict subset. So the band-only subset of the screen would read PASS on literally
#:      every point in every grid this project has ever built, which is a column that can never
#:      fire and therefore carries no information either.
#: Forcing either version would be a label that looks like a device-rule verdict and is not one, so
#: no `device_rules_blocked` field is added. `device_rules_status` instead states this limitation
#: plainly, matching the project's own rule (CLAUDE.md's principle 2b) that a test or a label
#: asserting something untrue is worse than no label at all. See the D2(a) discussion in this
#: track's report for the concrete PI-level question this leaves open.
DEVICE_RULES_STATUS_NOTE = (
    "more stimulation settings needed: the device's 51-rule screen needs a specific stimulation "
    "current, pulse width, rate and impedance reading, none of which a (contact, band centre) grid "
    "point carries; every one of this grid's 22 centres already sits inside the device's own "
    "8.0-30.0 Hz adaptive-sensing range (decision 32), so a band-only version of the screen would "
    "never flag anything either")


def _attach_grid_export_columns(participant_uid, sweeps, *, band_width_hz):
    """TRACK D, TASK D2(b). Attach the RAW (untranslated) cross-setting-stability result to every
    row of every channel's `best_correlation_rows` and `best_auc_rows`, computed once per unique
    (channel, centre) pair rather than once per row (the correlation and AUC grids share the same
    22 centres, so this halves the number of calls). Also attaches `device_rules_status`, see
    `DEVICE_RULES_STATUS_NOTE` above for why no device-rule pass/fail verdict is attached instead.

    STAYS RAW ON PURPOSE. The honest four-valued translation
    (`ClosedLoopDeployment.stability.finding_from_stability_result`) is Closed-Loop Deployment's own
    module and Biomarkers must never import it back (see the note on
    `raw_stability_result_for_point` above) -- so the reader on the other side does the translation,
    the same as `adapter.py` already does for one candidate today.

    Never raises. A failure for one point is confined to that point's own field
    (`available: False`), the same never-crash contract every other function in this module keeps
    for a page that has to render something even when one channel's data is unusable.
    """
    # TRACK D LIVE-PROOF FINDING (2026-09-08): each row's band centre is named `band_center_hz`,
    # not `center_hz` -- confirmed by reading a real row live on RCS08 after this function's first
    # draft used the wrong key and, because a missing key is treated as "skip this row" rather than
    # an error, silently attached nothing to any row while still returning a normal-looking, fast
    # response. Caught only by measuring the response's own field count, not by a shape check --
    # exactly the reason this project's rules require reading a real row before trusting a field
    # name, and reporting a live count rather than assuming a code path ran.
    for channel, sweep in (sweeps or {}).items():
        cache = {}
        for key in ("best_correlation_rows", "best_auc_rows"):
            rows = sweep.get(key) or []
            for row in rows:
                center_hz = row.get("band_center_hz")
                if center_hz is None:
                    continue
                if center_hz not in cache:
                    try:
                        cache[center_hz] = raw_stability_result_for_point(
                            participant_uid, channel, center_hz, band_width_hz=band_width_hz)
                    except Exception as exc:                        # noqa: BLE001
                        cache[center_hz] = {"available": False,
                                            "reason": f"stability lookup raised {exc!r}"}
                row["cross_setting_stability_raw"] = cache[center_hz]
                row["device_rules_status"] = DEVICE_RULES_STATUS_NOTE


def _forecast_match_direction(request_data):
    """The PSD<->PRO match-direction parsing used by `run_for_participant` and
    `_validate_band_core`, extracted from two byte-identical inline copies (a review found the
    duplication and that neither copy had a request-level test).

      pro_first (default for discovery): walk PROs, claim up to max_per_rating PSDs/channel each
        within tolerance. Maximizes PRO coverage -- the right framing for discovery, where each
        PRO is the unit of independence.
      nearest: PSD-first symmetric, each PSD matched to the closest PRO either direction.
      prior:   PSD-first FORECASTING semantics (PSD must precede the PRO). Kept for the
        threshold-deployment view where causal prediction is the right semantics.

    Falls back to "prior" for an unrecognised value -- deliberately different from
    `_sweep_match_direction`'s "pro_first" fallback, because this reader is the causal-forecasting
    view and that one is the discovery sweep; collapsing the two into one helper would silently
    change one of their fallback behaviours.
    """
    _md = str(request_data.get("MatchDirection", "pro_first")).lower()
    if _md in ("pro_first", "pro-first", "pro"):
        return "pro_first"
    if _md == "nearest":
        return "nearest"
    return "prior"


def _sweep_match_direction(request_data):
    """The band-by-length sweep's own MatchDirection parsing, shared by the full grid
    (`band_time_sweep_for_participant`) and the per-cell drill-down
    (`band_time_sweep_cell_for_participant`) so the two always read the request the same way.

    Deliberately NOT the same helper as `_forecast_match_direction` above: that one falls back to
    "prior" for an unrecognised value, because it is the threshold-deployment view's
    causal-forecasting reading. This one falls back to "pro_first", because it is the discovery
    sweep's own reading, unchanged from before MatchDirection was wired into it. Collapsing the two
    would silently change one of their fallback behaviours.
    """
    _md = str(request_data.get("MatchDirection", "pro_first")).lower()
    return "prior" if _md == "prior" else ("nearest" if _md == "nearest" else "pro_first")


def band_time_sweep_for_participant(request_data):
    """The payload for the band-by-length-of-signal section at the bottom of the exploration page.

    Loads only what the sweep needs, reuses the memoized 3 s-piece cache the page's other panels
    already built, and returns one grid per sensing contact pair plus the two summary tables and the
    two heat maps for each. Never raises: a missing input comes back as an empty payload with the
    reason in `message`, which is what the panel renders as its empty state.
    """
    participant_uid = request_data["ParticipantId"]
    Participant = models.Participant.find(uid=participant_uid)
    blank = {"band_time_sweep": {}, "available_metrics": BIOMARKER_METRICS,
             "integration_seconds": [float(s) for s in analytics.BAND_TIME_SWEEP_SECONDS],
             "tile_seconds": float(analytics.RAW_LSB_WINDOW_SECONDS)}

    td = _load_recordings(participant_uid, TIMEDOMAIN_TYPES)
    pro_df = _load_pros(request_data, Participant)
    if pro_df is None or len(pro_df) == 0:
        return dict(blank, message=("No patient-reported pain scores are available for this "
                                    "participant, so there is nothing to track the band power "
                                    "against."))
    if not td:
        return dict(blank, message=("No time-domain Percept recordings have been ingested for this "
                                    "participant, so no band power can be computed at any length "
                                    "of signal."))

    # The section's OWN pain-score choice, sent as SweepMetric, falling back to the page's. Resolved
    # through the SAME helper the main analysis uses, so a composite score is blended identically
    # and an unknown choice falls back the same way rather than erroring.
    sweep_request = dict(request_data)
    chosen = request_data.get("SweepMetric")
    if chosen:
        sweep_request["LabelMetric"] = chosen
    pro_df, label_metric, _ = _resolve_biomarker_metric(sweep_request, pro_df)
    metric_label = next((m["label"] for m in BIOMARKER_METRICS if m["key"] == label_metric),
                        label_metric)

    # Every remaining setting comes from the top of the page, through the helpers the main analysis
    # uses. See the section note above for why MatchExtentSec is the one that is deliberately not
    # read here.
    label_strategy, low_pct, high_pct = _label_strategy_params(request_data)
    match_tol_min = _match_tolerance_param(request_data)
    allow_window_reuse = str(request_data.get("AllowWindowReuse", "")).lower() in (
        "1", "true", "yes", "on")
    outlier_n_mad = _float_param(request_data, "OutlierNMad",
                                 default=float(analytics.OUTLIER_N_MAD), lo=0.0, hi=50.0)
    outlier_scale = str(request_data.get("OutlierScale") or analytics.OUTLIER_SCALE).lower()
    if outlier_scale not in ("log", "raw"):
        outlier_scale = analytics.OUTLIER_SCALE
    # The eligibility radius, in seconds. The main slider can be switched off, in which case the
    # longest length of signal in the sweep stands in for it so that a pain report is still matched
    # against nearby recording rather than against the whole record.
    tol_s = (float(match_tol_min) * 60.0 if match_tol_min
             else float(max(analytics.BAND_TIME_SWEEP_SECONDS)))
    # Same three-way control the page's full-spectrum scan already reads (MatchDirection); this
    # section did not read it at all before this change, so every request behaved as "prospective"
    # (matched in either time direction) regardless of what the toggle showed on screen.
    match_direction = _sweep_match_direction(request_data)
    # TRACK D, TASK D2(b): off by default. The Biomarkers exploration page has never needed this
    # column and must not pay for it on every Recompute click; Closed-Loop Deployment's own reader
    # is the caller that sets this, once, for the entry it exports. Folded into `sweep_settings`
    # below (not a separate signature input) so a flagged and an unflagged request for the same
    # participant and settings are, correctly, two different cache entries -- never one serving a
    # stale answer for the other.
    include_stability = str(request_data.get("IncludeCrossSettingStability", "")).lower() in (
        "1", "true", "yes", "on")

    pro_match = _pro_match_arrays(pro_df, label_metric)
    if pro_match is None or pro_match[0] is None or np.asarray(pro_match[0]).size == 0:
        return dict(blank, label_metric=label_metric, metric_label=metric_label,
                    message=(f"No pain report carries a finite {metric_label} score, so there is "
                             f"nothing to track the band power against for this choice of score."))
    pro_times = np.asarray(pro_match[0], dtype=float)
    pain_values = np.asarray(pro_match[1], dtype=float)

    # TRACK A STEP 6: THE RESULTS ARE WRITTEN BACK, AND THE KEY DECIDES WHETHER TO RECOMPUTE.
    # The key names the tile entry, the pain-report snapshot, the pain score, and every setting
    # the sweep ran under. A newly filed report changes the snapshot key, a new upload changes the
    # tile key, and a moved slider changes a setting, so nothing stale can be served; and when
    # nothing changed, the thousand shuffles and thousand resamples per cell are not paid again.
    # THE STORE IS ASKED BEFORE THE SPECTRA, THE EVENT BLOCKS AND THE TILE CACHE ARE LOADED: the
    # key needs only the database rows and the reports already fetched, and on the live record
    # those loads were most of what a served request still paid.
    sweep_settings = {
        "eligibility_radius_seconds": float(tol_s), "allow_window_reuse": bool(allow_window_reuse),
        "label_strategy": label_strategy, "percentile_low": float(low_pct),
        "percentile_high": float(high_pct), "outlier_n_mad": float(outlier_n_mad),
        "outlier_scale": outlier_scale, "match_direction": match_direction,
        "include_cross_setting_stability": bool(include_stability)}
    sweep_sig, sweep_prov, tiles_sig = _band_sweep_signature(participant_uid, pro_df,
                                                             label_metric, sweep_settings)
    if sweep_sig is not None:
        stored = _load_stored_sweep(participant_uid, sweep_sig)
        if stored is not None:
            return stored

    # Through the SAME memo the cell drill-down reads, so a grid that actually builds also leaves
    # this worker ready for the first hover on it. Deliberately placed AFTER the stored-response
    # return above, not before it: a request served from the store must keep paying nothing for the
    # spectra and event blocks, which is the whole point of asking the store first (decision 38).
    # A store-served grid therefore leaves the memo cold and its first hover fills it once.
    _td_seed, psd_list, event_blocks, montage_blocks, chan_order, channels = (
        _recordings_setup_cached(participant_uid, td=td))
    if not channels:
        return dict(blank, label_metric=label_metric, metric_label=metric_label,
                    message="No sensing contact pair could be identified in the recordings.")
    _stamp_td_product(list(td or []))
    raw_by_ch = _raw_lsb_cache_cached(participant_uid, channels,
                                      list(td or []) + list(psd_list or []), event_blocks,
                                      montage_psd_blocks=montage_blocks, shared_sig=tiles_sig)

    t0 = _time.perf_counter()
    sweeps = _band_time_sweep_channels(
        raw_by_ch, pro_times, tol_s=tol_s, allow_window_reuse=allow_window_reuse,
        pain_values=pain_values, label_strategy=label_strategy, low_pct=low_pct,
        high_pct=high_pct, outlier_n_mad=outlier_n_mad, outlier_scale=outlier_scale,
        metric_key=label_metric, metric_label=metric_label, match_direction=match_direction,
        region_map=_region_map(Participant, chan_order))
    wall = float(_time.perf_counter() - t0)
    if include_stability:
        _attach_grid_export_columns(participant_uid, sweeps,
                                    band_width_hz=float(analytics.BAND_TIME_SWEEP_WIDTH_HZ))

    out = {
        "band_time_sweep": sweeps,
        "available_metrics": BIOMARKER_METRICS,
        "label_metric": label_metric,
        "metric_label": metric_label,
        "integration_seconds": [float(s) for s in analytics.BAND_TIME_SWEEP_SECONDS],
        "integration_seconds_delivered": [
            analytics.integration_time_tile_count(s)[1]
            for s in analytics.BAND_TIME_SWEEP_SECONDS],
        "tile_seconds": float(analytics.RAW_LSB_WINDOW_SECONDS),
        "band_width_hz": float(analytics.BAND_TIME_SWEEP_WIDTH_HZ),
        # Echoed so a saved response records the settings the sweep actually ran under, and so the
        # panel can state them without the reader having to trust that they were passed through.
        "settings_applied": {
            "match_tolerance_min": match_tol_min,
            "eligibility_radius_seconds": float(tol_s),
            "allow_window_reuse": bool(allow_window_reuse),
            "label_strategy": label_strategy,
            "percentile_low": float(low_pct),
            "percentile_high": float(high_pct),
            "outlier_n_mad": float(outlier_n_mad),
            "outlier_scale": outlier_scale,
            "sweep_metric": label_metric,
            "match_extent_sec_ignored": ("the top-of-page slider for how much recording goes into "
                                         "one measurement is not read here, because that quantity "
                                         "is the axis this section sweeps"),
        },
        "wall_seconds": wall,
        "message": None,
        "served_from_store": False,
        "store_keys": None,
    }
    if sweep_sig is not None:
        _store_sweep_results(participant_uid, sweep_sig, sweep_prov, out,
                             n_recordings=len(td or []))
    return out


#: The request key that asks for one cell's underlying (band power, pain score) pairs alone,
#: added for the heat-map redesign's click-through drill-down (Track A, task A2).
BAND_TIME_SWEEP_CELL_KEY = "BandTimeSweepCell"


def _wants_band_time_sweep_cell(request_data):
    """Whether this request is asking for one grid cell's underlying pairs alone."""
    return str(request_data.get(BAND_TIME_SWEEP_CELL_KEY, "")).lower() in ("1", "true", "yes", "on")


def band_time_sweep_cell_for_participant(request_data):
    """The (band power, pain score) pairs behind one cell of the band-by-length grid.

    Reuses every matching and labelling helper `band_time_sweep_for_participant` uses, on the same
    request fields, so the pairs returned here are matched exactly the way that cell's own grid
    value was computed -- but for one contact pair (`Channel`), one band centre (`BandCenterHz`)
    and one length of signal (`IntegrationSeconds`) rather than all of them. No permutation test and
    no bootstrap are run: the r, the AUC, the interval and the verdict for the cell are already in
    the grid response the browser holds from its own sweep request, and this endpoint exists only
    to supply the raw pairs a scatter and a pair of violin plots need, which the stored grid
    response never carried.
    """
    participant_uid = request_data["ParticipantId"]
    Participant = models.Participant.find(uid=participant_uid)
    blank = {"band_time_sweep_cell": None}
    channel = request_data.get("Channel")
    center_raw = request_data.get("BandCenterHz")
    seconds_raw = request_data.get("IntegrationSeconds")
    if not channel or center_raw is None or seconds_raw is None:
        return dict(blank, message=("Channel, BandCenterHz and IntegrationSeconds are all required "
                                    "to look up one cell."))
    try:
        center_hz = float(center_raw)
        seconds = float(seconds_raw)
    except (TypeError, ValueError):
        return dict(blank, message="BandCenterHz and IntegrationSeconds must both be numbers.")

    # Memoized setup (recordings + PSD blocks): this used to be rebuilt from scratch on every
    # single hover (~2s of the ~2.9s this endpoint cost, timed live on RCS08), even though none of
    # it depends on which cell was hovered.
    td, psd_list, event_blocks, montage_blocks, chan_order, channels = (
        _recordings_setup_cached(participant_uid))
    # The pain-report table held from the most recent build, rather than a fresh REDCap fetch on
    # every hover -- the narrow, deliberate override of decision 22 authorised for the read-only
    # drill-downs. See `_PRO_BUILD_CACHE`'s own note for the rule and what it costs; every endpoint
    # that builds something still fetches fresh and re-seeds what this reads.
    pro_df = _pain_reports_for_drilldown(request_data, Participant)
    if pro_df is None or len(pro_df) == 0:
        return dict(blank, message="No patient-reported pain scores are available for this "
                                   "participant.")
    if not td:
        return dict(blank, message="No time-domain Percept recordings have been ingested for this "
                                   "participant.")

    sweep_request = dict(request_data)
    chosen = request_data.get("SweepMetric")
    if chosen:
        sweep_request["LabelMetric"] = chosen
    pro_df, label_metric, _ = _resolve_biomarker_metric(sweep_request, pro_df)
    metric_label = next((m["label"] for m in BIOMARKER_METRICS if m["key"] == label_metric),
                        label_metric)

    label_strategy, low_pct, high_pct = _label_strategy_params(request_data)
    match_tol_min = _match_tolerance_param(request_data)
    allow_window_reuse = str(request_data.get("AllowWindowReuse", "")).lower() in (
        "1", "true", "yes", "on")
    outlier_n_mad = _float_param(request_data, "OutlierNMad",
                                 default=float(analytics.OUTLIER_N_MAD), lo=0.0, hi=50.0)
    outlier_scale = str(request_data.get("OutlierScale") or analytics.OUTLIER_SCALE).lower()
    if outlier_scale not in ("log", "raw"):
        outlier_scale = analytics.OUTLIER_SCALE
    tol_s = (float(match_tol_min) * 60.0 if match_tol_min
             else float(max(analytics.BAND_TIME_SWEEP_SECONDS)))
    match_direction = _sweep_match_direction(request_data)

    pro_match = _pro_match_arrays(pro_df, label_metric)
    if pro_match is None or pro_match[0] is None or np.asarray(pro_match[0]).size == 0:
        return dict(blank, message=(f"No pain report carries a finite {metric_label} score."))
    pro_times = np.asarray(pro_match[0], dtype=float)
    pain_values = np.asarray(pro_match[1], dtype=float)

    canon_channel = availability._canon_channel(channel)
    if canon_channel not in channels:
        return dict(blank, message=(f"Sensing contact pair {channel} was not found in this "
                                    f"participant's recordings."))
    _stamp_td_product(list(td or []))
    raw_by_ch = _raw_lsb_cache_cached(participant_uid, channels, list(td or []) + list(psd_list or []),
                                      event_blocks, montage_psd_blocks=montage_blocks)
    raw_cache = raw_by_ch.get(canon_channel)
    if not raw_cache:
        return dict(blank, message=f"No cached spectra for sensing contact pair {channel}.")

    power, _stats, centers, _col, chunk_excl = _band_time_sweep_power_by_seconds(
        pro_times, raw_cache, center_hz, tol_s=tol_s, allow_window_reuse=allow_window_reuse,
        seconds=[seconds], match_direction=match_direction, channel=canon_channel)
    mat = power.get(float(seconds))
    if mat is None or mat.size == 0 or not centers.size:
        return dict(blank, message="No band-power measurements could be produced for this cell.")
    col_power = mat[:, 0].astype(float)
    # THE SAME OUTLIER RULE THE GRID APPLIED, so a point drawn here is a point the grid's own r and
    # AUC for this cell were computed from -- without it, this endpoint would answer a question
    # close to but not the same as "what is behind that cell", and the two numbers would silently
    # disagree the way they did before this rule was added here (found live on RCS08: the raw
    # Pearson r recomputed from the un-excluded pairs was -0.022 against the grid's own -0.085 for
    # the same cell).
    # `chunk_excl` set means the contaminated 3 s pieces were already dropped one at a time before
    # these values were averaged, exactly as the grid's own cell was built, so there is nothing left
    # to exclude here and running the median-deviation rule on top would clean the same cell twice.
    if chunk_excl is None and outlier_n_mad > 0:
        mask = analytics.mad_outlier_columns(col_power.reshape(-1, 1), n_mad=outlier_n_mad,
                                             scale=outlier_scale).reshape(-1)
        col_power = np.where(mask, np.nan, col_power)

    y_bin, split_why, low_cut, high_cut = analytics._pain_split(
        pain_values, strategy=label_strategy, low_pct=low_pct, high_pct=high_pct)
    y_bin = np.asarray(y_bin, dtype=float)

    points = []
    n = min(pain_values.size, col_power.size, y_bin.size)
    for i in range(n):
        p, v = pain_values[i], col_power[i]
        if not (np.isfinite(p) and np.isfinite(v)):
            continue
        yb = y_bin[i]
        label = "high" if yb == 1 else ("low" if yb == 0 else "excluded")
        points.append({"pain": float(p), "power": float(v), "label": label})

    return {
        "band_time_sweep_cell": {
            "channel": canon_channel,
            "band_center_hz": float(centers[0]),
            "integration_seconds": float(seconds),
            "metric_key": label_metric,
            "metric_label": metric_label,
            "points": points,
            "n_points": len(points),
            "n_high": sum(1 for pt in points if pt["label"] == "high"),
            "n_low": sum(1 for pt in points if pt["label"] == "low"),
            "low_cut": low_cut,
            "high_cut": high_cut,
            "split_why": split_why,
        },
        "message": None,
    }


#: ==========================================================================================
#: TRACK A STEP 6 — "Write the biomarker results back after computing them".
#:
#: Three products leave the sweep. Two are the tidy tables the approved plan asks for, one row per
#: contact pair, band centre and length of signal: the correlation results and the discrimination
#: results, every value copied from the response and checkable against it
#: (`routines/band_results_tables.py`). The third is the response itself, so the page is served
#: from the store when nothing that feeds it has changed. All three carry the same key and the
#: same provenance: the tile entry and the pain-report snapshot, both raw inputs, so any module
#: may read them. `consumer="biomarkers"` is passed on the read anyway, because the refusal must
#: be exercised on every live read path or it protects nothing.
#: ==========================================================================================
_BAND_SWEEP_RESPONSE_KIND = "biomarker_band_sweep"
#: Bump this whenever the sweep's own computation changes in a way that is not already reflected
#: by a change to `sweep_settings` (decision 63 added the family-wise q-value and pass/fail label
#: to every row without adding a new user-facing setting, so a returning request with unchanged
#: settings would otherwise be served a stored response computed before those fields existed --
#: confirmed live: an unversioned before/after check on RCS08 showed 0 new fields because both
#: runs hit the same pre-existing cache entry).
#: Track D added `include_cross_setting_stability` to `sweep_settings` (folded into the signature
#: already, so a flagged and an unflagged request are already two different keys) and, when set,
#: the `cross_setting_stability` / `device_rules_status` fields on every best-row. Bumped anyway,
#: belt and suspenders, after this exact class of bug (an unversioned response shape change served
#: stale) was found and fixed twice already in this feature's own Tracks B and C.
#: v6 replaces the sweep's own outlier rule for a contact that has a historical ceiling table
#: entry: instead of 5 median absolute deviations computed from the window being looked at, each
#: contaminated 3 s piece is left out BEFORE anything is averaged, and the next closest clean piece
#: is taken in its place. This changes which measurements are excluded, so it changes numbers -- a
#: stored response built under any earlier rule must never be served as if it were built under this
#: one.
_BAND_SWEEP_RULE_VERSION = "v6_sweep_per_chunk_ceiling_backfill"

#: Response fields that are timings of the run that produced them, not results. They are not
#: compared when a stored response is checked against a fresh one, and a served response keeps the
#: timings of the run that built it, which is what they describe.
BAND_SWEEP_TIMING_FIELDS = ("wall_seconds", "matched_seconds", "total_seconds")


def _band_sweep_signature(participant_uid, pro_df, label_metric, settings):
    """`(signature, provenance, tile_signature)` for the sweep's three products, or three Nones
    when an input cannot be named: no tile entry key (no recordings identity) or no pain-report
    snapshot key (reports handed in through the request body). Without a name for both inputs the
    products are computed and returned but never written, because a key that cannot change with
    its inputs would serve a stale answer. The tile signature is returned so the tile cache lookup
    can reuse it instead of enumerating the recording rows again."""
    try:
        tiles_sig = _raw_lsb_shared_signature(participant_uid, _LSB_SPECTRUM_CENTERS)
    except Exception as exc:                                    # noqa: BLE001
        _log.info("Biomarkers: no tile key for the sweep (%r); results not stored", exc)
        tiles_sig = None
    report_key = getattr(pro_df, "attrs", {}).get(PRO_STORE_KEY_ATTR) if pro_df is not None else None
    if tiles_sig is None or not report_key:
        return None, None, tiles_sig
    tiles_key = _cache_store.product_key(_RAW_LSB_SHARED_KIND, participant_uid, tiles_sig)
    sig = (_BAND_SWEEP_RESPONSE_KIND, _BAND_SWEEP_RULE_VERSION, band_results_tables.RULE_VERSION,
           str(participant_uid), tiles_key, report_key, str(label_metric),
           tuple(sorted((k, v) for k, v in settings.items())),
           tuple(float(s) for s in analytics.BAND_TIME_SWEEP_SECONDS),
           float(analytics.BAND_TIME_SWEEP_WIDTH_HZ),
           float(analytics.BAND_TIME_SWEEP_CENTER_LO_HZ), float(analytics.BAND_TIME_SWEEP_CENTER_HI_HZ),
           int(analytics.BAND_TIME_SWEEP_N_PERM), int(analytics.BAND_TIME_SWEEP_N_BOOT), 0)
    try:
        from modules.CacheStore import provenance as _prov
    except ImportError:                                         # pragma: no cover
        from CacheStore import provenance as _prov
    prov = _prov.flatten([
        _prov.entry(tiles_key, kind=_RAW_LSB_SHARED_KIND, writer="biomarkers"),
        _prov.entry(report_key, kind="redcap_reports", writer="biomarkers")])
    return sig, prov, tiles_sig


def _sweep_store_keys(participant_uid, sig):
    return {
        "response": _cache_store.product_key(_BAND_SWEEP_RESPONSE_KIND, participant_uid, sig),
        "correlation": _cache_store.product_key(band_results_tables.CORRELATION_KIND,
                                                participant_uid, sig),
        "discrimination": _cache_store.product_key(band_results_tables.DISCRIMINATION_KIND,
                                                   participant_uid, sig),
    }


def _load_stored_sweep(participant_uid, sig):
    """The stored response for this key, marked as served from the store, or None."""
    try:
        got = _cache_store.load(_BAND_SWEEP_RESPONSE_KIND, participant_uid, sig,
                                consumer="biomarkers", root=_SHARED_CACHE_DIR_OVERRIDE)
    except Exception as exc:              # a refusal is impossible on a raw chain; log if it fires
        _log.warning("Biomarkers: the stored sweep was not released (%r); recomputing", exc)
        return None
    if not isinstance(got, dict):
        return None
    out = dict(got)
    out["served_from_store"] = True
    out["store_keys"] = _sweep_store_keys(participant_uid, sig)
    out["store_written"] = dict(got.get("store_written") or {}, response=True)
    stamp = _cache_store.read_stamp(_BAND_SWEEP_RESPONSE_KIND, participant_uid, sig,
                                    root=_SHARED_CACHE_DIR_OVERRIDE) or {}
    out["stored_utc"] = stamp.get("written_utc")
    return out


def _store_sweep_results(participant_uid, sig, prov, response, *, n_recordings=None):
    """Write the two tables and the response. Returns the three keys. Never raises."""
    keys = _sweep_store_keys(participant_uid, sig)
    # The keys go INTO the response before it is written, so the stored copy names its own
    # tables and a served copy does not depend on being patched after the read. `store_keys` is
    # the ADDRESS of each product; `store_written` says whether each one actually landed, because
    # a refused or failed write is logged and swallowed and a reader must not infer from an
    # address that a file exists.
    response["store_keys"] = keys
    written = {"correlation": False, "discrimination": False, "response": None}
    response["store_written"] = written
    sweeps = response.get("band_time_sweep") or {}
    metric = response.get("label_metric")
    common = dict(writer="biomarkers", trigger="band_time_sweep", provenance=prov,
                  n_recordings=n_recordings, root=_SHARED_CACHE_DIR_OVERRIDE)
    try:
        corr = band_results_tables.correlation_table(sweeps, metric_key=metric)
        disc = band_results_tables.discrimination_table(sweeps, metric_key=metric)
        if len(corr):
            got, _w = _cache_store.store_if_absent(band_results_tables.CORRELATION_KIND,
                                                   participant_uid, sig, lambda: corr, **common)
            written["correlation"] = got is not None and _landed(
                band_results_tables.CORRELATION_KIND, participant_uid, sig)
        if len(disc):
            got, _w = _cache_store.store_if_absent(band_results_tables.DISCRIMINATION_KIND,
                                                   participant_uid, sig, lambda: disc, **common)
            written["discrimination"] = got is not None and _landed(
                band_results_tables.DISCRIMINATION_KIND, participant_uid, sig)
        # The response is written with `response` still None in its own copy; a served copy is
        # by definition one that landed, and `_load_stored_sweep` says so on the way out.
        _cache_store.store_if_absent(_BAND_SWEEP_RESPONSE_KIND, participant_uid, sig,
                                     lambda: response, fmt="pickle", **common)
        written["response"] = _landed(_BAND_SWEEP_RESPONSE_KIND, participant_uid, sig)
    except Exception as exc:                                    # noqa: BLE001
        _log.warning("Biomarkers: the sweep results were not written back (%r)", exc)
    return keys


def _landed(kind, participant_uid, sig):
    """True when an entry for this key is on disk with its sidecar; opens no payload."""
    return _cache_store.read_stamp(kind, participant_uid, sig,
                                   root=_SHARED_CACHE_DIR_OVERRIDE) is not None
