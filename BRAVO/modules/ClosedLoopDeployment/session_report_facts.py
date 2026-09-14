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

WHERE THE SUMMARY COMES FROM, changed 2026-09-12. Until then the only summary was
``_facts_RCS08.json``, produced once on 2026-09-05 by ``scan_folder`` over a plain-JSON folder on a
shared drive, committed next to the module, and refreshed by nothing. It went stale on the point
that matters most: it says the newest active sensing group runs at 110 Hz with adaptive therapy
NOT_CONFIGURED, and the device's newest report (2026-09-11) says GROUP_D at 55 Hz with adaptive
RUNNING on both channels. The server holds every ingested session report itself (572 files for
RCS08, 4,079 MB, encrypted at ``SourceFile.pointer``), so the summary is now built from THOSE by
``summary_from_ingested``, stored in the one cache store as the raw kind
``session_report_summary`` keyed on the participant's session-report file set, and rebuilt off the
request path (``manage.py rebuild_session_report_summary``, started detached by ``device_facts``
when the stored summary is missing or behind, and daily by the precompute loop). The committed
file is now the LAST fallback, and every rule's provenance sentence says which of the three was
used. ``scan_documents`` is the pure scanner both routes share; ``scan_folder`` is kept as a thin
wrapper so the two are provably the same pass.

