"""Read established device facts off the platform, for the rules that need a measurement.

Several rules in ``constraints.py`` cannot be evaluated from the analysis tables alone: they ask
about the state of the hardware. This module supplies those facts from the database and, where a
fact can only come from a person reading the programmer, says so rather than inventing a value.

WHY IMPEDANCE IS READ FROM ``metadata`` AND NOT THROUGH ``Database.loadSourceFile``. Recordings of
type ``MedtronicDeviceImpedance`` carry an EMPTY ``pointer``: there is no ``.bdat`` file for them,
because the payload is small enough to live inline on the row. Calling ``loadSourceFile`` with an
empty pointer trips its path-prefix guard and raises "Malicious Attempt at Accessing Other Data in
the Computer", which reads like a security incident and is nothing of the sort. That exception is
the PREFIX check; the HMAC integrity check raises a different message entirely ("DANGER:
Unauthorized Modification of Data"). Diagnosing this the wrong way round cost a session, so it is
written down here: for this recording type, read ``recording.metadata`` and never call the loader.
"""
from __future__ import annotations

import os
import statistics as _st
import subprocess
import sys
import time as _time

# Spelled twice on purpose: the container makes the package ``modules.CacheStore``, the test
# suite run from BRAVO/modules makes it ``CacheStore``. ARCHITECTURE_cache_store.md §3.
try:
    from modules.CacheStore import store as _cache_store
except ImportError:                                   # pragma: no cover - depends on the runner
    from modules.CacheStore import store as _cache_store

# THE BRAINSENSE MINIMUM RATE, ONE NUMBER, imported rather than retyped (review C3, 2026-09-12).
# ``StimOptimizer.routines.percept_adaptive.MIN_ADAPTIVE_RATE_HZ`` is the PI-stated 55 Hz the Stim
# Optimizer page enforces (decision 138); D31 here reads ``brainsense_min_rate_hz`` and until this
# import nobody supplied it, so the two pages carried two floors (this ledger's D44 at 30 Hz, that
# page's 55 Hz) and a 40 Hz candidate got two different reasons on two pages. Spelled twice like
# every cross-module import in this repository: the container makes the package
# ``modules.StimOptimizer``, the host suite makes it ``StimOptimizer``.
try:
    from modules.StimOptimizer.routines.percept_adaptive import MIN_ADAPTIVE_RATE_HZ as _MIN_ADAPTIVE_RATE_HZ
except ImportError:                                   # pragma: no cover - depends on the runner
    from modules.StimOptimizer.routines.percept_adaptive import MIN_ADAPTIVE_RATE_HZ as _MIN_ADAPTIVE_RATE_HZ

#: Lead models whose short-circuit floor is the SenSight value rather than the 1x4 value. The
#: constraint table keys its floor on the string "sensight", so the model number is mapped here
#: rather than at the call site.
_SENSIGHT_MODELS = ("LEAD_B33015", "LEAD_B33005")



# Aditya canonical compatibility imports/constants.

def _lead_type(lead_model):
    if not lead_model:
        return None
    model = str(lead_model).upper().rsplit(".", 1)[-1]
    if model in _SENSIGHT_MODELS:
        return "sensight"
    if model in ("LEAD_3387", "LEAD_3389"):
        return "1x4"
    return None


#: The open-circuit limit D16 uses, duplicated here (rather than imported from ``constraints``)
#: because ``constraints.py`` already imports this module and a circular import would follow.
_OPEN_LIMIT_OHM = 10_000.0


