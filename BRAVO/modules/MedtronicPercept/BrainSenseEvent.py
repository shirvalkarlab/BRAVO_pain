""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
Medtronic Percept BrainSense Event Logs Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from datetime import datetime
import copy
import json
import hashlib
import math
import numpy as np
import pandas as pd

key = os.environ.get('DATASERVER_ENCRYPTION')

def saveBrainSenseEvents(LfpFrequencySnapshotEvents):
    """ Save BrainSense Events Data in NoSQL Database.

    Args:
      participant: Study participant model
      device: Recording device model
      LfpFrequencySnapshotEvents: Event-snapshot Power Spectrum data extracted from Medtronic JSON file.

    Returns:
      Boolean indicating if new data is found (to be saved).
    """

    NewRecordings = []
    for event in LfpFrequencySnapshotEvents:
        EventTime = event["DateTime"].timestamp()
        SensingExist = False
        if "LfpFrequencySnapshotEvents" in event.keys():
            SensingExist = True
            EventData = event["LfpFrequencySnapshotEvents"]

        event = { "name": event["EventName"], "type": "PatientControllerEvent", "date": EventTime }
        if SensingExist:
            event["data"] = EventData
        NewRecordings.append(event)
    return NewRecordings

def _is_side(key):
    return str(key).startswith("HemisphereLocationDef")


