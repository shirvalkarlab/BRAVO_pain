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


def mergeEventData(stored, incoming):
    """How one more copy of a patient event combines with what is stored (decision 439).

    The same event appears in several exports and its copies differ: the device adds the PSD to a
    later export and drops it from a still later one, lists one side only, or leaves the contact
    pair (`SenseID`) empty. Every copy is merged; nothing is lost to the order the exports arrive in.

    ``stored`` is the stored event's brain data (its per-side PSD blocks, keyed
    ``HemisphereLocationDef.*``), ``{}`` for a stored event without any, ``None`` when the event
    is not stored. ``incoming`` is this copy's (``None`` or ``{}`` when it has none).

    Returns ``(action, data, conflicts)``: ``"create"`` (store a new event with ``data``),
    ``"drop"`` (no brain data in any copy: not stored), ``"update"`` (replace the stored data with
    ``data``), ``"keep"`` (nothing to change). ``conflicts`` lists the sides whose spectra differ
    between copies; the stored spectrum is kept and the conflict is reported, never resolved
    silently.
    """
    incoming = dict(incoming or {})
    if stored is None:
        if any(_is_side(k) for k in incoming):
            return "create", incoming, []
        return "drop", {}, []
    merged = dict(stored)
    changed, conflicts = False, []
    for key, block in incoming.items():
        if not _is_side(key):
            continue
        have = merged.get(key)
        if have is None:
            merged[key] = block
            changed = True
            continue
        if list(have.get("FFTBinData") or []) != list(block.get("FFTBinData") or []) or \
                list(have.get("Frequency") or []) != list(block.get("Frequency") or []):
            conflicts.append(key)
            continue
        if not have.get("SenseID") and block.get("SenseID"):
            merged[key] = dict(have, SenseID=block["SenseID"])
            changed = True
    return ("update" if changed else "keep"), merged, conflicts


def extractBrainSenseEventRecording(data, DBSDevices):
    Device = DBSDevices.filter(uid=data["Device"]).first().get_info() # TODO: SQL-Specific Syntax
    EventPSDs = []
    for hemisphere in data["Metadata"].keys():
        ChannelName = hemisphere
        for k in range(len(Device["Electrodes"])):
            if hemisphere.endswith(Device["Electrodes"][k]["Target"].split(" ")[0]):
                ChannelName = Device["Electrodes"][k]["CustomName"]
                break

        EventPSDs.append({
            "Device": data["Device"],
            "DeviceHeritage": Device["Heritage"],
            "ChannelName": ChannelName,
            "Frequency": data["Metadata"][hemisphere]["Frequency"],
            "Power": data["Metadata"][hemisphere]["FFTBinData"],
            "Date": data["Date"],
            "SenseConfig": data["Metadata"][hemisphere]["SenseID"]
        })
    return EventPSDs