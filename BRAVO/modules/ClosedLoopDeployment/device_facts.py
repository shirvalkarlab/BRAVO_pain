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


def facts_for_participant(participant_uid, impedance_recordings=None, *, hemisphere=None):
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
            prov["impedance_ohms"] = (
                f"measured: worst bipolar reading on the {hemisphere} lead across "
                f"{imp['n_records']} impedance recordings, newest record")
        out["impedance_tested"] = True
        prov["impedance_tested"] = f"measured: {imp['n_records']} impedance recordings on record"
        if imp.get("lead_type"):
            out["lead_type"] = imp["lead_type"]
            prov["lead_type"] = f"measured: LeadModel {imp.get('lead_model')}"
        out["_impedance_status"] = imp.get("status_newest")
        out["_impedance_status_counts"] = imp.get("status_counts")
    out["_provenance"] = prov
    return out