def _usable_sense_id(value):
    """NOT_SET is absent evidence, not an electrode configuration."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return "" if not value or value.split(".")[-1].upper() == "NOT_SET" else value


def _sense_observations(block, source):
    observations = block.get("SenseIDObservations")
    if observations:
        return copy.deepcopy(observations)
    item = {"sense_id": block.get("SenseID")}
    if source:
        item["source"] = copy.deepcopy(source)
    return [item]


def _merge_sense_observations(have, incoming, *, stored_source=None, incoming_source=None):
    observations = _sense_observations(have, stored_source) + _sense_observations(incoming, incoming_source)
    # Sorting the serialized identity makes re-import and export order immaterial.
    unique = {json.dumps(item, sort_keys=True, separators=(",", ":")): item for item in observations}
    observations = [unique[key] for key in sorted(unique)]
    usable = sorted({_usable_sense_id(item.get("sense_id")) for item in observations} - {""})
    ambiguous = len(usable) > 1 or bool(have.get("UnverifiedSenseIDObservations"))
    merged = dict(have, SenseID=usable[0] if len(usable) == 1 and not ambiguous else "",
                  SenseIDObservations=observations, SenseIDConflict=ambiguous,
                  SenseIDStatus="ambiguous" if ambiguous else "resolved" if usable else "unresolved")
    return merged


RAW_SPECTRUM_VERSION = "raw-event-spectrum-v2"


def _exact_numeric_identity(value):
    """Canonical exact numbers; no float conversion of integers or numeric strings."""
    if isinstance(value, bool):
        raise ValueError("identity_boolean_invalid")
    if isinstance(value, int):
        return ["number", value, 1]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("identity_nonfinite_invalid")
        numerator, denominator = value.as_integer_ratio()
        return ["number", numerator, denominator]
    if isinstance(value, list):
        return [_exact_numeric_identity(item) for item in value]
    if isinstance(value, str):
        return value
    raise ValueError("identity_type_invalid")


def rawSpectrumDigest(block):
    """Exact source numeric arrays, before database JSON conversion. No tolerance."""
    values = [block.get("Frequency"), block.get("FFTBinData")]
    if any(not isinstance(v, list) or not v for v in values) or len(values[0]) != len(values[1]):
        raise ValueError("spectrum_arrays_invalid")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or (isinstance(x, float) and not math.isfinite(x))
           for values_ in values for x in values_):
        raise ValueError("spectrum_numbers_invalid")
    return hashlib.sha256(json.dumps(_exact_numeric_identity(values), separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sourceEventIndex(raw, table, clock_module, percept):
    """Compact source-bound event index using exactly the canonical clock/parser.

    The original raw document is never modified. A nonunique native key stays a list
    and must be refused by the caller. No participant/filename data leaves storage.
    """
    raw_events = (raw.get("DiagnosticData") or {}).get("LfpFrequencySnapshotEvents") or []
    serial = ((raw.get("DeviceInformation") or {}).get("Final") or {}).get("NeurostimulatorSerialNumber")
    skinny = {key: copy.deepcopy(raw[key]) for key in ("SessionDate", "SessionEndDate", "DeviceInformation") if key in raw}
    events = copy.deepcopy(raw_events)
    for i, event in enumerate(events):
        event["_SpectrumOriginalIndex"] = i
    skinny["DiagnosticData"] = {"LfpFrequencySnapshotEvents": events}
    clock_module.convert_export(skinny, table)
    converted = skinny["DiagnosticData"]["LfpFrequencySnapshotEvents"]
    decoded = percept.extractChronicLFP(skinny, {})
    saved = saveBrainSenseEvents(decoded.get("PatientEventLogs", []))
    if len(converted) != len(saved):
        raise ValueError("source_event_projection_cardinality")
    index = {}
    for event, native in zip(converted, saved):
        ordinal = event["_SpectrumOriginalIndex"]
        original = raw_events[ordinal]
        for side, block in (native.get("data") or {}).items():
            if not _is_side(side):
                continue
            source_block = original["LfpFrequencySnapshotEvents"][side]
            def clock_identity(item):
                block_id, offset = item.get("DateTimeBlockId"), item.get("DateTimeOffsetInSeconds")
                if block_id is not None and offset is not None:
                    return ["clock", block_id, offset]
                return ["datetime", item["DateTime"]] if item.get("DateTime") else None
            raw_key = [serial, clock_identity(original), original.get("EventID"), original.get("EventName"), side, clock_identity(source_block)]
            if any(value is None or value == "" for value in raw_key):
                continue
            try:
                source_digest, native_digest = rawSpectrumDigest(source_block), rawSpectrumDigest(block)
                exact_raw_key = _exact_numeric_identity(raw_key)
            except ValueError:
                # Retain malformed/partial raw blocks for display, but never assign identity.
                continue
            if source_digest != native_digest:
                raise ValueError("source_projection_changed_spectrum")
            identity = {"version": RAW_SPECTRUM_VERSION, "sha256": source_digest,
                        "raw_identity_sha256": hashlib.sha256(json.dumps(exact_raw_key, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                        "raw_event_index": ordinal}
            key = (native["name"], float(native["date"]), side)
            index.setdefault(key, []).append({"identity": identity, "block": block})
    return index


def _same_spectrum(have, incoming, stored_identity, incoming_identity):
    if stored_identity is not None or incoming_identity is not None:
        return (stored_identity is not None and incoming_identity is not None and
                stored_identity["sha256"] == incoming_identity["sha256"] and
                stored_identity["raw_identity_sha256"] == incoming_identity["raw_identity_sha256"])
    return (list(have.get("FFTBinData") or []) == list(incoming.get("FFTBinData") or []) and
            list(have.get("Frequency") or []) == list(incoming.get("Frequency") or []))



def _withhold_identity(have, incoming, reason, stored_source, incoming_source):
    """Keep unsupported copy claims separate from the established spectrum ledger."""
    result = copy.deepcopy(have)
    deferred = copy.deepcopy(have.get("UnverifiedSenseIDObservations") or [])
    claim = {"sense_id": incoming.get("SenseID"), "source": copy.deepcopy(incoming_source), "reason": reason}
    if claim not in deferred:
        deferred.append(claim)
    deferred.sort(key=lambda value: json.dumps(value, sort_keys=True))
    result.update(SenseIDObservations=_sense_observations(have, stored_source),
                  SenseID="", SenseIDConflict=True, SenseIDStatus="ambiguous",
                  SpectrumIdentityStatus="unverified", SpectrumIdentityReason=reason,
                  UnverifiedSenseIDObservations=deferred)
    return result


def mergeEventData(stored, incoming, *, stored_source=None, incoming_source=None,
                   stored_identities=None, incoming_identities=None, blocked_sides=()):
    """Merge spectral copies without inventing contact precedence.

    Same-array copies retain their raw contact claims and opaque source provenance.
    Empty/NOT_SET claims can be enriched by one explicit contact; two different
    explicit contacts remain ambiguous, with SenseID blank and SenseIDConflict true.
    Completion status is evidence only: this function never prefers a completed read.
    Raw spectra stay intact, including when contact-specific analysis is unavailable.

    Returns (create/drop/update/keep, data, conflicting_sides). Different arrays keep
    the prior spectrum and report the existing spectral conflict policy; their original
    exports remain in source storage. Contact conflicts also report the side, and all
    contact copies remain in SenseIDObservations. Neither input is mutated.
    """
    incoming = copy.deepcopy(dict(incoming or {}))
    # Identity maps come only from the ingester's verified raw-source boundary.
    for side, identity in (incoming_identities or {}).items():
        incoming[side]["RawSpectrumIdentity"] = copy.deepcopy(identity)
    if stored is None:
        if not any(_is_side(key) for key in incoming):
            return "drop", {}, []
        merged = dict(incoming)
        for key, block in incoming.items():
            if _is_side(key):
                merged[key] = (_withhold_identity(block, block, blocked_sides[key], incoming_source, incoming_source)
                               if key in blocked_sides else
                               _merge_sense_observations(block, block, stored_source=incoming_source, incoming_source=incoming_source))
        return "create", merged, [key for key, block in merged.items() if _is_side(key) and block.get("SenseIDConflict")]
    merged, conflicts = copy.deepcopy(dict(stored)), []
    for key, block in incoming.items():
        if not _is_side(key):
            continue
        have = merged.get(key)
        if key in blocked_sides:
            merged[key] = _withhold_identity(have if have is not None else block, block, blocked_sides[key],
                                             stored_source if have is not None else incoming_source, incoming_source)
            conflicts.append(key)
            continue
        if have is not None and key in (stored_identities or {}):
            have["RawSpectrumIdentity"] = copy.deepcopy(stored_identities[key])
        if have is None:
            merged[key] = _merge_sense_observations(block, block, stored_source=incoming_source, incoming_source=incoming_source)
        elif not _same_spectrum(have, block, (stored_identities or {}).get(key), (incoming_identities or {}).get(key)):
            conflicts.append(key)
            continue
        else:
            merged[key] = _merge_sense_observations(have, block, stored_source=stored_source, incoming_source=incoming_source)
        if merged[key].get("SenseIDConflict"):
            conflicts.append(key)
    return ("update" if merged != stored else "keep"), merged, sorted(set(conflicts))


def extractBrainSenseEventRecording(data, DBSDevices):
    from .ContactAdjudication import validated_contact_adjudication
    Device = DBSDevices.filter(uid=data["Device"]).first().get_info() # TODO: SQL-Specific Syntax
    EventPSDs = []
    for hemisphere in data["Metadata"].keys():
        ChannelName = hemisphere
        for k in range(len(Device["Electrodes"])):
            if hemisphere.endswith(Device["Electrodes"][k]["Target"].split(" ")[0]):
                ChannelName = Device["Electrodes"][k]["CustomName"]
                break

        block = data["Metadata"][hemisphere]
        adjudication = validated_contact_adjudication(
            block, hemisphere=hemisphere, recording_uid=data.get("Id"))
        EventPSDs.append({
            "Device": data["Device"],
            "DeviceHeritage": Device["Heritage"],
            "ChannelName": ChannelName,
            "Frequency": data["Metadata"][hemisphere]["Frequency"],
            "Power": data["Metadata"][hemisphere]["FFTBinData"],
            "Date": data["Date"],
            "SenseConfig": adjudication["sense_id"] if adjudication else block["SenseID"],
            "SenseConfigStatus": adjudication["status"] if adjudication else block.get("SenseIDStatus", "unverified"),
            "SenseConfigRawStatus": block.get("SenseIDStatus", "unverified"),
            "SenseConfigAdjudicationSummary": adjudication["summary"] if adjudication else None,
            "SenseConfigUnavailableReason": data["Metadata"][hemisphere].get("SpectrumIdentityReason"),
            "SenseConfigConflict": bool(data["Metadata"][hemisphere].get("SenseIDConflict", False))
        })
    return EventPSDs
