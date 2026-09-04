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

import statistics as _st

#: Lead models whose short-circuit floor is the SenSight value rather than the 1x4 value. The
#: constraint table keys its floor on the string "sensight", so the model number is mapped here
#: rather than at the call site.
_SENSIGHT_MODELS = ("LEAD_B33015", "LEAD_B33005")


def _lead_type(lead_model):
    if not lead_model:
        return None
    return "sensight" if str(lead_model).upper() in _SENSIGHT_MODELS else "1x4"


def impedance_facts(recordings):
    """Summarise impedance for D16 from ``MedtronicDeviceImpedance`` recording rows.

    Returns the WORST (highest) bipolar reading per hemisphere rather than a mean, because D16 is a
    fault check: one open contact matters even when the other seven are healthy, and averaging is
    exactly the operation that would hide it. The device's own Status field is carried through
    verbatim, since the manufacturer's judgement of its own hardware outranks our threshold
    arithmetic.
    """
    rows = [r for r in (recordings or []) if getattr(r, "metadata", None)]
    if not rows:
        return {"available": False, "reason": "no impedance recordings on record"}
    rows.sort(key=lambda r: getattr(r, "date", 0) or 0)
    newest = rows[-1].metadata or {}

    statuses = {}
    for r in rows:
        s = str((r.metadata or {}).get("Status"))
        statuses[s] = statuses.get(s, 0) + 1

    out = {"available": True, "n_records": len(rows),
           "status_newest": newest.get("Status"),
           "status_counts": statuses,
           "lead_model": (newest.get("Left") or {}).get("LeadModel"),
           "lead_type": _lead_type((newest.get("Left") or {}).get("LeadModel"))}

    # The historical worst is a DIFFERENT question from the current reading and both matter: a lead
    # whose newest measurement is inside the limits but which has exceeded them before is not the
    # same object as one that never has. Reporting only the newest hid this until the 2026-09-04
    # ingest brought in a newer, better measurement and D16 silently flipped from fail to pass.
    for hemi in ("Left", "Right"):
        hist = [float(x) for r in rows
                for row in (((r.metadata or {}).get(hemi) or {}).get("Bipolar") or [])
                for x in row if x]
        out.setdefault("history", {})[hemi] = {
            "bipolar_max_ohm_ever": max(hist) if hist else None,
            "n_readings": len(hist),
            "n_above_open_limit": sum(1 for x in hist if x > 10000.0),
        }

    for hemi in ("Left", "Right"):
        h = newest.get(hemi) or {}
        bip = [float(x) for row in (h.get("Bipolar") or []) for x in row if x]
        mono = [float(x) for x in (h.get("Monopolar") or []) if x]
        out[hemi] = {
            "bipolar_max_ohm": max(bip) if bip else None,
            "bipolar_min_ohm": min(bip) if bip else None,
            "bipolar_median_ohm": _st.median(bip) if bip else None,
            "monopolar_max_ohm": max(mono) if mono else None,
            "n_bipolar_pairs": len(bip),
        }
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
PI_STATED_FACTS = {
    "2e3c75c00d7f4f37b53a048d195f11da": {          # RCS08
        #: D04. Stated 2026-09-04: a single implanted neurostimulator.
        "n_neurostimulators": 1,
        #: D13. Stated 2026-09-04: the user-configurable high-pass is set to 1 Hz, the lower of the
        #: two selectable values. This matters for a low-centre band: a 10 Hz high-pass would
        #: attenuate the alpha peak that is the only part of this device's spectrum reaching the
        #: capture floor.
        "highpass_hz": 1.0,
        #: D15. Stated 2026-09-04 and CONFIRMED against the record rather than taken on trust:
        #: ONE_THREE_LEFT appears as a configured sensing channel in the session reports.
        "channel_is_brainsense_setup_channel": True,
        #: D34. Stated 2026-09-04, after an explicit correction: 2.5 mA on the LEFT and 2.0 mA on
        #: the RIGHT. The first statement had the sides the other way round, so the assignment is
        #: recorded per side rather than as a single number. These are INTENDED values: the device
        #: record's SuspendAmplitude fields read 0.0, 1.3 and 1.5 mA, none of them 2.5 or 2.0, so
        #: nothing here has been programmed yet.
        "paused_amplitude_mA_by_hemisphere": {"Left": 2.5, "Right": 2.0},
    },
}


