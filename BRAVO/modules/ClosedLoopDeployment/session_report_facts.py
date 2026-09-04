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
    newest = {"stamp": "", "adaptive": None, "capture": {}, "d32": {}}

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
            # NOT counted here any more: the substring match caught
            # `.DiagnosticData.LfpFrequencySnapshotEvents[].Cycling` as well as the group setting,
            # which is why an earlier pass reported cycling enabled in 15187 records. Cycling is
            # now read per GROUP below, scoped to groups that actually have sensing configured,
            # because D32 asks about the BrainSense group and not about the device's history.
            elif p.endswith(".Channel") and "SensingChannel" in p:
                sensing_channels[_tail(v)] += 1
            elif "ElectrodeState" in p and "Electrode" in p and isinstance(v, str):
                electrodes[_tail(v)] += 1

        # capture pairs and their pulse widths, per hemisphere
        for grp in ("Final", "Initial"):
            for g in ((d.get("Groups") or {}).get(grp) or []):
                ps = g.get("ProgramSettings") or {}
                rate = ps.get("RateInHertz")
                # D32 SCOPE, corrected 2026-09-04. The rule asks whether cycling is enabled in a
                # BrainSense or Adaptive group, so the only groups that can answer it are the ones
                # with a SensingChannel configured. Reading Cycling across every group and every
                # historical snapshot answered a different question and reported the majority state
                # of the device rather than the state of the group we intend to use. The real path
                # is GroupSettings.Cycling.Enabled, one level deeper than first assumed.
                has_sensing = bool(ps.get("SensingChannel"))
                gs = g.get("GroupSettings") or {}
                cyc = (gs.get("Cycling") or {}).get("Enabled")
                if cyc is not None:
                    key = ("sensing" if has_sensing else "no_sensing",
                           "active" if g.get("ActiveGroup") else "inactive")
                    cycling[(key[0], key[1], bool(cyc))] += 1

                # THE NEWEST ACTIVE SENSING GROUP is the configuration a clinician would actually
                # program, so its state is what D32 should read. A 46% historical rate across every
                # group ever recorded answers "has this device ever cycled", which is a different
                # question and not the one the rule asks. This mirrors the pattern settled on for
                # impedance: report the current state for the decision and keep the history
                # alongside it, because "is it set that way now" and "has it ever been" are
                # different questions and both are worth having.
                if has_sensing and g.get("ActiveGroup") and stamp >= newest["stamp"]:
                    progs = []
                    for _ch in (ps.get("SensingChannel") or []):
                        progs.append(_ch)
                    rates = {ps.get("RateInHertz")} | {
                        _ch.get("RateInHertz") for _ch in progs if _ch.get("RateInHertz")}
                    rates = {r for r in rates if r is not None}
                    pws = {_ch.get("PulseWidthInMicroSecond") for _ch in progs
                           if _ch.get("PulseWidthInMicroSecond") is not None}
                    limits = [(_ch.get("UpperLimitInMilliAmps"), _ch.get("LowerLimitInMilliAmps"))
                              for _ch in progs]
                    newest["d32"] = {
                        # Each of these is a FEATURE EXCLUSION in D32: if present in the group,
                        # BrainSense or Adaptive cannot be configured there.
                        "cycling_in_group": bool(cyc) if cyc is not None else None,
                        # More than one distinct rate inside the group is what "multiple rates"
                        # means; a single rate at the group level with agreeing channels is one.
                        "multiple_rates_in_group": (len(rates) > 1) if rates else None,
                        # Interleaving shows up as programs on one hemisphere at different pulse
                        # widths or rates. With one program per hemisphere there is nothing to
                        # interleave, which is the common case here.
                        "interleaving_in_group": (len(pws) > 1) if pws else None,
                        # Patient amplitude limits are configured when an upper or lower limit is
                        # present on the program rather than absent.
                        "patient_limits_configured": (
                            any(u is not None or l is not None for u, l in limits)
                            if limits else None),
                        # The pocket adaptor is a hardware accessory and is NOT reported anywhere in
                        # the session report, so it stays None and D32 stays honest about it rather
                        # than assuming its absence.
                        "has_pocket_adaptor": None,
                        "n_programs": len(progs),
                        "rates_seen": sorted(float(r) for r in rates),
                        "pulse_widths_seen": sorted(float(x) for x in pws),
                    }

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
        # Keyed by (group has sensing, group is active, cycling enabled) so a reader can see WHICH
        # groups the cycling belongs to. D32 should consult the sensing groups only.
        "cycling_by_group_kind": {"%s/%s/%s" % k: v for k, v in cycling.items()},
        "cycling_in_sensing_group": bool(sum(
            v for k, v in cycling.items() if k[0] == "sensing" and k[2])),
        "cycling_in_active_sensing_group": bool(sum(
            v for k, v in cycling.items() if k[0] == "sensing" and k[1] == "active" and k[2])),
        # The five D32 feature exclusions as they stand in the NEWEST active sensing group.
        "d32_newest_active_sensing_group": newest["d32"],
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
