"""Participant/device-scoped observations, never a BrainSense compatibility envelope.

Use the shared, source-keyed settings cache. It admits only unambiguous active
group snapshots and preserves native status fields. An active group and recorded
ON flags still do not establish continuous delivery, successful sensing, or a
manufacturer-approved operating limit. No history here is supplied to D31.
"""
import hashlib
import json
import math
from pathlib import Path
import time


def _quantity(value, unit):
    """Read one unit-labelled value from the shared settings presentation cache."""
    if not isinstance(value, str) or not value.endswith(" " + unit):
        return None
    try:
        number = float(value[:-(len(unit) + 1)])
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def collect(participant_uid, sources, load_context, *, now, earliest=None):
    """Collect cached observations with explicit owner, device and configuration identity.

    Counts are source snapshots, not distinct programming events. All settings in
    the group and on the side participate in configuration identity, so merely
    matching rate/pulse width cannot merge different sensing/contact settings.
    """
    configurations = {}
    excluded = 0
    unavailable = 0
    for source in sources:
        device = source.metadata.get("Device")
        if (str(source.owner_id) != str(participant_uid) or not device or
                source.type != "MedtronicJSON" or source.metadata.get("AnalysisExclusion")):
            excluded += 1
            continue
        context = load_context(source)
        if context is None:
            unavailable += 1
            continue
        if context["excluded"]:
            excluded += 1
            continue
        for event in context["events"]:
            stamp = event["time"]
            if (event["kind"] != "settings_observed" or not math.isfinite(stamp) or
                    stamp > now or (earliest is not None and stamp < earliest)):
                continue
            settings = event["settings"]
            group_fields = {field["label"]: field["value"] for field in settings["group"]}
            for side in ("left", "right"):
                fields = {field["label"]: field["value"] for field in settings[side]}
                rate = _quantity(fields.get("Frequency"), "Hz")
                pw = _quantity(fields.get("Pulse width"), "µs")
                # Missing/multiple side programs cannot define a unique pair.
                if rate is None or pw is None:
                    continue
                configuration = {"participant_id": str(participant_uid), "device_id": str(device),
                                 "hemisphere": side.capitalize(), "rate_hz": rate,
                                 "pulse_width_us": pw, "group_settings": settings["group"],
                                 "side_settings": settings[side]}
                identity = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
                if identity not in configurations:
                    configurations[identity] = {
                        "id": identity, **configuration, "active_group_observed": True,
                        "stimulation_status": group_fields.get("Stimulation status", "Unknown"),
                        "sensing_status": fields.get("Sensing", "Unknown"),
                        "delivery_verified": None, "observations": []}
                observation = {"source_id": str(source.uid), "source_hash": source.hashed,
                               "time": stamp, "phase": event["phase"]}
                if observation not in configurations[identity]["observations"]:
                    configurations[identity]["observations"].append(observation)
    return {"participant_id": str(participant_uid), "configurations": list(configurations.values()),
            "excluded_source_count": excluded,
            "unavailable_source_count": unavailable,
            "scope": "Eligible native active-group snapshots, grouped by participant, device, side and complete recorded settings. Inactive or ambiguous groups are not included.",
            "interpretation": "Previously observed configuration only. Recorded stimulation/sensing statuses are snapshot declarations; actual delivery and successful sensing are not verified. Repeated snapshots are not separate programming events.",
            "compatibility_gate_effect": "None; historical observations do not supply or override D31 device limits."}


def for_participant(participant, sources, *, now=None):
    """Read evidence without fitting a model, syncing data or programming a device."""
    from modules import RedcapStimulation, RCS08DataPolicy
    reviewed = RCS08DataPolicy.applies_to(participant)
    policy_hash = hashlib.sha256(Path(RCS08DataPolicy.__file__).read_bytes()).hexdigest()
    return collect(participant.uid, sources,
                   lambda source: RedcapStimulation.source_context(
                       source, participant, reviewed, policy_hash, cached_only=True)[0],
                   now=time.time() if now is None else now,
                   earliest=RCS08DataPolicy.IMPLANT_DAY if reviewed else None)
