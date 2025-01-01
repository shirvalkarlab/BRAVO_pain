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

from modules import Therapy, Database
from modules.utility.PythonUtility import rangeSelection

key = os.environ.get('DATASERVER_ENCRYPTION')

def saveChronicBrainSense(ChronicLFPs):
    """ Save Chronic BrainSense Data in Database Storage

    Args:
      deviceID: UUID4 deidentified id for each unique Percept device.
      ChronicLFPs: Chronic BrainSense (Power-band) structures extracted from Medtronic JSON file.
      sourceFile: filename of the raw JSON file that the original data extracted from.

    Returns:
      Boolean indicating if new data is found (to be saved).
    """

    NewRecordings = []
    for key in ChronicLFPs.keys():
        if key == "HemisphereLocationDef.Right": 
            hemisphere = "RightHemisphere"
        else:
            hemisphere = "LeftHemisphere"

        Time = np.array([t.timestamp() for t in ChronicLFPs[key]["DateTime"]])
        Amplitude = ChronicLFPs[key]["Amplitude"]
        LFP = ChronicLFPs[key]["LFP"]

        Recording = dict()
        Recording["SamplingRate"] = -1 # Variable Frequency
        Recording["Time"] = Time
        Recording["Data"] = np.zeros((len(Recording["Time"]),2))
        Recording["Data"][:,0] = LFP
        Recording["Data"][:,1] = Amplitude
        Recording["ChannelNames"] = [hemisphere + " LFP", hemisphere + " Amplitude"]
        Recording["StartTime"] = Recording["Time"][0]
        Recording["Duration"] = Recording["Time"][-1] - Recording["Time"][0]
        NewRecordings.append(Recording)

    return NewRecordings

def extractTherapyString(note):
    try:
        TherapyString = str(int(note["Stimulation"]["Frequency"])) + "Hz " + str(int(note["Stimulation"]["Pulsewidth"])) + "" + note["Stimulation"]["PulsewidthUnit"]

        if note["Stimulation"]["ReturnContact"] == ["CAN"]:
            TherapyString += " [" + "|".join(note["Stimulation"]["Contact"]) + "]"
        else:
            TherapyString += " [" + " ".join(note["Stimulation"]["Contact"]) + " => " + " ".join(note["Stimulation"]["ReturnContact"]) + "]"
        return TherapyString
    except Exception as e:
        return "Unknown"
    
def extractSensingString(note):
    try:
        if "Bypass" in note["Adaptive"]["StimulationConfiguration"]["Config"].keys():
            return str(note["Adaptive"]["RecordingConfiguration"]["Config"]["SensingSetup"]["FrequencyInHertz"]) + "Hz Bypassed"
        else:
            return str(note["Adaptive"]["RecordingConfiguration"]["Config"]["SensingSetup"]["FrequencyInHertz"]) + "Hz"
    except Exception as e:
        return "Unknown"
    
def extractChronicNeuralActivity(participant, devices, recordings, config):
    TherapyHistory = Therapy.queryTherapyHistory(participant)
    ChronicNeuralActivity = []
    for recording in recordings:
        RecordingInfo = recording.get_info()
        Data = Database.loadSourceFile(recording.pointer, recording.hashed)
        DBSDevice = devices.filter(uid=RecordingInfo["Device"]).first().get_info() # NOTE: SQL-Specific QuerySet
        for i in range(len(TherapyHistory["TherapyModification"])):
            if TherapyHistory["TherapyModification"][i]["Device"]["Id"] == DBSDevice["Id"]:
                TherapyHistory["TherapyModification"][i]["History"] = [j for j in TherapyHistory["TherapyModification"][i]["History"] if j["Type"] == "TherapyChangeGroup"]
                TherapyHistory["TherapyModification"][i]["History"].sort(key=lambda x: x["Date"])
                Timestamps = [event["Date"] for event in TherapyHistory["TherapyModification"][i]["History"]]
                for j in range(1, len(Timestamps)):
                    # TODO: Make it less specific to Percept
                    WindowSelected = rangeSelection(Data["Time"], [Timestamps[j-1], Timestamps[j]]) & (Data["Data"][:,0] < 50000)
                    if np.any(WindowSelected):
                        GroupId = TherapyHistory["TherapyModification"][i]["History"][j-1]["New"]
                        if datetime.fromtimestamp(Data["Time"][0]).isoformat() == "2021-07-02T21:59:16":
                            print(TherapyHistory["TherapyModification"][i]["History"][j-1])
                        ClosestTherapy = Therapy.findClosestTherapy(Data["Time"][WindowSelected][0], "Left" if Data["ChannelNames"][0].startswith("Left") else "Right", GroupId, TherapyHistory["TherapyConfiguration"][i]["History"])
                        TherapyNote = Therapy.findClosestAdaptiveTherapy(Data["Time"][WindowSelected][0], ClosestTherapy)
                        if extractSensingString(TherapyNote) == "Unknown":
                            GroupId = TherapyHistory["TherapyModification"][i]["History"][j]["Previous"]
                            ClosestTherapy = Therapy.findClosestTherapy(Data["Time"][WindowSelected][0], "Left" if Data["ChannelNames"][0].startswith("Left") else "Right", GroupId, TherapyHistory["TherapyConfiguration"][i]["History"])
                            TherapyNote = Therapy.findClosestAdaptiveTherapy(Data["Time"][WindowSelected][0], ClosestTherapy)

                        ChronicNeuralActivity.append({
                            "Device": DBSDevice["Id"],
                            "TherapyWindow": [Timestamps[j-1], Timestamps[j]],
                            "TherapyNote": TherapyNote,
                            "TherapyString": extractTherapyString(TherapyNote),
                            "RecordingString": extractSensingString(TherapyNote),
                            "Time": Data["Time"][WindowSelected],
                            "ChannelNames": copy.deepcopy(Data["ChannelNames"]),
                            "ChannelUnits": ["", "mA"],
                            "Data": Data["Data"][WindowSelected,:].T
                        })

    return ChronicNeuralActivity