def _measurement_current(metadata):
    """The impedance test's own measurement current, from ``metadata["Amplitude"]``."""
    raw = (metadata or {}).get("Amplitude")
    if raw is None:
        return None
    s = str(raw).strip()
    if s.lower().startswith("automatic"):
        return "automatic_increase"
    if s.lower().endswith("ma"):
        s = s[:-2]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _iso(d):
    """A recording's date as something a report can print.

    Real recordings carry a ``datetime``; the tests in this module use a plain integer, which is
    passed through unchanged rather than forced into a shape it was never given.
    """
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        return d.isoformat()
    # On the live platform ``Recording.date`` is a number of seconds since 1970 (UTC), e.g.
    # 1789140600.0 for 2026-09-11 15:30 UTC; print it as a date rather than as that number.
    try:
        import datetime as _dt
        v = float(d)
        if v > 1e8:
            return _dt.datetime.fromtimestamp(v, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return d


def impedance_facts(recordings):
    """Summarise impedance for D16 from ``MedtronicDeviceImpedance`` recording rows.

    Returns the WORST (highest) bipolar reading per hemisphere rather than a mean, because D16 is a
    fault check: one open contact matters even when the other seven are healthy, and averaging is
    exactly the operation that would hide it. The device's own Status field is carried through
    verbatim, since the manufacturer's judgement of its own hardware outranks our threshold
    arithmetic.

    WHICH RECORD THE PER-HEMISPHERE NUMBERS COME FROM, decided by the PI 2026-09-12 (see
    ``_measurement_current``'s own note for the measurement). ``out["Left"]``, ``out["Right"]`` and
    therefore ``candidate_impedance_ohm`` are read from the NEWEST recording run at a FIXED
    measurement current, when one exists; only when no fixed-current recording is on record do
    they fall back to the newest recording of any kind, which is exactly what this function did
    before this change. ``measurement_current``, ``measured_at`` and ``status_chosen`` describe
    whichever recording was actually used for that choice. ``status_newest``, ``lead_model`` and
    ``lead_type`` still describe the single newest recording of any kind, because they are about
    the device's current state rather than about which reading D16 trusts.
    """
    rows = [r for r in (recordings or []) if getattr(r, "metadata", None)]
    if not rows:
        return {"available": False, "reason": "no impedance recordings on record"}
    rows.sort(key=lambda r: getattr(r, "date", 0) or 0)
    newest_row = rows[-1]
    newest = newest_row.metadata or {}
    newest_current = _measurement_current(newest)

    fixed_rows = [r for r in rows if isinstance(_measurement_current(r.metadata), float)]
    chosen_row = fixed_rows[-1] if fixed_rows else newest_row
    chosen = chosen_row.metadata or {}
    chosen_current = _measurement_current(chosen)

    statuses = {}
    for r in rows:
        s = str((r.metadata or {}).get("Status"))
        statuses[s] = statuses.get(s, 0) + 1

    out = {"available": True, "n_records": len(rows),
           "status_newest": newest.get("Status"),
           "status_counts": statuses,
           # ``lead_model`` / ``lead_type`` are the LEFT lead's, kept for callers that predate the
           # per-side pair below; ``facts_for_participant`` reads the sensing side's own entry
           # (review C11, 2026-09-12: D16's short-circuit limit depends on the lead family, and the
           # left lead's family was being used to judge the right lead).
           "lead_model": (newest.get("Left") or {}).get("LeadModel"),
           "lead_type": _lead_type((newest.get("Left") or {}).get("LeadModel")),
           "lead_model_by_hemisphere": {h: (newest.get(h) or {}).get("LeadModel")
                                        for h in ("Left", "Right")},
           "lead_type_by_hemisphere": {h: _lead_type((newest.get(h) or {}).get("LeadModel"))
                                       for h in ("Left", "Right")},
           "measurement_current": chosen_current,
           "measured_at": _iso(getattr(chosen_row, "date", None)),
           "status_chosen": chosen.get("Status")}

    # The historical worst is a DIFFERENT question from the current reading and both matter: a lead
    # whose newest measurement is inside the limits but which has exceeded them before is not the
    # same object as one that never has. Reporting only the newest hid this until the 2026-09-04
    # ingest brought in a newer, better measurement and D16 silently flipped from fail to pass.
    # The "_fixed" figures restrict that same history to recordings run at a fixed measurement
    # current, so a reader can tell whether the record's own worst-ever reading is itself a
    # low-current artefact or a reading a fixed-current test actually confirmed.
    for hemi in ("Left", "Right"):
        hist = [float(x) for r in rows
                for row in (((r.metadata or {}).get(hemi) or {}).get("Bipolar") or [])
                for x in row if x]
        hist_fixed = [float(x) for r in rows
                      if isinstance(_measurement_current(r.metadata), float)
                      for row in (((r.metadata or {}).get(hemi) or {}).get("Bipolar") or [])
                      for x in row if x]
        out.setdefault("history", {})[hemi] = {
            "bipolar_max_ohm_ever": max(hist) if hist else None,
            "n_readings": len(hist),
            "n_above_open_limit": sum(1 for x in hist if x > 10000.0),
            "bipolar_max_ohm_ever_fixed": max(hist_fixed) if hist_fixed else None,
            "n_readings_fixed": len(hist_fixed),
            "n_above_open_limit_fixed": sum(1 for x in hist_fixed if x > 10000.0),
        }

    for hemi in ("Left", "Right"):
        h = chosen.get(hemi) or {}
        bip = [float(x) for row in (h.get("Bipolar") or []) for x in row if x]
        mono = [float(x) for x in (h.get("Monopolar") or []) if x]
        out[hemi] = {
            "bipolar_max_ohm": max(bip) if bip else None,
            "bipolar_min_ohm": min(bip) if bip else None,
            "bipolar_median_ohm": _st.median(bip) if bip else None,
            "monopolar_max_ohm": max(mono) if mono else None,
            "n_bipolar_pairs": len(bip),
            "lead_model": h.get("LeadModel"), "lead_type": _lead_type(h.get("LeadModel")),
        }
        # THE SPURIOUS-FAIL CASE the PI named: the truly newest recording of all ran in the
        # automatic mode and reads above the open-circuit limit, while the fixed-current recording
        # this rule actually trusts reads inside it. Recorded here, per hemisphere, so the ledger
        # can state both numbers rather than only the one D16 acts on.
        if fixed_rows and newest_current == "automatic_increase":
            hn = newest.get(hemi) or {}
            bip_auto = [float(x) for row in (hn.get("Bipolar") or []) for x in row if x]
            auto_worst = max(bip_auto) if bip_auto else None
            chosen_worst = out[hemi]["bipolar_max_ohm"]
            if (auto_worst is not None and auto_worst > _OPEN_LIMIT_OHM
                    and chosen_worst is not None and chosen_worst <= _OPEN_LIMIT_OHM):
                out[hemi]["automatic_newest_ohm"] = auto_worst
                out[hemi]["automatic_newest_date"] = _iso(getattr(newest_row, "date", None))
    return out


def candidate_impedance_ohm(facts, hemisphere):
    """The single number D16's predicate compares against its short and open limits.

    The WORST bipolar reading on the sensing hemisphere. A sensing channel is a bipolar pair, so a
    bipolar reading is the right quantity; taking the worst on the hemisphere is deliberately
    conservative, because the matrix index to contact-label mapping for a segmented SenSight lead is
    not one-to-one and picking the wrong cell would silently report a healthy pair in place of a
    faulty one.
    """
    if not (facts or {}).get("available"):
        return None
    return ((facts.get(hemisphere) or {}).get("bipolar_max_ohm"))


# ---------------------------------------------------------------------------------------------
# FACTS THAT CAN ONLY COME FROM A PERSON READING THE PROGRAMMER
# ---------------------------------------------------------------------------------------------
#: Values the investigator supplied directly, with the date and the fact that they were STATED
#: rather than measured from the record. This block is a stopgap and should be read as one: these
#: belong in a per-participant database row with an audit trail, not in source. They are here, with
#: provenance on every line, because the alternative was leaving eleven device rules unevaluable —
#: and an unevaluable rule blocks, so the whole verdict was stuck behind values that take two
#: minutes to read off a programmer.
#:
#: The rule for adding to this block: a value goes here ONLY if a person read it off the device or
#: stated it as a clinical decision. Anything derivable from the record must be derived, because a
#: stated value cannot be re-checked when the record changes. Two candidate values were REFUSED
#: entry on exactly that basis — the LFP capture amplitude (D09), because the surveys measure it and
#: the stated estimate of 2 uVp would have passed a gate the measured 0.27 uVp median fails, and
#: the impedance (D16), because 548 recordings carry it.
PI_STATED_FACTS = {}  # Participant-specific values remain in private reviewed storage.


#: D31. WHAT THE DEVICE HAS ACTUALLY ACCEPTED, per hemisphere, as (rate_hz, pulse_width_us).
#:
#: Measured 2026-09-05 by walking all 1,154 session reports and collecting every group carrying a
#: ``SensingChannel``. This exists because D31 was written to compare a candidate against the
#: BrainSense parameter envelope, and that envelope is NOT PUBLISHED: the A610 guide states only
#: that the maximum pulse width and maximum rate are lower and the minimum rate higher than for a
#: group without BrainSense, without giving any of the three numbers, and a search of the entire
#: JSON corpus found no field carrying them either. The only path in 1,154 files combining a
#: rate/pulse-width/frequency name with a limit word is ``IndefiniteStreaming[].SampleRateInHz``,
#: which is the sensing sample rate and not a stimulation limit.
#:
#: So the rule stops asking for a number it will never get and asks an answerable question instead:
#: has this exact rate and pulse width been programmed in a BrainSense group on this hemisphere?
#: A demonstrated configuration is stronger evidence than a limit comparison, because the device
#: itself accepted it.
#:
#: Two asymmetries in this table matter and would be hidden by pooling the hemispheres. 55 Hz with
#: 60 us appears 1,274 times on the LEFT and never on the right; 165 Hz with 60 us appears 152
#: times on the LEFT and never on the right, where 165 Hz has only run at 80 and 160 us. The
#: observed minimum rate in a sensing group is 55 Hz on both sides against 10 Hz in non-sensing
#: groups, which is consistent with the guide's claim that the BrainSense minimum is higher, and
#: bounds it at 55 Hz or below without revealing its value.
BRAINSENSE_PROGRAMMED_PAIRS = {}

#: Provenance for the table above, carried onto the report so a reader can tell a measurement from
#: an assertion and can see how stale it is.
BRAINSENSE_PAIRS_PROVENANCE = (
    "measured 2026-09-05 from all 1,154 RCS08 session reports; counts are group records carrying "
    "a SensingChannel, not distinct programming events"
)


def brainsense_pair_programmed(rate_hz, pulse_width_us, hemisphere):
    """Has this exact (rate, pulse width) been programmed in a BrainSense group on this side?

    Returns True when the pair appears in the measured table, False when the hemisphere is known
    and the pair is absent from it, and None when any input is missing or the hemisphere is not
    one this device has. The False case is deliberately NOT a device prohibition: absence means the
    combination has never been demonstrated here, which is a weaker statement than being
    forbidden, and the caller must present it that way.
    """
    if hemisphere not in BRAINSENSE_PROGRAMMED_PAIRS:
        return None
    if rate_hz is None or pulse_width_us is None:
        return None
    try:
        key = (float(rate_hz), float(pulse_width_us))
    except (TypeError, ValueError):
        return None
    return key in BRAINSENSE_PROGRAMMED_PAIRS[hemisphere]


def facts_for_participant(participant_uid, impedance_recordings=None, *,
                          hemisphere=None, channel=None,
                          sensing_hemisphere=None, actuated_hemisphere=None,
                          stated_facts=None, session_summary=None):
    """Assemble every device fact this module can establish for one participant.

    Measured values take precedence over stated ones wherever both exist, and the returned dict
    records which is which under ``_provenance`` so a reader can tell a reading from an assertion.

    TWO SIDES, NOT ONE (review C1, 2026-09-12). A fact about the SENSING lead -- the impedance
    (D16), the lead family that sets its short limit, the device's artefact verdict (D17), the
    survey's LFP bins (D09), whether the contact has ever been a sensing channel (D15) -- is read
    from ``sensing_hemisphere``. A fact about the STIMULATED side -- the capture amplitudes and
    the adaptive limits they become (D24, D27, D28), the capture pulse width, the paused amplitude
    (D34) -- is read from ``actuated_hemisphere``. Until this split one ``hemisphere`` served both,
    and the adapter filled it with the ACTUATED side, which the page always sent as "Left": a band
    on a right contact was judged on the left lead's impedance and the left survey's flags. The
    plain ``hemisphere`` keyword is kept as the value for whichever of the two is not given, so a
    caller that names one side still gets one-sided facts as before.
    """
    sens = sensing_hemisphere or hemisphere
    act = actuated_hemisphere or hemisphere
    stated = dict(stated_facts or {})
    out, prov = {}, {}

    paused = stated.pop("paused_amplitude_mA_by_hemisphere", None)
    if paused and act in (paused or {}):
        out["paused_amplitude_mA"] = paused[act]
        prov["paused_amplitude_mA"] = f"caller-supplied reviewed declaration for the {act} hemisphere"
    for k, v in stated.items():
        out[k] = v
        prov[k] = "caller-supplied reviewed declaration"
    if "brainsense_min_rate_hz" in out:
        prov["brainsense_min_rate_hz"] = ("stated by PI (StimOptimizer.routines.percept_adaptive."
                                          "MIN_ADAPTIVE_RATE_HZ, the same number the Stim "
                                          "Optimizer page enforces)")

    imp = impedance_facts(impedance_recordings or [])
    if imp.get("available"):
        # Every impedance fact below is about the SENSING lead: the sensing channel is a bipolar
        # pair on that lead, and D16 asks whether that pair can be sensed from.
        hemisphere = sens
        ohm = candidate_impedance_ohm(imp, hemisphere) if hemisphere else None
        if ohm is not None:
            out["impedance_ohms"] = ohm
            out["impedance_min_ohms"] = (imp.get(hemisphere) or {}).get("bipolar_min_ohm")
            prov["impedance_min_ohms"] = "measured: minimum non-placeholder bipolar pair in the selected impedance test"
            # Be exact about what this number IS. It is the worst bipolar pair WITHIN the record
            # D16 actually trusts (the newest FIXED-current test when one exists, decision
            # 2026-09-12; otherwise the newest test of any kind, which is the whole record here
            # before that decision) — and the difference is not academic: on 2026-09-04 an ingest
            # brought in a newer, better measurement and D16 flipped from fail to pass with no code
            # change, while 1265 of 15540 historical left-lead readings remain above the
            # open-circuit limit. The old wording said "across N recordings", which would have let
            # a reader take a currently-sound lead for a never-faulty one.
            _hist = ((imp.get("history") or {}).get(hemisphere) or {})
            _worst_ever_txt = (
                f"worst EVER {_hist.get('bipolar_max_ohm_ever')} ohm with "
                f"{_hist.get('n_above_open_limit')} of {_hist.get('n_readings')} readings above "
                f"the 10000 ohm open limit")
            _cur = imp.get("measurement_current")
            out["impedance_measurement_current"] = _cur
            out["impedance_measured_at"] = imp.get("measured_at")
            if isinstance(_cur, float):
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the newest FIXED-current impedance test "
                    f"({_cur:g} mA, {imp.get('measured_at')}, device status "
                    f"{imp.get('status_chosen')}) on the {hemisphere} lead; {_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    f"measured: {_cur:g} mA, the Amplitude field of the impedance test D16 uses "
                    f"for the {hemisphere} lead")
                _hemi_block = imp.get(hemisphere) or {}
                _auto_ohm = _hemi_block.get("automatic_newest_ohm")
                _auto_date = _hemi_block.get("automatic_newest_date")
                if _auto_ohm is not None:
                    out["impedance_ohms_automatic_newest"] = _auto_ohm
                    out["impedance_automatic_measured_at"] = _auto_date
                    prov["impedance_ohms"] += (
                        f". The newest impedance test of all ({_auto_date}) used the automatic "
                        f"low-current mode and read {_auto_ohm:g} ohm, which the PI has ruled a "
                        f"spurious fail at that measurement current (2026-09-12), not a real open "
                        f"circuit")
            elif _cur == "automatic_increase":
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the NEWEST impedance test on the "
                    f"{hemisphere} lead ({imp.get('measured_at')}, device status "
                    f"{imp.get('status_chosen')}), which used the device's automatic low-current "
                    f"mode; no fixed-current impedance test is on record, and one would settle "
                    f"whether this reading is a spurious fail at low measurement current "
                    f"(PI decision 2026-09-12); {_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    "measured: the device's automatic low-current mode, the only impedance test "
                    f"on record for the {hemisphere} lead")
            else:
                prov["impedance_ohms"] = (
                    f"measured: worst bipolar pair in the NEWEST of {imp['n_records']} impedance "
                    f"recordings on the {hemisphere} lead (status {imp.get('status_newest')}); "
                    f"{_worst_ever_txt}")
                prov["impedance_measurement_current"] = (
                    "measured: no measurement current was recorded on the impedance test used")
            prov["impedance_measured_at"] = (
                f"measured: date of the impedance test D16 uses for the {hemisphere} lead")
        out["impedance_tested"] = True
        prov["impedance_tested"] = f"measured: {imp['n_records']} impedance recordings on record"
        # The SENSING lead's own family (review C11): the short-circuit limit D16 applies depends
        # on it, and the two leads need not match. Falls back to the newest record's left-lead
        # value only when no side is known, which is what every caller got before.
        _lt_side = ((imp.get("lead_type_by_hemisphere") or {}).get(hemisphere)
                    if hemisphere else None)
        _lm_side = ((imp.get("lead_model_by_hemisphere") or {}).get(hemisphere)
                    if hemisphere else None)
        if _lt_side:
            out["lead_type"] = _lt_side
            prov["lead_type"] = f"measured: LeadModel {_lm_side} on the {hemisphere} lead"
        elif imp.get("lead_type"):
            out["lead_type"] = imp["lead_type"]
            prov["lead_type"] = f"measured: LeadModel {imp.get('lead_model')}"
        out["_impedance_status"] = imp.get("status_newest")
        out["_impedance_status_counts"] = imp.get("status_counts")
    # Facts from the raw session reports: capture amplitudes, adaptive limits, the device's own
    # artefact verdict, cycling, and the per-bin LFP spectrum D09 consumes.
    srf, srf_prov = session_report_facts_for(participant_uid, channel=channel,
                                             sensing_hemisphere=sens, actuated_hemisphere=act, summary=session_summary)
    for k, v in srf.items():
        if v is not None and out.get(k) is None:
            out[k] = v
            prov[k] = srf_prov.get(k, "measured: session reports")

    out["_provenance"] = prov
    return out


