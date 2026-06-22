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

_log = logging.getLogger(__name__)

# DB recording types. Time-domain = raw 250 Hz LFP. The "power domain" source merges TWO
# band-power-over-time streams: the ~10-min Chronic (BrainSense Timeline) trend AND the per-session
# BrainSense Power-Domain band power — concatenated so power is compared apples-to-apples.
TIMEDOMAIN_TYPES = ["MedtronicBrainSenseTimeDomain", "MedtronicIndefiniteStream"]
CHRONIC_TYPES = ["MedtronicChronicBrainSense"]
POWERDOMAIN_TYPES = ["MedtronicBrainSensePowerDomain"]
# PSD-bearing products (montage surveys) for the data-availability timeline — loaded ONLY for the
# availability payload (they don't feed the decoder). See routines/availability.AVAILABILITY_TYPES.
AVAILABILITY_PSD_TYPES = ["MedtronicBrainSenseSurvey", "MedtronicBaselineMontages",
                          "MedtronicStimulationMontages"]

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
    """Resolve the tidy PRO DataFrame (canonical columns: `date_time_s1_daily`, `nrs`, `vas`, ...).

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
                       train_days=None, step_days=None, sliding=True, region_map=None):
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
            td_tasks = {
                "corr_spectrum": lambda: analytics.corr_spectrum(det, region_map=region_map),
                "psd_spectra": lambda: analytics.psd_spectra(det, region_map=region_map),
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
        ts = [r["t_start"] for r in records] + pain["t"] + stim["t"]
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
        return {"records": records, "pain": pain, "stim": stim, "freq_bands": bands,
                "span": span, "samples": samples, "lsb_overview": lsb_overview}
    except Exception as e:
        _log.warning("Biomarkers: availability payload failed: %s", e, exc_info=True)
        return {"records": [], "pain": {"metric": label_metric, "t": [], "y": []},
                "stim": {"t": [], "y": []}, "freq_bands": [], "span": [], "lsb_overview": {}}


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
    train_days, step_days, sliding, window_months, window_step_months = _window_params(request_data)
    rb_kwargs = {"sliding": sliding, "label_strategy": label_strategy,
                 "low_pct": low_pct, "high_pct": high_pct}
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
    out = _serialize_run(run, _compute_analytics(run, chronic, pro_df, label_metric=label_metric,
                                                 kmeans_features=kmeans_features,
                                                 label_strategy=label_strategy,
                                                 low_pct=low_pct, high_pct=high_pct,
                                                 train_days=train_days, step_days=step_days,
                                                 sliding=sliding, region_map=region_map),
                         label_metric=label_metric)
    out["label_metric"] = label_metric
    out["available_metrics"] = BIOMARKER_METRICS
    out["label_strategy"] = label_strategy
    out["available_strategies"] = BINARIZATION_STRATEGIES
    out["percentile_low"] = low_pct
    out["percentile_high"] = high_pct
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

    stages = _demo_stages() if demo else (request_data.get("Stages") or [])

    return {"metrics": metrics, "n_reports": int(t.notna().sum()), "correlation": correlation,
            "stages": stages,
            "message": "DEMO DATA — synthetic pain-score reports." if demo else ""}