The summary records the NEWEST value for each fact plus the distribution across the whole record,
because for several of these rules the distribution is the finding: D27 is violated by 1571 of 1736
right-hemisphere capture records, and reporting only the newest would hide that.
"""
from __future__ import annotations

import glob
import json
import os
import re
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


#: Bumped when the scanner's output changes shape or meaning. It is part of the stored summary's
#: key, so a summary built by older scanner code is never served as if this code had built it
#: (decision 25: the key carries every constant the stored numbers depend on).
SUMMARY_RULE_VERSION = "v3_session_report_summary_d32_per_hemisphere_and_adaptive_limits"

#: The store kind. Registered as RAW in ``CacheStore.provenance``: it is read straight off the
#: device export and no module's choice produced it, so it can never close a provenance cycle.
SUMMARY_KIND = "session_report_summary"


_STAMP_TOKEN = re.compile(r"(\d{8}T\d{6})")


def report_stamp(name):
    """The string "newest" is decided on, for one session-report file name.

    The export names carry the session's date as a token, ``Report_Json_Session_Report_
    20260911T083131.json``, and the scanner orders "newest" by comparing stamps. On the shared-drive
    folder every basename has the same prefix, so comparing basenames compared those tokens. THE
    INGESTED RECORD IS NOT LIKE THAT, found on the first live rebuild (2026-09-12): the uploader
    prefixes the export name with the folder it came from -- ``Rcs08.db - Report_Json_...`` for
    532 of RCS08's 572 files, ``RCS08 - ...``, ``JI - ...``, ``Report_JI Pacu_...`` for the rest --
    so comparing names compared prefixes, and "newest" came out as an August 2025 file whose
    prefix-less name sorted above every ``Rcs08.db - ...`` name from 2026. The stamp is therefore
    the date token first and the whole name after it as a tie-break; a name with no token is its
    own stamp, which is what it was before. For a uniformly named folder this is exactly the old
    order.
    """
    name = str(name or "")
    m = _STAMP_TOKEN.search(name)
    return f"{m.group(1)} {name}" if m else name


def scan_folder(folder, *, limit=None):
    """One pass over every session report under ``folder``. Returns a JSON-able summary.

    A THIN WRAPPER over ``scan_documents`` since 2026-09-12: it opens the files and hands each one
    over as ``(stamp, dict)``, the stamp being ``report_stamp`` of the file's basename (the date
    token the export name carries, then the basename -- see that function for why not the bare
    basename). A file that fails to parse is handed over as ``(stamp, None)`` so it is counted
    rather than aborting the scan: a single truncated export must not cost the other eleven
    hundred. ``tests/test_session_report_summary_store.py`` proves this wrapper and
    ``scan_documents`` agree field for field.
    """
    files = sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True))
    if limit:
        files = files[:limit]

    def _docs():
        for f in files:
            try:
                with open(f) as fh:
                    d = json.load(fh)
            except Exception:
                d = None
            yield report_stamp(os.path.basename(f)), d

    return scan_documents(_docs())


def _interleaving_per_hemisphere(progs):
    """True when any ONE hemisphere carries more than one distinct (rate, pulse width)."""
    if not progs:
        return None
    per_hemi = defaultdict(set)
    for ch in progs:
        hemi = _tail(ch.get("HemisphereLocation", "")) or "Unknown"
        rate, pw = ch.get("RateInHertz"), ch.get("PulseWidthInMicroSecond")
        if rate is not None or pw is not None:
            per_hemi[hemi].add((rate, pw))
    if not per_hemi:
        return None
    return any(len(v) > 1 for v in per_hemi.values())


def _patient_limits_configured(progs, limits):
    """True when a limit is present on a sensing channel whose adaptive therapy is NOT running.

    While Adaptive Therapy is RUNNING the channel's limits are the adaptive amplitude limits the
    controller moves between (D28), which D32 does not exclude; a limit on a channel that is not
    running adaptive therapy is a patient limit.
    """
    if not progs or not limits:
        return None
    flagged = False
    for ch in progs:
        u, l = ch.get("UpperLimitInMilliAmps"), ch.get("LowerLimitInMilliAmps")
        if u is None and l is None:
            continue
        if _tail(ch.get("AdaptiveTherapyStatus", "")) == "RUNNING":
            continue
        flagged = True
    return flagged


def scan_documents(docs):
    """One pass over decoded session reports. Returns a JSON-able summary.

    ``docs`` is an iterable of ``(stamp, report)`` pairs: ``stamp`` is the string "newest" is
    decided on (the export file name, which carries the date) and ``report`` is the decoded JSON
    dict, or ``None`` for a document that could not be read, which is counted in ``n_unreadable``
    and otherwise skipped. Pure: no file, no database, so the same pass serves the shared-drive
    folder, the ingested record and the tests.

    The summary records the NEWEST value for each fact plus the distribution across the whole
    record; see the module docstring for why both are kept.
    """
    n_files = 0
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
    programmed_pairs = defaultdict(Counter)                # hemi -> (rate, pw) -> count (D31)
    newest = {"stamp": "", "adaptive": None, "capture": {}, "d32": {}}

    for stamp, d in docs:
        n_files += 1
        if not isinstance(d, dict):
            unreadable += 1
            continue
        stamp = str(stamp)

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
                        # Interleaving shows up as programs on ONE hemisphere at different pulse
                        # widths or rates. With one program per hemisphere there is nothing to
                        # interleave, which is the common case here. Counted PER HEMISPHERE
                        # (corrected 2026-09-12): the earlier pool across both sides read RCS08's
                        # ordinary 100 us Left / 150 us Right as interleaving and failed D32 the
                        # first time the scanner met current data.
                        "interleaving_in_group": _interleaving_per_hemisphere(progs),
                        # Patient amplitude limits. The SensingChannel's Upper/LowerLimitInMilliAmps
                        # are the ADAPTIVE amplitude limits while Adaptive Therapy is RUNNING (they
                        # default to the capture amplitudes, D28; on RCS08's GROUP_D they read
                        # 2.0-3.0 mA, exactly the capture range) and become patient limits only
                        # when the group is sensing-only (D28; RCS08's GROUP_A reads 0-4 mA).
                        # Corrected 2026-09-12: reading a present limit as a patient limit
                        # regardless of status failed D32 on the very group running adaptive DBS.
                        "patient_limits_configured": _patient_limits_configured(progs, limits),
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
                    # D31's table: every (rate, pulse width) the device has accepted in a group
                    # carrying a SensingChannel, per hemisphere. Counted here ONLY -- nothing in
                    # this task reads it into ``brainsense_pair_programmed``; the next step
                    # compares these counts against the hardcoded
                    # ``device_facts.BRAINSENSE_PROGRAMMED_PAIRS`` before anything switches over.
                    _rate = ch.get("RateInHertz") if ch.get("RateInHertz") is not None else rate
                    if _rate is not None and pw is not None:
                        try:
                            programmed_pairs[hemi][(float(_rate), float(pw))] += 1
                        except (TypeError, ValueError):
                            pass
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
        "n_files": n_files, "n_unreadable": unreadable,
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
        # Same content as ``device_facts.BRAINSENSE_PROGRAMMED_PAIRS``, spelled "rate/pw" so it
        # survives JSON; ``programmed_pairs_table`` turns it back into that tuple-keyed shape.
        "brainsense_programmed_pairs": {h: {"%g/%g" % k: v for k, v in sorted(c.items())}
                                        for h, c in programmed_pairs.items()},
    }


def programmed_pairs_table(summary):
    """``brainsense_programmed_pairs`` in the tuple-keyed shape of
    ``device_facts.BRAINSENSE_PROGRAMMED_PAIRS``: ``{"Left": {(55.0, 60.0): 1274, ...}}``."""
    out = {}
    for hemi, pairs in ((summary or {}).get("brainsense_programmed_pairs") or {}).items():
        table = {}
        for k, v in (pairs or {}).items():
            try:
                r, pw = str(k).split("/")
                table[(float(r), float(pw))] = int(v)
            except (TypeError, ValueError):
                continue
        out[hemi] = table
    return out


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


# ---------------------------------------------------------------------------------------------
# THE SAME SCAN OVER THE INGESTED RECORD, STORED UNDER THE FILE SET'S OWN KEY
# ---------------------------------------------------------------------------------------------
# The store import is spelled twice on purpose: the container puts /usr/src/BRAVO on the path and
# makes the package ``modules.CacheStore``; the test suite runs from BRAVO/modules and makes it
# ``CacheStore``. See ARCHITECTURE_cache_store.md §3.
try:
    from modules.CacheStore import store as _cache_store
except ImportError:                                   # pragma: no cover - depends on the runner
    from CacheStore import store as _cache_store


def is_session_report(source_file):
    """The rule for which ingested files are session reports: the name contains "Session"."""
    return "Session" in (getattr(source_file, "name", None) or "")


def session_report_files(participant):
    """This participant's ingested session-report rows, sorted by name. Django inside; the caller
    passes a Participant row or its uid. One query over ``SourceFile``; no file is opened."""
    from Server import models as _m
    p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
    if p is None:
        return []
    rows = [s for s in _m.SourceFile.find_all(owner=p) if is_session_report(s)]
    rows.sort(key=lambda s: (str(s.name or ""), str(s.uid)))
    return rows


def file_set_signature(rows):
    """The store key for a summary of exactly these session-report files.

    A digest over each file's (uid, hashed, name) in a fixed order, with the file count and the
    scanner's rule version beside it -- never the file NAMES alone, because a re-ingested file
    keeps its name and changes its hash, and never a date, because a summary must be found by what
    it was built from (decision 24: the key is built from the database rows, before anything is
    opened). Pure: takes anything with ``uid``, ``hashed`` and ``name`` attributes, so the tests
    hand it stub rows. Returns None for an empty set, so nothing is ever stored for a participant
    with no session reports.
    """
    import hashlib
    items = sorted((str(getattr(r, "uid", "")), str(getattr(r, "hashed", "") or ""),
                    str(getattr(r, "name", "") or "")) for r in (rows or []))
    if not items:
        return None
    h = hashlib.blake2b(digest_size=16)
    for uid, hashed, name in items:
        h.update(f"{uid}\x1f{hashed}\x1f{name}\x1e".encode("utf8"))
    return (SUMMARY_KIND, SUMMARY_RULE_VERSION, len(items), h.hexdigest())


def newest_by_stamp(rows):
    """The row whose name's stamp is greatest, or None for an empty set."""
    rows = list(rows or [])
    if not rows:
        return None
    return max(rows, key=lambda r: report_stamp(getattr(r, "name", "") or ""))