# ---------------------------------------------------------------------------------------------
# FACTS FROM THE SESSION REPORTS
# ---------------------------------------------------------------------------------------------
#: Fraction of a channel's surveys that must flag an artefact before D17 treats the channel as
#: contaminated. DECLARED BY THIS MODULE, not published by the manufacturer, whose guidance is
#: qualitative. Set at one half — the artefact must be the channel's prevailing state, not an
#: occasional observation — because D17's predicate is categorical and a rule that refuses a
#: configuration on four adverse surveys out of two hundred is answering a different question from
#: the one it asks. The rate itself is always reported regardless of this threshold, so softening
#: the gate does not hide the observation.
ARTIFACT_FLAG_RATE_LIMIT = 0.5

#: Artefact statuses that do NOT count against D17. PI decision, 2026-09-04: "ignore the impedance
#: failures, they should count normally."
#:
#: The reasoning, so a later reader does not undo it as an oversight. D17 asks whether the device
#: detected a SIGNAL artefact on the sensing channel — cardiac, motion or atypical morphology — any
#: of which corrupts the band-power estimate the control loop would read. ``IMPEDANCE_FAILURE`` is
#: not that. It reports that the electrode's impedance measurement failed or fell outside range,
#: which is a statement about the hardware and is already governed by D16, where it is evaluated
#: against the manufacturer's published short and open limits. Counting it here as well penalises
#: one hardware fact twice through two independent rules, and the second penalty carries no
#: additional information: on this participant the same four surveys drive both. A survey whose
#: only adverse finding is an impedance failure is therefore treated as a normal survey for D17,
#: and the impedance question is answered where it belongs.
#:
#: The status is still COUNTED AND REPORTED in ``artifact_flag_counts``, so nothing is hidden — it
#: simply does not enter the numerator of the artefact rate. D16 continues to carry the lead's full
#: impedance history, including the 1265 of 15540 left-lead readings above the open-circuit limit.
D17_NON_ARTEFACT_STATUSES = ("ARTIFACT_NOT_PRESENT", "IMPEDANCE_FAILURE")


