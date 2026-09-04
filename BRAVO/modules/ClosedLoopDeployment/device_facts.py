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