def _decoded_documents(rows, loader):
    """``(stamp, dict-or-None)`` for each ingested row, decrypted through ``loader``; a file that
    cannot be decrypted or parsed becomes ``(stamp, None)`` and is counted, not fatal."""
    for sf in rows:
        stamp = report_stamp(getattr(sf, "name", "") or "")
        try:
            raw = loader(sf)
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            d = json.loads(raw)
        except Exception:                                        # noqa: BLE001
            d = None
        yield stamp, d


def summary_from_ingested(participant, *, rows=None, loader=None):
    """The summary built from the participant's INGESTED session reports, the same pass
    ``scan_folder`` makes over a folder.

    Each row is decrypted with ``DataCurator.loadCacheFile`` (the route the therapy history and
    the D30 reader already take) and handed to ``scan_documents`` with ``report_stamp`` of
    ``SourceFile.name`` as the stamp. Over the whole record this takes minutes -- decrypting and parsing the 20 newest,
    small daily files alone took 1.34 s on RCS08 -- so it must run off the request path: the
    management command and the detached launcher call it, a page request never does.

    ``rows`` and ``loader`` exist for the tests; production passes neither and the Django imports
    happen here, inside the function, because this module is imported by tests with no Django.
    Adds to the scanner's dict: ``newest_stamp`` (the NAME of the newest file, by ``report_stamp``
    order), ``newest_stamp_key`` (its stamp, what a later file set is compared against),
    ``built_utc``, ``source_signature`` (the file-set key the summary is stored under),
    ``participant_uid`` and ``source``.
    """
    import datetime as _dt
    if rows is None:
        rows = session_report_files(participant)
    if loader is None:
        from modules import DataCurator as _DC
        loader = _DC.loadCacheFile
    sig = file_set_signature(rows)
    summary = scan_documents(_decoded_documents(rows, loader))
    newest = newest_by_stamp(rows)
    summary["newest_stamp"] = str(newest.name or "") if newest is not None else None
    summary["newest_stamp_key"] = report_stamp(newest.name) if newest is not None else None
    summary["built_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    summary["source_signature"] = list(sig) if sig else None
    summary["participant_uid"] = str(getattr(participant, "uid", participant))
    summary["source"] = "ingested"
    return summary


def rebuild_and_store(participant, *, force=False, rows=None, loader=None):
    """Build the summary from the ingested record and store it under its file-set key, unless the
    store already holds that key. Returns a status dict; never raises.

    THE KEY DECIDES WHETHER ANY WORK HAPPENS (decision 26): the file-set signature is one database
    query, and if the store already has an entry under it the minutes-long scan is not paid. This
    is what makes the daily pass cheap and the second run of the command ``already_current``.
    ``force`` rebuilds anyway, for a deliberate refresh. Nothing is stored for a participant with
    no session reports, and a summary that could not be stored is reported as such rather than
    silently kept in this process only.
    """
    import time as _time
    uid = str(getattr(participant, "uid", participant))
    out = {"participant_uid": uid, "stored": False, "already_current": False, "reason": None,
           "n_files": None, "newest_stamp": None, "store_key": None, "wall_seconds": None}
    t0 = _time.perf_counter()
    try:
        if rows is None:
            rows = session_report_files(participant)
        sig = file_set_signature(rows)
        if sig is None:
            out["reason"] = "this participant has no ingested session reports, so there is nothing to summarise"
            return out
        out["n_files"] = len(rows)
        out["store_key"] = _cache_store.product_key(SUMMARY_KIND, uid, sig)
        if not force and _cache_store.load(SUMMARY_KIND, uid, sig) is not None:
            out["already_current"] = True
            out["reason"] = "a summary of exactly this session-report file set is already stored"
            out["newest_stamp"] = str(newest_by_stamp(rows).name or "")
            return out
        summary = summary_from_ingested(participant, rows=rows, loader=loader)
        out["newest_stamp"] = summary.get("newest_stamp")
        out["n_unreadable"] = summary.get("n_unreadable")
        wrote = _cache_store.store(SUMMARY_KIND, uid, sig, summary,
                                   trigger="rebuild_session_report_summary",
                                   n_recordings=summary.get("n_files"), writer="closed_loop",
                                   provenance=[])
        out["stored"] = bool(wrote)
        if not wrote:
            out["reason"] = ("the summary was computed and NOT stored (the store refused or has "
                             "nowhere to write); a page request will keep using the stale copy")
    except Exception as exc:                                     # noqa: BLE001
        out["reason"] = f"raised {exc!r}"
    finally:
        out["wall_seconds"] = round(_time.perf_counter() - t0, 3)
    return out