#: THE LAST FALLBACK: the per-participant summary ``session_report_facts.scan_folder`` produced
#: ONCE, on 2026-09-05, over a plain-JSON folder on a shared drive, and committed next to the
#: module. Until 2026-09-12 it was the only summary and nothing refreshed it, so it is stale today
#: (110 Hz and adaptive NOT_CONFIGURED where the device says 55 Hz and RUNNING). ``_load_summary``
#: now reads the summary built from the INGESTED reports out of the one store first, and reaches
#: this file only when the store holds nothing for the participant; the provenance sentence on
#: every fact says which was used.
_SUMMARY_FILES = {}  # Participant-specific values remain in private reviewed storage.
_COMMITTED_SCAN_DATE = "2026-09-05"
_COMMITTED_SCAN_SOURCE = "shared-drive"


def _committed_summary(participant_uid):
    """The committed ``_facts_<code>.json`` for this participant, or ``{}``."""
    import json as _json
    name = _SUMMARY_FILES.get(str(participant_uid))
    if not name:
        return {}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    try:
        with open(path) as fh:
            return _json.load(fh)
    except Exception:
        return {}


def _ingested_file_set(participant_uid):
    """``(rows, signature, error)`` for the participant's ingested session reports: one query over
    ``SourceFile``, no file opened (decision 24). ``error`` names why the record could not be
    queried -- no Django, no database -- so the caller can say so rather than guess."""
    from . import session_report_facts as _srf
    try:
        rows = _srf.session_report_files(participant_uid)
    except Exception as exc:                                     # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"
    return rows, _srf.file_set_signature(rows), None


