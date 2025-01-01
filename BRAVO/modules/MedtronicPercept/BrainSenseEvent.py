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