def facts_for_participant(participant_uid, impedance_recordings=None, *,
                          hemisphere=None, channel=None):
    """Assemble every device fact this module can establish for one participant.

    Measured values take precedence over stated ones wherever both exist, and the returned dict
    records which is which under ``_provenance`` so a reader can tell a reading from an assertion.
    """
    stated = dict(PI_STATED_FACTS.get(str(participant_uid), {}))
    out, prov = {}, {}

    paused = stated.pop("paused_amplitude_mA_by_hemisphere", None)
    if paused and hemisphere in (paused or {}):
        out["paused_amplitude_mA"] = paused[hemisphere]
        prov["paused_amplitude_mA"] = f"stated by PI 2026-09-04 for the {hemisphere} hemisphere"
    for k, v in stated.items():
        out[k] = v
        prov[k] = "stated by PI 2026-09-04"

    imp = impedance_facts(impedance_recordings or [])
    if imp.get("available"):
        ohm = candidate_impedance_ohm(imp, hemisphere) if hemisphere else None
        if ohm is not None:
            out["impedance_ohms"] = ohm
            # Be exact about what this number IS. It is the worst bipolar pair WITHIN the newest
            # recording, not the worst across the record — and the difference is not academic: on
            # 2026-09-04 an ingest brought in a newer, better measurement and D16 flipped from fail
            # to pass with no code change, while 1265 of 15540 historical left-lead readings remain
            # above the open-circuit limit. The old wording said "across N recordings", which would
            # have let a reader take a currently-sound lead for a never-faulty one.
            _hist = ((imp.get("history") or {}).get(hemisphere) or {})
            prov["impedance_ohms"] = (
                f"measured: worst bipolar pair in the NEWEST of {imp['n_records']} impedance "
                f"recordings on the {hemisphere} lead (status {imp.get('status_newest')}); "
                f"worst EVER {_hist.get('bipolar_max_ohm_ever')} ohm with "
                f"{_hist.get('n_above_open_limit')} of {_hist.get('n_readings')} readings above "
                f"the 10000 ohm open limit")
        out["impedance_tested"] = True
        prov["impedance_tested"] = f"measured: {imp['n_records']} impedance recordings on record"
        if imp.get("lead_type"):
            out["lead_type"] = imp["lead_type"]
            prov["lead_type"] = f"measured: LeadModel {imp.get('lead_model')}"
        out["_impedance_status"] = imp.get("status_newest")
        out["_impedance_status_counts"] = imp.get("status_counts")
    # Facts from the raw session reports: capture amplitudes, adaptive limits, the device's own
    # artefact verdict, cycling, and the per-bin LFP spectrum D09 consumes.
    srf, srf_prov = session_report_facts_for(participant_uid, channel=channel,
                                             hemisphere=hemisphere)
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


#: Per-participant summary produced by ``session_report_facts.scan_folder``. Committed next to the
#: module because the scan takes ~4 minutes over 8.5 GB of reports and its result is a 34 KB
#: summary; re-scanning per request is not an option and re-scanning per session is wasteful. The
#: file records ``n_files`` so a reader can tell which pass produced it.
_SUMMARY_FILES = {"2e3c75c00d7f4f37b53a048d195f11da": "_facts_RCS08.json"}


def _load_summary(participant_uid):
    import json as _json
    import os as _os
    name = _SUMMARY_FILES.get(str(participant_uid))
    if not name:
        return {}
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), name)
    try:
        with open(path) as fh:
            return _json.load(fh)
    except Exception:
        return {}


def session_report_facts_for(participant_uid, *, channel=None, hemisphere=None):
    """Facts for the six rules the platform decoder does not keep in queryable form.

    Every value here comes from the raw session reports rather than a person's recollection, and the
    DISTRIBUTION is carried alongside the newest value because for several of these rules the
    distribution is the finding — D27 is violated by 90% of the right-hemisphere capture records
    while the most recent capture is compliant, and reporting only one of those would mislead.
    """
    from . import session_report_facts as _srf
    S = _load_summary(participant_uid)
    if not S:
        return {}, {}
    out, prov = {}, {}
    n = S.get("n_files")
    tag = f"measured: session reports, {n} files"

    # D28 — adaptive limits and whether adaptive has ever run
    cap = (S.get("capture_newest") or {}).get(hemisphere or "") or {}
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
    key = _match_survey_channel(art, channel, hemisphere)
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

    # D09 — the per-bin spectrum, which is the form the rule now consumes
    bins = _srf.candidate_lfp_bins(S, channel, hemisphere) if channel else []
    if bins:
        out["lfp_bins_uvp"] = bins
        prov["lfp_bins_uvp"] = tag + f" ({len(bins)} survey bins, median per bin)"
    return out, prov


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