def _load_summary(participant_uid):
    """``(summary, resolution)``: the best session-report summary available and where it came from.

    THE ORDER, each step cheap enough for a page request (nothing here opens a session report):

    (a) the STORED summary whose key equals the participant's CURRENT session-report file set --
        the answer is up to date and no rebuild is needed;
    (b) else the NEWEST stored summary of that kind for the participant, whatever file set it was
        built from -- used, marked STALE with how many newer reports it misses, and a rebuild is
        started in the background;
    (c) else the committed ``_facts_<code>.json`` -- used, marked as the 2026-09-05 shared-drive
        scan, and a rebuild started in the background.

    ``resolution`` carries ``source`` (``current`` / ``stale`` / ``committed`` / ``none``), the
    ``sentence`` every fact's provenance is prefixed with, and ``launch`` (what the launcher did,
    or None when nothing was started). A summary handed back from (b) or (c) is exactly as wrong as
    it was before this resolver existed; what is new is that the report SAYS so, and that the next
    request after the rebuild lands gets (a).
    """
    from . import session_report_facts as _srf
    uid = str(participant_uid)
    rows, sig, err = _ingested_file_set(uid)
    n_ing = len(rows) if rows is not None else None
    _newest_row = _srf.newest_by_stamp(rows) if rows else None
    newest_ing = str(_newest_row.name or "") if _newest_row is not None else None
    res = {"source": "none", "sentence": "no session-report summary is available",
           "launch": None, "n_ingested": n_ing, "newest_ingested_stamp": newest_ing,
           "ingested_query_error": err}

    if sig is not None:
        S = _cache_store.load(_srf.SUMMARY_KIND, uid, sig)
        if isinstance(S, dict) and S:
            res["source"] = "current"
            res["sentence"] = (f"rebuilt from {S.get('n_files')} ingested session reports, newest "
                               f"{S.get('newest_stamp')}, built {str(S.get('built_utc') or '')[:10]}")
            return S, res

        # Research reports run inside an explicitly requested AnalysisJob. Build the current
        # summary here instead of launching a detached process or serving an older source set.
        if rows:
            S = _srf.summary_from_ingested(uid, rows=rows)
            if S.get("n_unreadable"):
                raise RuntimeError("Some approved session reports could not be decoded")
            _cache_store.store(_srf.SUMMARY_KIND, uid, sig, S, writer="closed_loop",
                               trigger="explicit_research_report", provenance=[])
            res["source"] = "current"
            res["sentence"] = f"rebuilt from {S.get('n_files')} approved session reports"
            return S, res

        S, stamp = _cache_store.load_newest(_srf.SUMMARY_KIND, uid)
        if isinstance(S, dict) and S:
            old_key = str(S.get("newest_stamp_key") or _srf.report_stamp(S.get("newest_stamp")))
            newer = sum(1 for r in rows if _srf.report_stamp(r.name) > old_key)
            res["source"] = "stale"
            res["sentence"] = (f"STALE: built from {S.get('n_files')} files on "
                               f"{str(S.get('built_utc') or '')[:10]}; {newer} newer session "
                               f"reports are not included")
            res["launch"] = launch_summary_rebuild_in_background(uid, sig)
            return S, res

    S = _committed_summary(uid)
    if S:
        res["source"] = "committed"
        if sig is not None:
            rec = f"the ingested record has {n_ing} reports, newest {newest_ing}"
            res["launch"] = launch_summary_rebuild_in_background(uid, sig)
        elif rows is not None:
            rec = "the ingested record has no session reports"
        else:
            rec = f"the ingested record could not be queried ({err})"
        res["sentence"] = (f"committed scan of {_COMMITTED_SCAN_DATE} over {S.get('n_files'):,} "
                           f"{_COMMITTED_SCAN_SOURCE} files; {rec}")
        return S, res
    return {}, res


