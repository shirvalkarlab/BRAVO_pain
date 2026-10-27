"""Which device records are ONE implant, where the serial number cannot say (decision 489).

THE RULE. Two device records are one implant when they share a serial number (decision 444: RCS08's
implant is filed as several records), OR when their owner is listed in `ONE_IMPLANT` and both are of
the device type listed there. The list is explicit and each entry names the ruling that made it:
nothing here is guessed from the format of a serial number.

WHY A LIST. The Dropbox copies mask the serial number; the two RCS08 implant-day exports
(2025-07-16 19:40 and 2025-07-17 00:31) had theirs restored (decision 479), so their device record
carries a different serial from the main record and the two split: the one chronic-log schedule
(decision 487) and the tablet-clock anchor tables (decision 444) were built without the implant-day
exports. Device record ids are made afresh by every ingest, so the link is kept by owner and type.

A participant who receives a second device of the same type must be taken off this list, or given
a date bound, before that device's first export is ingested.
"""

#: participant uid -> {"type": device type, "ruling": who decided and when}
ONE_IMPLANT = {
    "2e3c75c00d7f4f37b53a048d195f11da": {     # RCS08
        "type": "Percept RC",
        "ruling": "the PI, 2026-10-19: the implant-day device record and the main device record are one implant",
    },
}


def one_implant_type(owner_uid):
    """The device type every record of which is one implant for this owner, or None."""
    entry = ONE_IMPLANT.get(str(owner_uid or ""))
    return entry["type"] if entry else None


def same_implant(owner_a, type_a, serial_a, owner_b, type_b, serial_b):
    """True when two device records are one implant by THE RULE in the module text."""
    if serial_a and serial_a == serial_b:
        return True
    t = one_implant_type(owner_a)
    return bool(t) and str(owner_a) == str(owner_b) and type_a == t and type_b == t
