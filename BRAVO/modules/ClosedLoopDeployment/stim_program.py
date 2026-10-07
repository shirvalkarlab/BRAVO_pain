"""The stimulation program a clinician defines on the Closed-Loop page (decision 467).

On screen: Closed-Loop page, the "Stimulation program" card at the top. Its "Inherit current
settings" fills it from the device's newest export (`current_program`); a program the user edits
travels in the report request as ``StimProgram`` and replaces the device's settings for the
device-rule checks (rate, pulse width, which rings stimulate) and in the parameter table
(contacts, rate, pulse width, paused amplitude, the closed-loop limits). The analyses of recorded
data stay on what was actually delivered: a program that has never run has no recordings.

Shape of a program (the page's and the server's; contacts numbered 0-3 on both sides, as the
device writes them; the right lead's 8-11 is a label the page adds)::

    {"rate_hz": 55,
     "Left":  {"contacts": {"2a": -1, "2b": -1, "2c": -1, "case": 1}, "amp_mA": 3.0, "pw_us": 100,
               "lower_limit_mA": 1.4, "upper_limit_mA": 4.0, "target": "Left GPe"},
     "Right": {...}}

Nothing here writes to the device.
"""
from __future__ import annotations

CONTACTS = ("0", "1a", "1b", "1c", "2a", "2b", "2c", "3", "case")
SIDES = ("Left", "Right")


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def normalise(program):
    """The program with only known keys and numbers as floats; ``None`` when it is not a program."""
    if not isinstance(program, dict):
        return None
    out = {"rate_hz": _num(program.get("rate_hz"))}
    for side in SIDES:
        s = program.get(side)
        if not isinstance(s, dict):
            continue
        contacts = {}
        for k, v in (s.get("contacts") or {}).items():
            k = str(k).lower()
            if k in CONTACTS and _num(v) in (-1.0, 1.0):
                contacts[k] = int(_num(v))
        out[side] = {"contacts": contacts, "amp_mA": _num(s.get("amp_mA")), "pw_us": _num(s.get("pw_us")),
                     "lower_limit_mA": _num(s.get("lower_limit_mA")),
                     "upper_limit_mA": _num(s.get("upper_limit_mA"))}
    return out


def ring(contact):
    """"2a" -> 2, "3" -> 3, "case" -> None."""
    c = str(contact)
    return int(c[0]) if c[:1].isdigit() else None


def contacts_text(contacts):
    """The program as the programmer writes it: "C+ 2a- 2b- 2c-" (positives first)."""
    order = lambda k: (ring(k) if ring(k) is not None else -1, k)
    pos = sorted((k for k, v in contacts.items() if v == 1), key=order)
    neg = sorted((k for k, v in contacts.items() if v == -1), key=order)
    return " ".join([("C" if k == "case" else k) + "+" for k in pos] + [k + "-" for k in neg])


def blocking_problems(side_program, sensing_pair=None, side="Left"):
    """What stops this side's program being programmed, in plain words; ``[]`` when nothing does.

    The same four the page shows: no negative contact; no positive contact (the case counts);
    negative contacts the sensing pair does not flank, so the device cannot sense (D52); the
    amplitude outside the closed-loop limits. Contact numbers are the side's own (8-11 on the right).
    """
    s = side_program or {}
    c = s.get("contacts") or {}
    out = []
    if not any(v == -1 for v in c.values()):
        out.append("No negative contact: no stimulation on this side")
    if not any(v == 1 for v in c.values()):
        out.append("No positive contact: make the case or a contact positive")
    if sensing_pair:
        # D52's rule (decision 217): the device senses only on the two contacts immediately
        # flanking the negative contacts, so the pair must be exactly that flanking pair.
        try:
            from DecodeCommon.sensing_rule import flanking_pair
        except ImportError:                              # pragma: no cover - module spelling
            from modules.DecodeCommon.sensing_rule import flanking_pair
        lo, hi = sensing_pair
        rings = {ring(k) for k, v in c.items() if v == -1 and ring(k) is not None}
        if rings and flanking_pair(rings) != (lo, hi):
            off = 8 if side == "Right" else 0
            need = list(range(lo + 1, hi))
            words = " and ".join(str(r + off) for r in need) if need else None
            out.append(f"Sensing on {lo + off}-{hi + off} needs stimulation on {words}: the device cannot sense"
                       if words else f"No stimulating contact lets the device sense on {lo + off}-{hi + off}")
    amp, lo_mA, hi_mA = s.get("amp_mA"), s.get("lower_limit_mA"), s.get("upper_limit_mA")
    if None not in (lo_mA, hi_mA) and lo_mA > hi_mA:
        out.append("Lowest current is above the highest")
    elif None not in (amp, lo_mA, hi_mA) and not lo_mA <= amp <= hi_mA:
        out.append("Amp is outside the lowest and highest current")
    return out


def device_facts_from_program(program, sensing_hemisphere):
    """The device facts a program replaces, for the sensing side's rules (D27, D30, D31, D52):
    ``rate_hz``, ``pulse_width_us``, ``stim_rings_on_sensing_lead`` and
    ``stim_contacts_on_sensing_lead``, plus ``_provenance``. ``{}`` with no program for that side."""
    p = normalise(program) or {}
    s = p.get(sensing_hemisphere)
    if not s:
        return {}
    neg = [k for k, v in s["contacts"].items() if v == -1 and ring(k) is not None]
    out = {"rate_hz": p.get("rate_hz"), "pulse_width_us": s.get("pw_us"),
           "stim_rings_on_sensing_lead": sorted({ring(k) for k in neg}),
           "stim_contacts_on_sensing_lead": "-".join(sorted(neg)) or "none"}
    out = {k: v for k, v in out.items() if v is not None}
    out["_provenance"] = ("your stimulation program, entered on the Closed-Loop page "
                          f"({sensing_hemisphere}: {contacts_text(s['contacts'])})")
    return out


def lead_targets(participant):
    """``{"Left": "Left GPe", "Right": "Right MD Thal"}`` from the participant's newest implanted
    device's leads (their stored names); ``{}`` when none is stored."""
    from Server import models as _m
    p = participant if hasattr(participant, "uid") else _m.Participant.find(uid=participant)
    if p is None:
        return {}
    devices = sorted(_m.DBSDevice.objects.filter(owner=p), key=lambda d: float(d.implanted_date or 0))
    out = {}
    for d in reversed(devices):
        for e in d.electrodes.all():
            name = str(e.custom_name or e.target or "")
            side = name.split(" ")[0] if name else ""
            if side in SIDES and side not in out:
                out[side] = name
        if out:
            break
    return out


def current_program(participant):
    """The program the device runs today, from the newest export's active sensing group, with each
    lead's target name. ``{"available": False, "reason": ...}`` when there is none."""
    from . import device_facts as _df
    facts = _df.active_sensing_group_facts(participant)
    prog = facts.get("active_sensing_group_program") or {}
    if not prog:
        return {"available": False,
                "reason": "the newest device export has no active group with sensing configured"}
    targets = lead_targets(participant)
    out = {"available": True, "rate_hz": facts.get("active_sensing_group_rate_hz"),
           "group": facts.get("active_sensing_group"),
           "session_date": facts.get("session_report_date")}
    for side in SIDES:
        if side in prog:
            out[side] = dict(prog[side], target=targets.get(side))
        elif side in targets:
            out[side] = {"contacts": {}, "target": targets[side]}
    return out