def session_report_facts_for(participant_uid, *, channel=None, hemisphere=None,
                             sensing_hemisphere=None, actuated_hemisphere=None, summary=None):
    """Facts for the six rules the platform decoder does not keep in queryable form.

    Two sides, as in ``facts_for_participant`` (review C1): the capture amplitudes, adaptive
    limits and capture pulse width are read for the ACTUATED side; the artefact verdict, the LFP
    bins and the sensing-channel count for the SENSING side. ``hemisphere`` stands in for either
    that is not given.

    Every value here comes from the raw session reports rather than a person's recollection, and the
    DISTRIBUTION is carried alongside the newest value because for several of these rules the
    distribution is the finding — D27 is violated by 90% of the right-hemisphere capture records
    while the most recent capture is compliant, and reporting only one of those would mislead.

    Which summary the facts were read from -- the stored one for the current file set, a stale
    stored one, or the committed 2026-09-05 scan -- is written into every provenance sentence and
    into ``session_report_summary_source``, so a ledger row can be read without wondering whether
    the value behind it is the device as it is today.
    """
    from . import session_report_facts as _srf
    sens = sensing_hemisphere or hemisphere
    act = actuated_hemisphere or hemisphere
    S, res = (_load_summary(participant_uid) if summary is None else
              (summary, {"sentence": "caller-supplied reviewed session summary", "source": "supplied", "launch": None}))
    if not S:
        return {}, {}
    out, prov = {}, {}
    n = S.get("n_files")
    tag = f"measured: session reports, {n} files ({res['sentence']})"
    out["session_report_summary_source"] = res["source"]
    # One sentence, carried as this key's provenance: which summary, and -- when it was not the
    # current one -- whether the rebuild that would make it current was started. Kept in the
    # provenance of a key that IS in ``out``, because ``facts_for_participant`` copies provenance
    # only for keys it copies values for.
    prov["session_report_summary_source"] = res["sentence"]
    if res.get("launch") is not None:
        prov["session_report_summary_source"] += (
            "; background rebuild started" if res["launch"].get("launched")
            else f"; background rebuild not started: {res['launch'].get('reason')}")

    # D28 — adaptive limits and whether adaptive has ever run. The STIMULATED side's capture.
    cap = (S.get("capture_newest") or {}).get(act or "") or {}
    if cap.get("lower_mA") is not None:
        out["capture_amp_low_mA"] = float(cap["lower_mA"])
        prov["capture_amp_low_mA"] = tag + " (newest capture)"
    if cap.get("upper_mA") is not None:
        out["capture_amp_high_mA"] = float(cap["upper_mA"])
        prov["capture_amp_high_mA"] = tag + " (newest capture)"
        # D28: the adaptive amplitude limits INHERIT the capture amplitudes (A610 p. 41).
        out["adaptive_min_mA"] = float(cap["lower_mA"]) if cap.get("lower_mA") is not None else None
        out["adaptive_max_mA"] = float(cap["upper_mA"])
        prov["adaptive_max_mA"] = tag + " (inherited from capture per D28)"
    if cap.get("pw_us") is not None:
        out["capture_pulse_width_us"] = float(cap["pw_us"])
        prov["capture_pulse_width_us"] = tag + " (newest capture)"

    # D17 — the device's own artefact verdict for this channel
    # D17 AND EVER-PRESENCE: a bug of mine, fixed 2026-09-04. The device raises an artefact flag
    # PER SURVEY, and this code used to flatten the per-channel counts into a presence list — so a
    # channel with 188 surveys reading ARTIFACT_NOT_PRESENT and 4 reading IMPEDANCE_FAILURE handed
    # D17 the list ['IMPEDANCE_FAILURE', 'SQC_ARTIFACT_PRESENT'] and the predicate, which tests
    # `len(flags) == 0`, refused the configuration outright on a 1.7% flag rate accumulated over
    # every survey ever recorded. That is not what the rule asks. The rule asks whether an artefact
    # is flagged on the channel we are about to use, and a flag seen four times in two hundred
    # surveys is a quality observation to report, not a categorical bar.
    #
    # The fix reports the RATE and applies the flag only when it is the prevailing state of the
    # channel. The threshold below is OURS, not the manufacturer's, and it is stated here so it can
    # be argued with: a channel whose surveys flag an artefact more often than not is treated as
    # contaminated, and anything less is reported as a rate. The device's own guidance is
    # qualitative ("using a configuration with an artefact detected may interfere"), so no published
    # rate exists to defer to.
    art = S.get("artifact_status") or {}
    key = _match_survey_channel(art, channel, sens)
    if key:
        counts = {k: v for k, v in (art.get(key) or {}).items() if k}
        total = sum(counts.values())
        adverse = {k: v for k, v in counts.items()
                   if k not in D17_NON_ARTEFACT_STATUSES}
        n_adverse = sum(adverse.values())
        rate = (n_adverse / total) if total else None
        out["artifact_flag_rate"] = rate
        out["artifact_flag_counts"] = counts
        # The flag list the predicate consumes now carries only the PREVAILING state.
        out["artifact_flags"] = (sorted(adverse) if (rate is not None and rate > ARTIFACT_FLAG_RATE_LIMIT)
                                 else [])
        out["artifact_excluded_counts"] = {k: v for k, v in counts.items()
                                           if k in D17_NON_ARTEFACT_STATUSES
                                           and k != "ARTIFACT_NOT_PRESENT"}
        prov["artifact_flags"] = (
            tag + f" (channel {key}: {n_adverse} of {total} surveys flag a SIGNAL artefact, "
            f"{100 * rate:.1f}%, against a {100 * ARTIFACT_FLAG_RATE_LIMIT:.0f}% limit declared by "
            f"this module. IMPEDANCE_FAILURE is excluded from the numerator by PI decision because "
            f"D16 governs impedance; counts {counts})")
        prov["artifact_flag_rate"] = prov["artifact_flags"]

    # D32 — cycling is the only one of the five feature exclusions the reports carry
    # D32 reads the SENSING groups only; see session_report_facts for why the earlier
    # device-wide count was answering a different question.
    # D32's five feature exclusions, read from the NEWEST ACTIVE SENSING GROUP — the configuration
    # a clinician would actually program — with the device-wide history reported alongside.
    cyc = S.get("cycling_by_group_kind") or {}
    d32 = S.get("d32_newest_active_sensing_group") or {}
    for k in ("cycling_in_group", "multiple_rates_in_group", "interleaving_in_group",
              "patient_limits_configured", "has_pocket_adaptor"):
        if d32.get(k) is not None:
            out[k] = d32[k]
            prov[k] = tag + " (newest ACTIVE group with sensing configured)"
    if "cycling_in_group" in out:
        prov["cycling_in_group"] = (
            tag + f" (GroupSettings.Cycling.Enabled in the newest ACTIVE sensing group = "
            f"{out['cycling_in_group']}; device-wide history, keyed sensing/active/enabled: {cyc})")
    if d32:
        prov["_d32_group_shape"] = (
            f"{d32.get('n_programs')} program(s), rates {d32.get('rates_seen')}, "
            f"pulse widths {d32.get('pulse_widths_seen')}")

    # D15 — has this exact contact ever been configured as a sensing channel on this side? MEASURED
    # from the summary's per-contact counts (review C5, 2026-09-12) rather than stated once for
    # ONE_THREE_LEFT and copied onto every contact. A key with no side in its name (the summary
    # counts ``ZERO_AND_THREE`` as well as ``ZERO_THREE_LEFT``) cannot say which lead it was on and
    # is not counted. No ``sensing_channels`` block at all means no key, so the rule reads "not
    # determinable" rather than passing on nothing.
    if channel and sens and isinstance(S.get("sensing_channels"), dict):
        n_setup = setup_channel_count(S.get("sensing_channels") or {}, channel, sens)
        out["channel_is_brainsense_setup_channel"] = n_setup > 0
        prov["channel_is_brainsense_setup_channel"] = (
            tag + f" (measured: {n_setup} groups carried {channel} as a SensingChannel on the "
            f"{sens} side)")

    # D09 — the per-bin spectrum, which is the form the rule now consumes. The SENSING lead's
    # survey.
    bins = _srf.candidate_lfp_bins(S, channel, sens) if channel else []
    if bins:
        out["lfp_bins_uvp"] = bins
        prov["lfp_bins_uvp"] = tag + f" ({len(bins)} survey bins, median per bin)"
    return out, prov


