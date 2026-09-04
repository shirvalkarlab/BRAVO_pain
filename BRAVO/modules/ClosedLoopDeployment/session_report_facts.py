"""Extract device facts the platform decoder does not keep, straight from the session-report JSONs.

WHY THIS FILE EXISTS, and what should eventually replace it. Six device rules ask about hardware
state that IS present in the Medtronic session reports but is not reachable from the platform's
decoded models. Of the fields those rules need, ``ArtifactStatus`` and ``LFPFrequencyinHertz`` have
ZERO references anywhere in the codebase, and the capture and adaptive fields that the decoder does
mention do not survive into a queryable form on ``Server.models.Therapy`` (its
``electricaltherapy`` column is null on the rows checked). So the rules were blocking for want of
data that had been ingested all along.

The right long-term fix is to decode these fields into the model at ingest, once, for every
participant. This module is the interim: a single pass over the raw reports that writes a compact
per-participant summary, which ``device_facts`` then reads. It is deliberately a SUMMARY and not a
live scan — the reports are 8.5 GB across 1154 files for one participant, so scanning them per
request is not an option.

The summary records the NEWEST value for each fact plus the distribution across the whole record,
because for several of these rules the distribution is the finding: D27 is violated by 1571 of 1736
right-hemisphere capture records, and reporting only the newest would hide that.
"""
from __future__ import annotations

import glob
import json
import os
from collections import Counter, defaultdict

#: D27 ceilings (A610 p. 73). Above either of these the stimulation artefact contaminates the
#: capture, so a threshold read there is not trustworthy.
CAPTURE_AMP_CEILING_MA = 5.0
CAPTURE_PW_CEILING_US = 120.0

#: D09 gate (A610 p. 37, p. 72).
LFP_CAPTURE_FLOOR_UVP = 1.2


def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, o


def _tail(v):
    return str(v).split(".")[-1]


def scan_folder(folder, *, limit=None):
    """One pass over every session report under ``folder``. Returns a JSON-able summary.

    Files that fail to parse are counted and skipped rather than aborting the scan: a single
    truncated export must not cost the other eleven hundred.
    """
    files = sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True))
    if limit:
        files = files[:limit]

    adaptive = Counter()
    artifact = defaultdict(Counter)
    cap_pairs = defaultdict(Counter)
    cap_pw = defaultdict(Counter)
    cap_violations = defaultdict(lambda: [0, 0])          # hemi -> [violating, total]
    suspend = Counter()
    cycling = Counter()
    lfp_bins = defaultdict(lambda: defaultdict(list))     # channel -> freq -> [uVp]
    sensing_channels = Counter()
    electrodes = Counter()
    unreadable = 0
    newest = {"stamp": "", "adaptive": None, "capture": {}}

    for f in files:
        try:
            with open(f) as fh:
                d = json.load(fh)
        except Exception:
            unreadable += 1
            continue
        stamp = os.path.basename(f)

        for p, v in _walk(d):
            if p.endswith("AdaptiveTherapyStatus"):
                adaptive[_tail(v)] += 1
                if stamp > newest["stamp"]:
                    newest["stamp"], newest["adaptive"] = stamp, _tail(v)
            elif "SuspendAmplitude" in p and isinstance(v, (int, float)):
                suspend[float(v)] += 1
            elif "Cycling.Enabled" in p:
                cycling[bool(v)] += 1
            elif p.endswith(".Channel") and "SensingChannel" in p:
                sensing_channels[_tail(v)] += 1
            elif "ElectrodeState" in p and "Electrode" in p and isinstance(v, str):
                electrodes[_tail(v)] += 1

        # capture pairs and their pulse widths, per hemisphere
        for grp in ("Final", "Initial"):
            for g in ((d.get("Groups") or {}).get(grp) or []):
                ps = g.get("ProgramSettings") or {}
                rate = ps.get("RateInHertz")
                for ch in (ps.get("SensingChannel") or []):
                    lo = ch.get("LowerCaptureAmplitudeInMilliAmps")
                    up = ch.get("UpperCaptureAmplitudeInMilliAmps")
                    pw = ch.get("PulseWidthInMicroSecond")
                    hemi = _tail(ch.get("HemisphereLocation", "")) or "Unknown"
                    if lo or up:
                        cap_pairs[hemi][(lo, up)] += 1
                        if pw:
                            cap_pw[hemi][pw] += 1
                        bad = (up is not None and up > CAPTURE_AMP_CEILING_MA) or \
                              (pw is not None and pw > CAPTURE_PW_CEILING_US)
                        cap_violations[hemi][1] += 1
                        cap_violations[hemi][0] += 1 if bad else 0
                        if stamp >= newest["stamp"]:
                            newest["capture"][hemi] = {"lower_mA": lo, "upper_mA": up,
                                                       "pw_us": pw, "rate_hz": rate}

        # per-bin LFP magnitude and the device's own artefact verdict
        for blk in (d.get("BrainSenseSurveys") or []):
            for e in (blk.get("ElectrodeSurvey") or []):
                ch = "%s_%s" % (e.get("SensingElectrodes"), e.get("Hemisphere"))
                artifact[ch][_tail(e.get("ArtifactStatus"))] += 1
                fr = e.get("LFPFrequencyinHertz")
                mg = e.get("LFPMagnitudeinMicroVoltPeak")
                if fr and mg and len(fr) == len(mg):
                    for f_, m_ in zip(fr, mg):
                        if 4.0 <= float(f_) <= 40.0:      # keep the adaptive window and its shoulders
                            lfp_bins[ch][round(float(f_), 2)].append(float(m_))

    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None

    return {
        "n_files": len(files), "n_unreadable": unreadable,
        "adaptive_status_counts": dict(adaptive),
        "adaptive_status_newest": newest["adaptive"],
        "adaptive_has_run": bool(adaptive.get("RUNNING")),
        "capture_newest": newest["capture"],
        "capture_pairs": {h: {"%s/%s" % k: v for k, v in c.items()} for h, c in cap_pairs.items()},
        "capture_pulse_widths": {h: dict(c) for h, c in cap_pw.items()},
        "capture_ceiling_violations": {h: {"violating": v[0], "total": v[1]}
                                       for h, v in cap_violations.items()},
        "suspend_amplitudes": {str(k): v for k, v in suspend.items()},
        "cycling_enabled_counts": {str(k): v for k, v in cycling.items()},
        "sensing_channels": dict(sensing_channels),
        "electrode_labels": dict(electrodes),
        "artifact_status": {ch: dict(c) for ch, c in artifact.items()},
        "lfp_bins_median_uvp": {ch: {str(f): med(v) for f, v in sorted(bins.items())}
                                for ch, bins in lfp_bins.items()},
    }


def candidate_lfp_bins(summary, channel, hemisphere):
    """The (Hz, uVp) list D09 consumes, for one sensing channel.

    The survey labels a channel by its electrode pair and hemisphere (``ONE_AND_THREE_Left``) while
    a candidate names it ``ONE_THREE_LEFT``, so the two spellings are reconciled here rather than at
    the call site. Returns an empty list when the channel has no survey, which D09 reports as "not
    determinable" rather than as a pass.
    """
    bins = summary.get("lfp_bins_median_uvp") or {}
    want = str(channel).upper().replace("_", "")
    for key, per_f in bins.items():
        pair, _, hemi = str(key).rpartition("_")
        if hemi.lower() != str(hemisphere).lower():
            continue
        if pair.upper().replace("_AND_", "").replace("_", "") == want.replace("LEFT", "").replace("RIGHT", ""):
            return [(float(f), float(v)) for f, v in per_f.items() if v is not None]
    return []
