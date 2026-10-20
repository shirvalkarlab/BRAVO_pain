"""Owner-scoped implant identity with explicitly bounded private device groups.

Equal nonempty serials join records only for the same owner and device type.
An evidence-backed exception names exact device UIDs in the private participant
``implant_groups`` section; it never absorbs a future same-type implant.
"""
from .private_clinical_config import participant_section, ClinicalConfigurationUnavailable


def configured_groups(owner_uid):
    """Return validated groups, or no exceptions if private evidence is unavailable."""
    try:
        section = participant_section(owner_uid, "implant_groups")
    except ClinicalConfigurationUnavailable:
        return ()
    groups = section.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ClinicalConfigurationUnavailable("Implant groups require explicit device membership.")
    result, seen = [], set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"device_type", "device_uids"}:
            raise ClinicalConfigurationUnavailable("Invalid implant group fields.")
        dtype, uids = group["device_type"], group["device_uids"]
        if not isinstance(dtype, str) or not dtype.strip() or not isinstance(uids, list) or len(uids) < 2:
            raise ClinicalConfigurationUnavailable("Implant group requires type and at least two devices.")
        if any(not isinstance(uid, str) or not uid.strip() for uid in uids):
            raise ClinicalConfigurationUnavailable("Implant group contains an invalid device identity.")
        if len(set(uids)) != len(uids) or seen.intersection(uids):
            raise ClinicalConfigurationUnavailable("Implant groups have duplicate or overlapping devices.")
        seen.update(uids)
        result.append((dtype, frozenset(uids)))
    return tuple(result)


def concrete_serial(value):
    """Recognized redaction placeholders are not implant identity evidence."""
    return (isinstance(value, str) and bool(value.strip())
            and value.strip().lower() not in {"unknown", "masked", "redacted"}
            and not any(character == "*" or 0x2580 <= ord(character) <= 0x259f for character in value))


def same_implant(owner_a, type_a, serial_a, owner_b, type_b, serial_b, *, device_a=None, device_b=None):
    """Identity never crosses owners, even when serial numbers match."""
    if not owner_a or not owner_b or str(owner_a) != str(owner_b) or not type_a or type_a != type_b:
        return False
    if concrete_serial(serial_a) and serial_a == serial_b:
        return True
    if not device_a or not device_b:
        return False
    return any(dtype == type_a and str(device_a) in uids and str(device_b) in uids
               for dtype, uids in configured_groups(owner_a))


def device_uids(rows, device_uid=None, serial=None, owner_uid=None, owner_only=None):
    """Resolve a seed against `(uid, serial, owner, type)` rows without owner guessing.

    Serial-only queries require an explicit owner. No seed means no inferred
    implant, even when private groups exist. Unknown device IDs are not accepted.
    """
    by = {str(r[0]): (str(r[0]), r[1], str(r[2]), r[3]) for r in rows}
    seed = by.get(str(device_uid)) if device_uid else None
    owner = str(owner_only if owner_only is not None else owner_uid) if (owner_only is not None or owner_uid is not None) else None
    if seed:
        if owner is not None and seed[2] != owner:
            return []
        owner = seed[2]
    if not owner or (owner_uid is not None and str(owner_uid) != owner):
        return []
    owned = {uid: row for uid, row in by.items() if row[2] == owner}
    selected = {seed[0]} if seed else {uid for uid, row in owned.items() if serial and row[1] == serial}
    if not seed and selected and not concrete_serial(serial):
        # A masked token supplies no independent link. It can only locate the
        # already verified explicit group, never an unbound same-token record.
        groups = configured_groups(owner)
        if not any(selected <= uids and all(owned[uid][3] == dtype for uid in selected)
                   for dtype, uids in groups):
            return []
    while selected:
        more = {uid for uid, row in owned.items() if any(
            same_implant(by[u][2], by[u][3], by[u][1], row[2], row[3], row[1], device_a=u, device_b=uid)
            for u in selected)} - selected
        if not more:
            break
        selected.update(more)
    return sorted(selected)