def setup_channel_count(sensing_channels, channel, hemisphere):
    """How many group records in the summary carried ``channel`` as a ``SensingChannel`` on
    ``hemisphere``: the sided keys of ``sensing_channels`` (``ZERO_TWO_LEFT``) whose pair equals
    the candidate's pair and whose side agrees. Sideless keys (``ZERO_AND_TWO``) are skipped: they
    cannot be attributed to a lead. Pure, so the test hands it a dict."""
    if not channel or not hemisphere:
        return 0
    want = str(channel).upper().replace("_LEFT", "").replace("_RIGHT", "").replace("_AND_", "").replace("_", "")
    total = 0
    for key, n in (sensing_channels or {}).items():
        pair, _, hemi = str(key).rpartition("_")
        if hemi.lower() not in ("left", "right") or hemi.lower() != str(hemisphere).lower():
            continue
        if pair.upper().replace("_AND_", "").replace("_", "") == want:
            try:
                total += int(n)
            except (TypeError, ValueError):
                continue
    return total


def _match_survey_channel(mapping, channel, hemisphere):
    """Reconcile a candidate's channel name with the survey's electrode-pair spelling.

    A candidate says ``ONE_THREE_LEFT``; the survey says ``ONE_AND_THREE_Left``. Returning None
    when no match is found is deliberate — a rule that receives no flags reports "not determinable"
    rather than "no artefact", and inventing the latter is how a contaminated channel would pass.
    """
    if not channel:
        return None
    want = str(channel).upper().replace("_LEFT", "").replace("_RIGHT", "").replace("_", "")
    for key in mapping:
        pair, _, hemi = str(key).rpartition("_")
        if hemisphere and hemi.lower() != str(hemisphere).lower():
            continue
        if pair.upper().replace("_AND_", "").replace("_", "") == want:
            return key
    return None


# Participant-specific provenance and examples are maintained outside source control.

#: Off switch that needs no deployment: set the environment variable
#: ``SESSION_REPORT_SUMMARY_BACKGROUND=0`` on the server (or this flag False in a running process)
#: and no page request starts a rebuild; nothing stored changes and nothing is deleted.
SESSION_REPORT_SUMMARY_BACKGROUND = True
SESSION_REPORT_SUMMARY_BACKGROUND_ENV = "SESSION_REPORT_SUMMARY_BACKGROUND"

#: How long one launch suppresses another for the SAME file-set key. Longer than a whole-record
#: rebuild takes, because a second scan started while the first is still decrypting 4 GB costs a
#: second whole-machine job and buys nothing.
SESSION_REPORT_SUMMARY_LAUNCH_COOLDOWN_SECONDS = 3600.0

#: PRODUCTION-ROOT SAFETY, default the safe one (decision 96's own finding: the unit suite was
#: found spawning real management commands for a fake participant). A run started while the store
#: is pointed at a caller's own root would scan the real database and write where nothing reads.
#: A test that means to exercise the launcher sets this True and replaces ``_spawn_detached``.
SESSION_REPORT_SUMMARY_LAUNCH_UNDER_OVERRIDE_ROOT = False


def _summary_launch_marker(sig):
    """The file whose age says when a rebuild was last started for this exact file-set key, or
    None when there is nowhere to write it. Beside the stored entries, named by the key, so a new
    ingest (a new key) gets its own cooldown rather than inheriting the old one's."""
    from . import session_report_facts as _srf
    d = _cache_store.kind_dir(_srf.SUMMARY_KIND)
    if not d:
        return None
    return os.path.join(d, f".launched.{_cache_store.signature_key(sig)}")


def _summary_command_argv(participant_uid):
    """The command line for the rebuild, or None when ``manage.py`` cannot be found."""
    manage = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "manage.py")
    if not os.path.isfile(manage):
        return None
    return [sys.executable, manage, "rebuild_session_report_summary",
            "--participant", str(participant_uid)]


def _spawn_detached(argv, log_path):
    """Start a command that outlives this request and this worker: its own session, so a recycled
    worker does not take it down; output to a file, because nothing reads a pipe and a full one
    would block the child."""
    log = open(log_path, "a")
    try:
        subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True, close_fds=True)
    finally:
        log.close()                      # the child holds its own copy of the descriptor


def launch_summary_rebuild_in_background(participant_uid, sig):
    """Heavy analysis is launched only by an explicit canonical AnalysisJob."""
    return {"launched": False, "reason": "Run the analysis explicitly to compute this product"}


# Participant-specific provenance and examples are maintained outside source control.
_ACTIVE_GROUP_MEMO = {}
_ACTIVE_GROUP_MEMO_MAX = 32


def active_sensing_group_from_report(d):
    """The device's newest ACTIVE group with sensing configured, from one decoded session report.

    Pure: takes the report as a dict and returns a dict, so it is testable with no Django. Reads
    ``Groups.Final`` -- the groups as they stood at the END of the session, which is what the device
    left the clinic running -- and takes the first group that is both ``ActiveGroup`` and carries at
    least one ``SensingChannel``. An active group WITHOUT sensing is not it (D30 is about the rate
    BrainSense froze), and an inactive group with sensing is not it either (a group nobody is
    running freezes nothing a clinician is about to program against).

    Returns ``{}`` when the report has no such group, so the caller supplies nothing and D30 stays
    not determinable rather than being handed a fabricated rate.
    """
    if not isinstance(d, dict):
        return {}
    groups = (d.get("Groups") or {}).get("Final") or []
    for g in groups:
        if not isinstance(g, dict) or not g.get("ActiveGroup"):
            continue
        ps = g.get("ProgramSettings") or {}
        sens = ps.get("SensingChannel") or []
        if not sens:
            continue
        rate = ps.get("RateInHertz")
        try:
            rate = float(rate) if rate is not None else None
        except (TypeError, ValueError):
            rate = None
        out = {
            # The export spells the group as an enum ("GroupIdDef.GROUP_D"); keep the part a
            # clinician would say, "GROUP_D".
            "active_sensing_group": str(g.get("GroupId")).split(".")[-1] if g.get("GroupId") is not None else None,
            "active_sensing_group_rate_hz": rate,
            "active_sensing_group_pulse_widths_us": [c.get("PulseWidthInMicroSecond")
                                                     for c in sens if isinstance(c, dict)],
            "active_sensing_group_adaptive_status": [c.get("AdaptiveTherapyStatus")
                                                     for c in sens if isinstance(c, dict)],
            "session_report_date": d.get("SessionDate"),
            # The closed-loop timing and threshold values the device is RUNNING on each side, so
            # the parameter card can print "programmed today" beside every recommendation
            # (2026-09-13). Read from the same group; the export's own field names are kept in
            # the comment beside each key.
            "active_sensing_group_timing": programmed_closed_loop_timing(sens),
        }
        return out
    return {}


def programmed_closed_loop_timing(sensing_channels):
    """Per hemisphere, the adaptive timing and threshold fields as programmed in one group.

    Pure. ``sensing_channels`` is the ``ProgramSettings.SensingChannel`` list of a group. Returns
    ``{"Left": {...}, "Right": {...}}`` with milliseconds for every duration, the two thresholds
    in the device's own units, the two adaptive amplitude limits in mA, and the sensing centre in
    Hz; a field the export does not carry is ``None`` rather than invented. An empty list gives
    ``{}``.
    """
    out = {}
    for c in sensing_channels or []:
        if not isinstance(c, dict):
            continue
        side = str(c.get("HemisphereLocation") or "").split(".")[-1] or None
        if side is None:
            continue
        adaptive = c.get("AdaptiveTherapy") or {}
        setup = c.get("SensingSetup") or {}

        def _f(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        out[side] = {
            "onset_upper_ms": _f(adaptive.get("UpperThresholdOnsetInMilliSeconds")),      # AdaptiveTherapy.UpperThresholdOnsetInMilliSeconds
            "onset_lower_ms": _f(adaptive.get("LowerThresholdOnsetInMilliSeconds")),      # AdaptiveTherapy.LowerThresholdOnsetInMilliSeconds
            "detection_blanking_ms": _f(adaptive.get("DetectionBlankingDurationInMilliSeconds")),
            "adaptive_startup_delay_ms": _f(adaptive.get("AdaptiveStartupDelayInMilliSeconds")),
            "transition_up_ms": _f(c.get("TransitionUpInMilliSeconds")),
            "transition_down_ms": _f(c.get("TransitionDownInMilliSeconds")),
            "averaging_ms": _f(setup.get("AveragingDurationInMilliSeconds")),           # SensingSetup.AveragingDurationInMilliSeconds
            "sensing_centre_hz": _f(setup.get("FrequencyInHertz")),
            "upper_threshold": _f(c.get("UpperLfpThreshold")),
            "lower_threshold": _f(c.get("LowerLfpThreshold")),
            "upper_limit_mA": _f(c.get("UpperLimitInMilliAmps")),
            "lower_limit_mA": _f(c.get("LowerLimitInMilliAmps")),
            "suspend_amplitude_mA": _f(c.get("SuspendAmplitudeInMilliAmps")),
            "adaptive_status": str(c.get("AdaptiveTherapyStatus") or "").split(".")[-1] or None,
        }
    return out


def _memoised_active_group_facts(key, build):
    """Serve ``build()``'s answer from the memo under ``key``; a new key is a miss.

    Split out from ``active_sensing_group_facts`` so the miss-on-new-file rule can be tested with
    no database: the key is the file identity, and the test changes it.
    """
    hit = _ACTIVE_GROUP_MEMO.get(key)
    if hit is not None:
        return dict(hit)
    facts = dict(build() or {})
    if len(_ACTIVE_GROUP_MEMO) >= _ACTIVE_GROUP_MEMO_MAX:
        _ACTIVE_GROUP_MEMO.pop(next(iter(_ACTIVE_GROUP_MEMO)))
    _ACTIVE_GROUP_MEMO[key] = dict(facts)
    return facts


def active_sensing_group_facts(participant):
    """The device's newest active sensing group for one participant, read live from the newest
    ingested session report; ``{}`` when there is no session report or no active sensing group.

    The Django imports live inside the function because this module is imported by tests that
    have no Django. ``participant`` may be a Participant row or its uid.
    """
    import json as _json
    from Server import models as _m
    from modules import DataCurator as _DC
    from . import session_report_facts as _srf

    p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
    if p is None:
        return {}
    # Participant-specific provenance and examples are maintained outside source control.
    sfs = _srf.session_report_files(p)
    if not sfs:
        return {}
    newest = _srf.newest_by_stamp(sfs)
    key = (str(p.uid), str(newest.uid), str(newest.hashed or ""))

    def _build():
        raw = _DC.loadCacheFile(newest)
        d = _json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        return active_sensing_group_from_report(d)

    return _memoised_active_group_facts(key, _build)


# Retained active Aditya interfaces.
